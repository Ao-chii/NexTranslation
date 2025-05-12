import pytest
import tempfile
import json
from pathlib import Path
import shutil 
import threading

from nex_translation.infrastructure.config import ConfigManager

# --- Fixtures ---

@pytest.fixture
def default_config_dir(monkeypatch):
    """创建一个临时目录作为 Path.home() / '.config' / 'NexTranslation' 的模拟"""
    temp_dir_base = Path(tempfile.mkdtemp()) # 作为模拟的 Path.home()
    
    # ConfigManager 内部会创建 .config/NexTranslation 子目录
    # 所以我们只需要模拟 Path.home()
    
    original_home = Path.home
    def mock_home():
        return temp_dir_base

    monkeypatch.setattr(Path, 'home', mock_home)
    
    # 返回 ConfigManager 将会使用的完整配置目录路径，用于断言
    yield temp_dir_base / ".config" / "NexTranslation"

    monkeypatch.setattr(Path, 'home', original_home) # 恢复
    shutil.rmtree(temp_dir_base) # 清理整个模拟的 home 目录


@pytest.fixture
def temp_config_file_path(default_config_dir):
    """提供在模拟的 default_config_dir 中的 config.json 的路径。"""
    return default_config_dir / "config.json"

@pytest.fixture
def initial_config_data():
    """定义一份初始配置数据，用于测试加载和读取。"""
    return {
        "translators": [
            {"name": "google", "envs": {}},
            {"name": "openai", "envs": {"OPENAI_API_KEY": "initial_openai_key", "OPENAI_MODEL": "gpt-3.5-turbo"}},
            {"name": "deepl", "envs": {"DEEPL_API_KEY": "initial_deepl_key"}}
        ],
        "ENABLED_SERVICES": ["google", "openai", "deepl"],
        "DEFAULT_SERVICE": "google"
    }

@pytest.fixture
def populated_config_file(temp_config_file_path, initial_config_data):
    """在预期的默认位置使用 initial_config_data 创建一个配置文件。"""
    # 确保父目录存在，因为 ConfigManager._ensure_config_exists 也会这样做
    temp_config_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_config_file_path, 'w', encoding='utf-8') as f:
        json.dump(initial_config_data, f, indent=4)
    return temp_config_file_path

@pytest.fixture(autouse=True)
def reset_config_manager_singleton():
    """确保 ConfigManager 单例在每个测试前被重置。"""
    ConfigManager._instance = None
    # 如果 ConfigManager 有 _initialized 标志来防止重复初始化，也应重置
    if hasattr(ConfigManager, "_initialized"):
        # 直接设置私有属性以重置状态
        setattr(ConfigManager, "_initialized", False)


# --- Test Functions ---

def test_config_singleton(default_config_dir): # default_config_dir 确保环境已设置
    """测试ConfigManager是否正确实现单例模式"""
    config1 = ConfigManager.get_instance()
    config2 = ConfigManager.get_instance()
    assert config1 is config2
    assert isinstance(config1, ConfigManager)

def test_default_config_creation(default_config_dir, temp_config_file_path):
    """测试首次运行时是否创建默认配置文件"""
    assert not temp_config_file_path.exists(), "配置文件不应预先存在"

    config = ConfigManager.get_instance() # 这将触发 _ensure_config_exists
    
    assert temp_config_file_path.exists(), "默认配置文件应已创建"
    
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    assert "translators" in data
    assert len(data["translators"]) == 3 # google, openai, deepl
    translator_names = {t["name"] for t in data["translators"]}
    assert "google" in translator_names
    assert "openai" in translator_names
    assert "deepl" in translator_names
    
    # 检查 OpenAI 和 DeepL 的默认 envs 是否存在且为空字符串
    openai_envs = next(t["envs"] for t in data["translators"] if t["name"] == "openai")
    assert openai_envs.get("OPENAI_API_KEY") == ""
    assert openai_envs.get("OPENAI_MODEL") == "gpt-4" # 根据 config.py 默认值
    
    deepl_envs = next(t["envs"] for t in data["translators"] if t["name"] == "deepl")
    assert deepl_envs.get("DEEPL_API_KEY") == ""

    assert data["ENABLED_SERVICES"] == ["google", "openai", "deepl"] # 根据 config.py 默认值
    assert data["DEFAULT_SERVICE"] == "google" # 根据 config.py 默认值

