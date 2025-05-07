import pytest
import json
from pathlib import Path
import tempfile  # 确保导入
from typing import Dict, Any, Optional  # 确保导入 Optional
import threading  # 确保导入
import queue  # 确保导入
import time  # 用于可能的延迟

from nex_translation.infrastructure.cache import (
    TranslationCache,
    _TranslationCache,
    init_test_db,  # 这是创建 SqliteDatabase 实例的函数
    clean_test_db,  # 这是清理文件的函数
    db_proxy  # 导入全局数据库代理
)
from peewee import SqliteDatabase  # 确保导入

# --- Fixtures ---

@pytest.fixture
def test_db_instance() -> SqliteDatabase:  # 重命名以区分，这只创建实例
    """创建一个临时的 SQLite 数据库实例，但不进行全局初始化或表创建。"""
    return init_test_db()  # init_test_db 现在只返回一个 SqliteDatabase 实例

@pytest.fixture
def test_db(test_db_instance: SqliteDatabase):  # 这个 fixture 负责连接、建表和清理
    """
    提供一个已连接并创建了表的测试数据库。
    关键：此 fixture 会将全局的 db_proxy 指向这个测试数据库实例，
    并在测试结束后恢复 db_proxy (如果需要的话) 和清理数据库文件。
    """
    original_db_proxy_obj = db_proxy.obj  # 保存原始的 db_proxy 指向的对象

    # 将全局代理指向我们的测试数据库实例
    db_proxy.initialize(test_db_instance)

    try:
        if db_proxy.is_closed():
            db_proxy.connect(reuse_if_open=True)
        db_proxy.create_tables([_TranslationCache], safe=True)
        
        yield test_db_instance  # 测试将使用这个实例（直接或通过db_proxy）
    finally:
        # 测试结束后，关闭通过代理操作的连接
        if not db_proxy.is_closed():
            db_proxy.close()
        
        # 恢复全局代理到原始状态（如果原始状态不是None）
        # 如果原始是None，或者我们不关心恢复到特定状态，可以简单地设为None或一个新的空代理
        if original_db_proxy_obj is not None:
            db_proxy.initialize(original_db_proxy_obj)
        else:
            # 如果原始是None，可能需要创建一个新的空代理或将其设为None
            # 这取决于您的应用在没有初始化数据库时的行为
            db_proxy.initialize(None) # 或者一个 DummyDatabase()
        
        # 清理测试数据库文件
        clean_test_db(test_db_instance)


@pytest.fixture
def cache_manager(test_db: SqliteDatabase):  # 依赖于上面已正确设置 db_proxy 的 test_db fixture
    """提供基本配置的缓存管理器，它将通过 db_proxy 使用测试数据库"""
    # TranslationCache 的 __init__ 现在可以不传 db_instance，
    # 它会默认使用全局的 db_proxy，而 db_proxy 在 test_db fixture 中已被设置为测试数据库。
    # 或者，为了更明确，仍然传递 test_db。
    return TranslationCache(
        translate_engine="test_engine",
        translate_engine_params={"model": "test_model"},
        db_instance=test_db # 显式传递，确保它使用注入的实例
                            # 即使 TranslationCache 内部回退到 db_proxy，
                            # db_proxy 也已经被 test_db fixture 设置了。
    )

@pytest.fixture
def sample_text():
    """提供示例文本数据"""
    return {
        "original": "Hello, world!",
        "translation": "你好，世界！"
    }

# --- 模型测试 ---

def test_translation_cache_model_constraints(test_db, cache_manager, sample_text):
    """测试翻译缓存模型的唯一性约束"""
    # 创建第一条记录
    _TranslationCache.create(
        translate_engine=cache_manager.translate_engine,
        translate_engine_params=cache_manager.translate_engine_params,
        original_text=sample_text["original"],
        translation=sample_text["translation"]
    )
    
    # 尝试创建具有相同键（引擎、参数、原文）的记录
    new_translation = "新的翻译结果"
    _TranslationCache.create(
        translate_engine=cache_manager.translate_engine,
        translate_engine_params=cache_manager.translate_engine_params,
        original_text=sample_text["original"],
        translation=new_translation
    )
    
    # 验证是否替换了旧记录
    result = _TranslationCache.get(
        translate_engine=cache_manager.translate_engine,
        translate_engine_params=cache_manager.translate_engine_params,
        original_text=sample_text["original"]
    )
    assert result.translation == new_translation
    
    # 验证只有一条记录
    count = _TranslationCache.select().count()
    assert count == 1

