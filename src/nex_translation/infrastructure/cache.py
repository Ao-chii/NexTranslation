import logging
import json
from pathlib import Path
from typing import Optional, Any, Dict
from peewee import Model, SqliteDatabase, AutoField, CharField, TextField, SQL
from ..utils.logger import get_logger

# 配置日志记录器
logger = get_logger(__name__)

# 初始化数据库连接（延迟初始化）
db = SqliteDatabase(None)

class _TranslationCache(Model):
    """翻译缓存数据模型"""
    id = AutoField()
    translate_engine = CharField(max_length=20)  # 翻译引擎名称
    translate_engine_params = TextField()        # 翻译参数（JSON格式）
    original_text = TextField()                  # 原始文本
    translation = TextField()                    # 翻译结果

    class Meta:
        database = db
        # 使用联合唯一约束，确保相同条件下的翻译只存储一次
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
    def __init__(self, translate_engine: str = "", translate_engine_params: Dict[str, Any] = None):
        """
        初始化缓存管理器
        Args:
            translate_engine: 翻译引擎名称
            translate_engine_params: 翻译引擎参数
        """
        assert len(translate_engine) < 20, "翻译引擎名称不能超过20个字符"
        self.translate_engine = translate_engine
        self.params = {}
        self.replace_params(translate_engine_params)

    @staticmethod
    def _sort_dict_recursively(obj: Any) -> Any:
        """递归排序字典，确保相同内容的字典具有相同的字符串表示"""
        if isinstance(obj, dict):
            return {
                k: TranslationCache._sort_dict_recursively(v)
                for k in sorted(obj.keys())
                for v in [obj[k]]
            }
        elif isinstance(obj, list):
            return [TranslationCache._sort_dict_recursively(item) for item in obj]
        return obj

    def replace_params(self, params: Optional[Dict[str, Any]] = None) -> None:
        """替换所有参数"""
        if params is None:
            params = {}
        self.params = params
        params = self._sort_dict_recursively(params)
        self.translate_engine_params = json.dumps(params)

    def update_params(self, params: Optional[Dict[str, Any]] = None) -> None:
        """更新部分参数"""
        if params is None:
            params = {}
        self.params.update(params)
        self.replace_params(self.params)

    def add_params(self, key: str, value: Any) -> None:
        """添加单个参数"""
        self.params[key] = value
        self.replace_params(self.params)

    def get(self, original_text: str) -> Optional[str]:
        """获取缓存的翻译结果"""
        try:
            result = _TranslationCache.get_or_none(
                translate_engine=self.translate_engine,
                translate_engine_params=self.translate_engine_params,
                original_text=original_text,
            )
            return result.translation if result else None
        except Exception as e:
            logger.debug(f"获取缓存时出错: {e}")
            return None

    def set(self, original_text: str, translation: str) -> None:
        """设置翻译缓存"""
        try:
            _TranslationCache.create(
                translate_engine=self.translate_engine,
                translate_engine_params=self.translate_engine_params,
                original_text=original_text,
                translation=translation,
            )
        except Exception as e:
            logger.debug(f"设置缓存时出错: {e}")

def init_db(remove_exists: bool = False) -> None:
    """
    初始化数据库
    Args:
        remove_exists: 是否删除现有数据库
    """
    cache_folder = Path.home() / ".cache" / "nex_translation"
    cache_folder.mkdir(parents=True, exist_ok=True)
    
    # 添加版本号以支持未来的数据库迁移
    cache_db_path = cache_folder / "cache.v1.db"
    
    if remove_exists and cache_db_path.exists():
        cache_db_path.unlink()
    
    db.init(
        str(cache_db_path),
        pragmas={
            "journal_mode": "wal",  # 启用WAL模式提高并发性能
            "busy_timeout": 1000,   # 设置忙等待超时
        },
    )
    
    db.create_tables([_TranslationCache], safe=True)

def init_test_db():
    """初始化测试数据库"""
    import tempfile
    
    cache_db_path = tempfile.mktemp(suffix=".db")
    test_db = SqliteDatabase(
        cache_db_path,
        pragmas={
            "journal_mode": "wal",
            "busy_timeout": 1000,
        },
    )
    test_db.bind([_TranslationCache], bind_refs=False, bind_backrefs=False)
    test_db.connect()
    test_db.create_tables([_TranslationCache], safe=True)
    return test_db

def clean_test_db(test_db: SqliteDatabase) -> None:
    """清理测试数据库"""
    test_db.drop_tables([_TranslationCache])
    test_db.close()
    
    # 清理所有相关文件
    db_path = Path(test_db.database)
    if db_path.exists():
        db_path.unlink()
    
    # 清理WAL和SHM文件
    for suffix in ["-wal", "-shm"]:
        wal_path = Path(str(db_path) + suffix)
        if wal_path.exists():
            wal_path.unlink()

# 初始化生产环境数据库
init_db()