def test_loading_existing_config(populated_config_file, initial_config_data):
    """测试是否正确加载已存在的配置文件"""
    config = ConfigManager.get_instance()
    
    expected_default_service = ConfigManager.normalize_service_name(initial_config_data["DEFAULT_SERVICE"])
    assert config.get_default_service() == expected_default_service
    
    expected_enabled_services = sorted([ConfigManager.normalize_service_name(s) for s in initial_config_data["ENABLED_SERVICES"]])
    assert sorted(config.get_enabled_services()) == expected_enabled_services
    
    openai_config_expected = initial_config_data["translators"][1]["envs"]
    assert config.get_translator_config("openai") == openai_config_expected

def test_normalize_service_name():
    """测试服务名称规范化"""
    assert ConfigManager.normalize_service_name("Google") == "google"
    assert ConfigManager.normalize_service_name("  openai  ") == "openai"
    assert ConfigManager.normalize_service_name("DeeplTranslator") == "deepltranslator"
    assert ConfigManager.normalize_service_name("google") == "google"

def test_get_translator_config(populated_config_file, initial_config_data):
    """测试获取翻译器配置"""
    config = ConfigManager.get_instance()

    openai_envs_expected = initial_config_data["translators"][1]["envs"]
    assert config.get_translator_config("OpenAI") == openai_envs_expected, "应不区分大小写"
    assert config.get_translator_config("  openai  ") == openai_envs_expected, "应去除首尾空格"
    
    google_envs_expected = initial_config_data["translators"][0]["envs"]
    assert config.get_translator_config("google") == google_envs_expected
    
    assert config.get_translator_config("nonexistent_service") == {}, "不存在的服务应返回空字典"

