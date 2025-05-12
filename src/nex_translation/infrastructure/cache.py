import json
from pathlib import Path
from typing import Optional, Any, Dict
from peewee import Model, SqliteDatabase, AutoField, CharField, TextField, SQL, Proxy
from ..utils.logger import get_logger

# 配置日志记录器
logger = get_logger(__name__)

# 全局数据库代理，允许延迟初始化或在不同上下文中使用不同数据库
# 这是一个更灵活处理数据库绑定的方式，尤其是在测试和生产环境切换时
db_proxy = Proxy()


class _TranslationCache(Model):
    """翻译缓存数据模型"""
    id = AutoField()
    translate_engine = CharField(max_length=20)  # 翻译引擎名称
    translate_engine_params = TextField()        # 翻译参数（JSON格式）
    original_text = TextField()                  # 原始文本
    translation = TextField()                    # 翻译结果

    class Meta:
        database = db_proxy  # 绑定到代理
        constraints = [
            SQL(
                """
                UNIQUE (
                    translate_engine,
                    translate_engine_params,
                    original_text
                )
                ON CONFLICT REPLACE
                """
            )
        ]

class TranslationCache:
    """翻译缓存管理器"""

    def __init__(
        self,
        translate_engine: str = "",
        translate_engine_params: Optional[Dict[str, Any]] = None,
        db_instance: Optional[SqliteDatabase] = None,  # 参数名改为 db_instance 以示区分
    ):
        assert len(translate_engine) <= 20, "翻译引擎名称不能超过20个字符"  # 原为 < 20
        self.translate_engine = translate_engine
        self.params: Dict[str, Any] = {}

        if db_instance is None:
            # 在测试中，我们总是希望显式传递 db_instance
            # 在生产中，它可能依赖于全局初始化的 db_proxy
            # 为了简单起见，这里假设在测试中 db_instance 总会被提供
            # 或者，如果 TranslationCache 可以在没有数据库的情况下用于某些操作，则相应调整
            logger.warning(
                "TranslationCache initialized without a specific db_instance. Operations requiring DB will use db_proxy."
            )
            self.db = db_proxy  # 如果没有提供，则依赖全局代理
        else:
            self.db = db_instance  # 使用传入的数据库实例

        self.replace_params(translate_engine_params)  # 确保在 self.db 设置后调用

    @staticmethod
    def _sort_dict_recursively(obj: Any) -> Any:
        """递归排序字典，确保相同内容的字典具有相同的字符串表示"""
        if isinstance(obj, dict):
            # 修正了之前版本中 for v in [obj[k]] 的冗余
            return {
                k: TranslationCache._sort_dict_recursively(obj[k])
                for k in sorted(obj.keys())
            }
        elif isinstance(obj, list):
            return [TranslationCache._sort_dict_recursively(item) for item in obj]
        return obj

    def replace_params(self, params: Optional[Dict[str, Any]] = None) -> None:
        """替换所有参数"""
        if params is None:
            params = {}
        self.params = params  # 存储原始（未排序）参数供内部使用
        # 对用于生成数据库键的参数进行排序和JSON化
        sorted_params_for_db = self._sort_dict_recursively(params.copy())  # 使用副本以防修改原始params
        self.translate_engine_params = json.dumps(sorted_params_for_db)

    def update_params(self, params: Optional[Dict[str, Any]] = None) -> None:
        """更新部分参数"""
        if params is None:
            params = {}
        current_params = self.params.copy()  # 使用副本进行更新
        current_params.update(params)
        self.replace_params(current_params)  # replace_params 会处理排序和JSON化

    def add_params(self, key: str, value: Any) -> None:
        """添加单个参数"""
        current_params = self.params.copy()
        # 确保值可以被 JSON 序列化
        try:
            # 尝试 JSON 序列化，如果失败则转换为字符串
            json.dumps(value)
            current_params[key] = value
        except (TypeError, OverflowError):
            # 如果值不可序列化，则转换为字符串
            current_params[key] = str(value)
        self.replace_params(current_params)

    def get(self, original_text: str) -> Optional[str]:
        """获取缓存的翻译结果"""
        try:
            # 确保 self.db 是一个已初始化的 SqliteDatabase 实例
            if not isinstance(self.db, SqliteDatabase) and not isinstance(self.db, Proxy) or \
               (isinstance(self.db, Proxy) and self.db.obj is None):
                logger.error("Database not initialized for TranslationCache.get")
                return None

            with self.db.connection_context():
                cached_item = _TranslationCache.get_or_none(
                    (_TranslationCache.translate_engine == self.translate_engine) &
                    (_TranslationCache.translate_engine_params == self.translate_engine_params) &
                    (_TranslationCache.original_text == original_text)
                )
                return cached_item.translation if cached_item else None
        except Exception as e:
            logger.debug(f"获取缓存时出错: {e}", exc_info=True)  # 添加 exc_info=True 获取更详细的堆栈信息
            return None

    def set(self, original_text: str, translation: str) -> None:
        """设置翻译缓存"""
        try:
            if not isinstance(self.db, SqliteDatabase) and not isinstance(self.db, Proxy) or \
               (isinstance(self.db, Proxy) and self.db.obj is None):
                logger.error("Database not initialized for TranslationCache.set")
                return

            with self.db.connection_context():
                _TranslationCache.replace(  # 使用 replace 而不是 create 来利用 ON CONFLICT REPLACE
                    translate_engine=self.translate_engine,
                    translate_engine_params=self.translate_engine_params,
                    original_text=original_text,
                    translation=translation,
                ).execute()
        except Exception as e:
            logger.debug(f"设置缓存时出错: {e}", exc_info=True)