# --- 缓存管理器测试 ---

def test_cache_manager_init(test_db: SqliteDatabase): # 添加 test_db fixture
    """测试缓存管理器初始化"""
    cache = TranslationCache("test_init_engine", {"param": "value"}, db_instance=test_db)
    assert cache.translate_engine == "test_init_engine"
    assert cache.params == {"param": "value"}
    
    with pytest.raises(AssertionError):
        TranslationCache("engine_name_len_is_21", db_instance=test_db) # 确保这个测试用例的引擎名确实超过20
    
    # 修改 "test_no_params_engine" 使其长度不超过20
    cache_no_params = TranslationCache("test_no_params_eng", db_instance=test_db) # 例如改为 "test_no_params_eng" (18字符)
    assert cache_no_params.params == {}
    assert cache_no_params.translate_engine_params == "{}"
    assert cache_no_params.translate_engine == "test_no_params_eng" # 最好也断言一下引擎名

    cache = TranslationCache("a" * 20, db_instance=test_db)  # 20字符
    assert cache.translate_engine == "a" * 20

def test_params_management(test_db: SqliteDatabase): # 添加 test_db fixture
    """测试参数管理功能"""
    # 修改 "test_params_engine" 使其长度不超过20
    cache = TranslationCache("test_params_eng", db_instance=test_db) # 例如改为 "test_params_eng" (15字符)
    
    # 测试替换参数
    new_params = {"model": "gpt4", "temperature": 0.7}
    cache.replace_params(new_params)
    assert cache.params == new_params
    assert json.loads(cache.translate_engine_params) == new_params
    
    # 测试更新部分参数
    cache.update_params({"temperature": 0.8, "new_param": "value"})
    assert cache.params["temperature"] == 0.8
    assert cache.params["model"] == "gpt4"
    assert cache.params["new_param"] == "value"
    
    # 测试添加单个参数
    cache.add_params("max_tokens", 100)
    assert cache.params["max_tokens"] == 100

def test_cache_operations(cache_manager: TranslationCache, sample_text: Dict[str, str]): # cache_manager fixture 已注入 db
    """测试缓存的基本操作"""
    # 测试设置缓存
    cache_manager.set(sample_text["original"], sample_text["translation"])
    
    # 测试获取缓存
    result = cache_manager.get(sample_text["original"])
    assert result == sample_text["translation"]
    
    # 测试获取不存在的缓存
    result = cache_manager.get("不存在的文本")
    assert result is None
    
    # 测试更新已存在的缓存
    new_translation = "新的翻译"
    cache_manager.set(sample_text["original"], new_translation)
    result = cache_manager.get(sample_text["original"])
    assert result == new_translation

def test_dict_sorting():
    """测试字典排序功能"""
    # 修改 "test" 使其长度不超过20 (虽然 "test" 已经符合，但为了统一性检查所有实例化的地方)
    # 如果 TranslationCache 的 __init__ 确实需要 db_instance (根据您之前的修改，它现在是可选的，但会回退到 db_proxy)
    # 为了测试 _sort_dict_recursively 的纯逻辑，可以不提供 db_instance，
    # 或者提供一个 mock/dummy db_instance，或者确保它能正确处理 db_instance=None 的情况。
    # 假设您的 TranslationCache 在 db_instance=None 时能正常工作（例如，回退到全局代理或不执行数据库操作）
    # 或者，如果 _sort_dict_recursively 确实是静态的，可以直接通过类名调用。
    # 根据您 cache.py 中的代码，_sort_dict_recursively 是 @staticmethod
    # 所以可以直接调用： TranslationCache._sort_dict_recursively(dict1)

    # 测试普通字典
    dict1 = {"b": 2, "a": 1}
    dict2 = {"a": 1, "b": 2}
    sorted1 = TranslationCache._sort_dict_recursively(dict1) # 通过类名调用静态方法
    sorted2 = TranslationCache._sort_dict_recursively(dict2)
    assert json.dumps(sorted1) == json.dumps(sorted2)
    
    # 测试嵌套字典
    nested1 = {"b": {"y": 2, "x": 1}, "a": [1, 2]}
    nested2 = {"a": [1, 2], "b": {"x": 1, "y": 2}}
    sorted1 = TranslationCache._sort_dict_recursively(nested1)
    sorted2 = TranslationCache._sort_dict_recursively(nested2)
    assert json.dumps(sorted1) == json.dumps(sorted2)

# --- 数据库操作测试 ---