def test_get_default_service(populated_config_file, initial_config_data, temp_config_file_path):
    """测试获取默认翻译服务，包括回退机制"""
    config = ConfigManager.get_instance()
    expected_default = ConfigManager.normalize_service_name(initial_config_data["DEFAULT_SERVICE"])
    assert config.get_default_service() == expected_default

    # 测试当 DEFAULT_SERVICE 键从配置文件中移除时
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    del data["DEFAULT_SERVICE"] # 移除键
    with open(temp_config_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    
    # reset_config_manager_singleton() # <--- 移除这一行
    # 由于 reset_config_manager_singleton 是 autouse=True 的 fixture，
    # 它会在每个测试函数开始前自动运行。
    # 为了测试重新加载，我们需要确保 ConfigManager 的单例被清除，
    # 这样下一次 get_instance() 就会重新初始化。
    # reset_config_manager_singleton fixture 已经做了这个工作。
    # 我们需要的是在修改文件后，再次获取实例。
    # 但由于 fixture 在函数开始时运行，我们需要一种方式在函数中间“重置”。
    # 最简单的方法是直接操作 ConfigManager 的类属性，模拟 fixture 的行为。
    ConfigManager._instance = None
    if hasattr(ConfigManager, "_initialized"):
        setattr(ConfigManager, "_initialized", False)

    config_reloaded = ConfigManager.get_instance() # 这会触发重新初始化和加载
    assert config_reloaded.get_default_service() == "google", "缺少 DEFAULT_SERVICE 时应回退到 'google'"

def test_get_enabled_services(populated_config_file, initial_config_data, temp_config_file_path):
    """测试获取启用的翻译服务列表，包括回退机制"""
    config = ConfigManager.get_instance()
    expected_enabled = sorted([ConfigManager.normalize_service_name(s) for s in initial_config_data["ENABLED_SERVICES"]])
    assert sorted(config.get_enabled_services()) == expected_enabled

    # 测试当 ENABLED_SERVICES 键从配置文件中移除时
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    del data["ENABLED_SERVICES"] # 移除键
    with open(temp_config_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    # reset_config_manager_singleton() # <--- 移除这一行
    ConfigManager._instance = None
    if hasattr(ConfigManager, "_initialized"):
        setattr(ConfigManager, "_initialized", False)
        
    config_reloaded = ConfigManager.get_instance() # 这会触发重新初始化和加载
    assert config_reloaded.get_enabled_services() == ["google"], "缺少 ENABLED_SERVICES 时应回退到 ['google']"

def test_update_translator_config_existing(populated_config_file, temp_config_file_path):
    """测试更新已存在的翻译器配置"""
    config = ConfigManager.get_instance()
    
    new_openai_envs = {"OPENAI_API_KEY": "new_key_for_openai_test", "OPENAI_MODEL": "gpt-4-turbo-preview"}
    config.update_translator_config("OpenAI", new_openai_envs) # 测试不区分大小写更新
    
    assert config.get_translator_config("openai") == new_openai_envs
    
    # 验证文件是否已持久化更改
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    updated_translator_data = next(t for t in file_data["translators"] if ConfigManager.normalize_service_name(t["name"]) == "openai")
    assert updated_translator_data["envs"] == new_openai_envs

def test_update_translator_config_new(populated_config_file, temp_config_file_path):
    """测试添加新的翻译器配置"""
    config = ConfigManager.get_instance()
    
    new_service_name = "MyCustomTranslator"
    new_service_envs = {"CUSTOM_API_URL": "http://example.com/api", "AUTH_TOKEN": "my_secret_token"}
    config.update_translator_config(new_service_name, new_service_envs)
    
    normalized_new_name = ConfigManager.normalize_service_name(new_service_name)
    assert config.get_translator_config(new_service_name) == new_service_envs
    assert config.get_translator_config(normalized_new_name) == new_service_envs
    
    # 验证文件是否已持久化更改
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    
    added_translator_data = next(t for t in file_data["translators"] if ConfigManager.normalize_service_name(t["name"]) == normalized_new_name)
    assert added_translator_data["envs"] == new_service_envs

def test_set_default_service(populated_config_file, temp_config_file_path):
    """测试设置默认翻译服务"""
    config = ConfigManager.get_instance()
    
    new_default_service = "deepl"
    config.set_default_service(new_default_service) # set_default_service 内部不进行规范化
    
    assert config.get_default_service() == ConfigManager.normalize_service_name(new_default_service) # get_default_service 会规范化
    
    # 验证文件是否已持久化更改
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    # config.py 的 _save_config 保存的是用户传入的原始 service_name
    assert file_data["DEFAULT_SERVICE"] == new_default_service 

    # 测试使用不同大小写设置
    config.set_default_service("Google")
    assert config.get_default_service() == "google" 
    with open(temp_config_file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    assert file_data["DEFAULT_SERVICE"] == "Google"

def test_concurrent_access_singleton(default_config_dir): # default_config_dir 确保环境已设置
    """测试多线程环境下单例的获取"""
    instances_set = set()
    thread_lock = threading.Lock()

    def worker_get_instance():
        instance = ConfigManager.get_instance()
        with thread_lock:
            instances_set.add(instance)

    threads_list = [threading.Thread(target=worker_get_instance) for _ in range(10)]
    for t in threads_list:
        t.start()
    for t in threads_list:
        t.join()
    
    assert len(instances_set) == 1, "所有线程应获取到同一个 ConfigManager 实例"

def test_config_file_not_found_error(monkeypatch): # 更准确的名称应该是 test_invalid_config_file_causes_decode_error
    """测试当配置文件内容无效时是否抛出 JSONDecodeError"""
    temp_dir_base = Path(tempfile.mkdtemp())
    
    # 模拟 Path.home() 以确保 ConfigManager 使用我们的临时目录
    original_home = Path.home
    def mock_home_for_error():
        return temp_dir_base
    monkeypatch.setattr(Path, 'home', mock_home_for_error)

    # 获取 ConfigManager 将使用的配置路径
    # ConfigManager 内部会创建 .config/NexTranslation
    config_dir = temp_dir_base / ".config" / "NexTranslation"
    config_dir.mkdir(parents=True, exist_ok=True)
    invalid_config_file = config_dir / "config.json"

    # 创建一个内容无效的 JSON 文件
    with open(invalid_config_file, "w", encoding='utf-8') as f:
        f.write("this is not valid json {") # 无效的 JSON

    # 重置 ConfigManager 单例，以便下次 get_instance 时重新初始化
    ConfigManager._instance = None
    if hasattr(ConfigManager, "_initialized"):
        setattr(ConfigManager, "_initialized", False)

    # 当 ConfigManager.get_instance() 被调用时，
    # 它会执行 __init__ -> _ensure_config_exists -> _load_config
    # _load_config 应该会因为无效的 JSON 而抛出 JSONDecodeError
    with pytest.raises(json.JSONDecodeError):
        ConfigManager.get_instance()

    # 清理
    monkeypatch.setattr(Path, 'home', original_home)
    shutil.rmtree(temp_dir_base)