# --- 生产环境数据库初始化 ---
def init_db(remove_exists: bool = False) -> None:
    """
    初始化生产环境数据库，并将其设置到全局代理 db_proxy
    Args:
        remove_exists: 是否删除现有数据库
    """
    cache_folder = Path.home() / ".cache" / "nex_translation"
    cache_folder.mkdir(parents=True, exist_ok=True)

    cache_db_path = cache_folder / "cache.v1.db"

    if remove_exists and cache_db_path.exists():
        try:
            cache_db_path.unlink()
            logger.info(f"已删除现有数据库: {cache_db_path}")
        except OSError as e:
            logger.error(f"删除数据库失败 {cache_db_path}: {e}")
            return  # 如果删除失败，则不继续初始化

    # 创建生产数据库实例
    prod_db = SqliteDatabase(
        str(cache_db_path),
        pragmas={
            "journal_mode": "wal",
            "busy_timeout": 1000,
        },
    )
    # 将生产数据库实例初始化到全局代理
    db_proxy.initialize(prod_db)

    # 连接并创建表（通过代理）
    try:
        if db_proxy.is_closed():  # 检查代理包装的连接是否关闭
            db_proxy.connect(reuse_if_open=True)
        db_proxy.create_tables([_TranslationCache], safe=True)
        logger.info(f"生产数据库已初始化: {cache_db_path}")
    except Exception as e:
        logger.error(f"初始化生产数据库表失败: {e}", exc_info=True)