def test_db_initialization(test_db: SqliteDatabase): # test_db fixture 负责初始化
    """测试数据库初始化"""
    tables = test_db.get_tables() # 直接对 test_db 实例操作
    assert "_translationcache" in tables 
    assert not test_db.is_closed()
    
    cursor = test_db.execute_sql("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == "wal"

# test_db_cleanup 不再需要，因为 clean_test_db 由 test_db fixture 的 teardown 调用

# --- 并发和错误处理测试 ---
def test_concurrent_access(test_db: SqliteDatabase): # 依赖 test_db fixture
    """测试并发访问"""
    results = queue.Queue()
    # TranslationCache 实例现在通过 test_db fixture 间接使用正确的数据库
    # 或者显式传递 test_db
    # 修改 "test_concurrent_engine" 使其长度不超过20
    cache = TranslationCache("test_concurrent_eng", db_instance=test_db) # 例如改为 "test_concurrent_eng" (19字符)
    
    def worker(text: str, translation_val: str):
        try:
            # cache 实例现在使用注入的 test_db，并通过 connection_context 管理连接
            cache.set(text, translation_val)
            retrieved = cache.get(text)
            results.put((text, retrieved)) # 将 text 和获取到的结果放入队列
        except Exception as e:
            # 将异常放入队列，以便主线程可以检查
            results.put(e) 
    
    threads = []
    test_data = [
        (f"concurrent_text_{i}", f"concurrent_translation_{i}") for i in range(5) # 增加数据量
    ]
    
    for text, translation_val in test_data:
        thread = threading.Thread(
            target=worker,
            args=(text, translation_val)
        )
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    success_count = 0
    for _ in range(len(test_data)): # 确保从队列中获取所有结果
        result_item = results.get(timeout=1) # 添加超时以防死锁
        assert not isinstance(result_item, Exception), f"工作线程发生错误: {result_item}"
        assert isinstance(result_item, tuple), f"结果格式错误: {result_item}"
        
        text_res, translation_res = result_item
        # 查找原始数据中对应的翻译
        expected_translation = next((tr for t, tr in test_data if t == text_res), None)
        assert translation_res == expected_translation, \
            f"并发测试中获取的值与设置的值不匹配: 原文='{text_res}', 获取='{translation_res}', 期望='{expected_translation}'"
        success_count +=1
    
    assert success_count == len(test_data), "并非所有并发操作都成功返回了预期的结果"


def test_error_handling(test_db: SqliteDatabase, cache_manager: TranslationCache): # 依赖 fixture
    """测试错误处理"""
    # 测试无效的JSON参数 (这个与数据库无关，可以直接测试 TranslationCache 的方法)
    # 修改 "json_test_engine" 使其长度不超过20
    temp_cache_for_json_test = TranslationCache("json_test_eng", db_instance=test_db) # 例如改为 "json_test_eng" (13字符)
    with pytest.raises(TypeError): # json.dumps 会对不可序列化对象抛 TypeError
        temp_cache_for_json_test.replace_params({"key": object()}) 
    
    # 测试数据库错误 (例如连接已关闭)
    # cache_manager 使用的 test_db 是由 fixture 管理的
    # 我们需要模拟 test_db 关闭的情况
    
    # 先确保 cache_manager 中的 db 是我们期望的 test_db
    assert cache_manager.db == test_db

    if not test_db.is_closed():
        test_db.close() # 关闭由 fixture 提供的数据库连接
    
    # 此时，cache_manager.get 内部的 self.db.connection_context() 应该会失败
    # 或者 Peewee 可能会尝试重新打开它。我们需要验证其行为。
    # 根据 TranslationCache.get 的实现，它会捕获异常并返回 None
    result = cache_manager.get("some_text_after_db_close")
    assert result is None, "数据库关闭后，get 操作应安全失败并返回 None"
    
    # 为了不影响其他测试，重新连接数据库（尽管 fixture 的 teardown 会处理关闭和清理）
    # 但由于我们在这里显式关闭了它，如果后续有操作依赖它，最好重新打开
    if test_db.is_closed():
        test_db.connect(reuse_if_open=True)

def test_clean_test_db(tmp_path):
    db_path = tmp_path / "test.db"
    wal_path = tmp_path / "test.db-wal"
    shm_path = tmp_path / "test.db-shm"
    
    db_path.write_text("")
    wal_path.write_text("")
    shm_path.write_text("")
    
    test_db = SqliteDatabase(str(db_path))
    clean_test_db(test_db)
    
    assert not db_path.exists()
    assert not wal_path.exists()
    assert not shm_path.exists()