# --- 测试环境数据库辅助函数 ---
def init_test_db() -> SqliteDatabase:
    """初始化一个临时的、唯一的测试数据库，并返回该实例"""
    import tempfile

    # 创建一个唯一的临时数据库文件名
    # delete=False 确保文件在 NamedTemporaryFile 关闭后不会立即被删除，Peewee 需要路径
    temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path_str = temp_db_file.name
    temp_db_file.close()  # 关闭文件句柄，Peewee 将重新打开它

    test_db_instance = SqliteDatabase(
        db_path_str,
        pragmas={
            "journal_mode": "wal",
            "busy_timeout": 2000,  # 稍微增加超时，以应对并发测试
        },
    )
    # 注意：这里不使用全局的 db_proxy.initialize(test_db_instance)
    # 因为我们希望测试数据库是完全隔离的，由 fixture 管理其生命周期。
    # _TranslationCache.Meta.database 仍然是 db_proxy，
    # 但在测试中，我们会将 test_db_instance 传递给 TranslationCache 实例。
    # 或者，更清洁的方式是，在测试的 fixture 中临时改变 _TranslationCache.Meta.database。
    # 但由于 TranslationCache 构造函数接受 db_instance，我们可以直接使用它。

    # 为了让 _TranslationCache 模型在测试中使用这个 test_db_instance，
    # 我们需要确保 TranslationCache 实例的 self.db 指向它。
    # Peewee 的操作（如 .get_or_none, .replace）会使用其模型 Meta.database 指定的数据库，
    # 除非在执行时显式指定了数据库。
    # 为了让测试中的 _TranslationCache 操作使用 test_db_instance，
    # 最好的方式是在测试期间动态地将模型的数据库绑定到 test_db_instance。
    # 这可以通过 Peewee 的 test_database 上下文管理器或手动设置完成。
    # 然而，由于 TranslationCache 的 get/set 方法内部使用了 self.db.connection_context()，
    # 并且 _TranslationCache.Meta.database 是 db_proxy，
    # 我们需要确保在这些方法执行时，db_proxy 指向的是 test_db_instance。
    # 或者，修改 TranslationCache 的 get/set，使其能够使用模型显式绑定到特定数据库。

    # 简单的做法：在测试的 fixture 中初始化 db_proxy 指向 test_db_instance
    # db_proxy.initialize(test_db_instance) # 这会影响全局代理，可能不适合并行测试

    # 更推荐：测试时，让 TranslationCache 的方法直接使用传入的 db_instance
    # 这已经在 TranslationCache 的 __init__ 和 get/set 中通过 self.db 实现。
    # 只要 _TranslationCache 模型在执行操作时能感知到这个 self.db 即可。
    # Peewee 的 Model 操作默认使用 Meta.database。
    # 为了让 _TranslationCache 使用 test_db_instance，
    # 我们可以在测试的 `test_db` fixture 中这样做：
    # with test_db_instance.bind_ctx([_TranslationCache]):
    #    yield test_db_instance
    # 或者，在 TranslationCache 的 get/set 中，如果 self.db 不是全局代理，
    # 而是特定的 test_db_instance，那么需要确保模型操作使用这个实例。
    # Peewee 的 `Model.select().database(specific_db)` 可以做到。

    # 当前的 TranslationCache.get/set 使用 self.db.connection_context()，
    # 这意味着它们期望 self.db 是一个 Peewee 数据库实例。
    # _TranslationCache 的操作（如 .get_or_none）会使用 _TranslationCache.Meta.database（即 db_proxy）。
    # 为了让测试隔离，我们需要在测试期间让 db_proxy 指向 test_db_instance。

    # 在 init_test_db 中，我们只创建并返回 test_db_instance。
    # 连接和表创建将在 test_db fixture 中处理，同时处理 db_proxy 的初始化。
    return test_db_instance


def clean_test_db(test_db_instance: SqliteDatabase) -> None:
    """清理测试数据库及其相关文件"""
    db_path_str = test_db_instance.database

    # 确保在尝试关闭和删除前，全局代理不再指向这个测试数据库实例
    # if db_proxy.obj == test_db_instance:
    #     db_proxy.initialize(None) # 或者指向一个空操作的数据库

    if not test_db_instance.is_closed():
        test_db_instance.close()

    # 清理主数据库文件和 WAL/SHM 文件
    for attempt in range(3):  # 重试几次以应对文件占用
        try:
            db_file = Path(db_path_str)
            wal_file = Path(db_path_str + "-wal")
            shm_file = Path(db_path_str + "-shm")

            if db_file.exists():
                db_file.unlink(missing_ok=True)  # missing_ok=True (Python 3.8+)
            if wal_file.exists():
                wal_file.unlink(missing_ok=True)
            if shm_file.exists():
                shm_file.unlink(missing_ok=True)

            # 检查是否都已删除
            if not db_file.exists() and not wal_file.exists() and not shm_file.exists():
                logger.debug(f"测试数据库文件已清理: {db_path_str}")
                break
        except PermissionError:
            if attempt < 2:
                import time

                time.sleep(0.2)  # 等待0.2秒
            else:
                logger.warning(f"清理测试数据库文件 {db_path_str} 失败 (权限错误)")
        except Exception as e:  # 捕获其他潜在错误
            logger.warning(
                f"清理测试数据库文件 {db_path_str} 时发生未知错误: {e}", exc_info=True
            )
            break  # 发生其他错误则停止重试
    else:  # for 循环正常结束（即重试次数用尽仍未成功）
        if Path(db_path_str).exists() or Path(db_path_str + "-wal").exists() or Path(db_path_str + "-shm").exists():
             logger.warning(f"重试后仍未能完全清理测试数据库文件: {db_path_str}")


# 在模块加载时初始化生产环境数据库
# init_db() # 考虑是否在模块加载时自动初始化，或者由应用主程序显式调用
# 对于库来说，通常不在导入时执行有副作用的操作（如创建文件、连接数据库）
# 最好由应用的入口点来调用 init_db()。
