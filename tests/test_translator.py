import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from string import Template
import os
import json
import requests # 确保导入
from pathlib import Path

from nex_translation.core.translator import BaseTranslator
from nex_translation.core.google_translator import GoogleTranslator
from nex_translation.infrastructure.config import ConfigManager # 确保导入
from nex_translation.infrastructure.cache import TranslationCache, init_db, db_proxy, _TranslationCache # 确保导入
from nex_translation.utils.exceptions import TranslationError # 确保导入

# 在测试开始前初始化数据库
@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """初始化测试数据库"""
    # 使用临时目录作为测试数据库位置
    import tempfile
    test_db_dir = tempfile.mkdtemp()
    test_db_path = Path(test_db_dir) / "test_cache.db"

    # 创建测试数据库
    from peewee import SqliteDatabase
    test_db = SqliteDatabase(
        str(test_db_path),
        pragmas={
            "journal_mode": "wal",
            "busy_timeout": 1000,
        },
    )

    # 初始化数据库代理
    db_proxy.initialize(test_db)

    # 创建表
    with db_proxy.connection_context():
        db_proxy.create_tables([_TranslationCache], safe=True)

    yield

    # 清理
    if not test_db.is_closed():
        test_db.close()

    # 删除测试数据库文件
    if test_db_path.exists():
        test_db_path.unlink(missing_ok=True)
    if (test_db_path.parent / f"{test_db_path.name}-wal").exists():
        (test_db_path.parent / f"{test_db_path.name}-wal").unlink(missing_ok=True)
    if (test_db_path.parent / f"{test_db_path.name}-shm").exists():
        (test_db_path.parent / f"{test_db_path.name}-shm").unlink(missing_ok=True)

@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager.get_instance()"""
    with patch('nex_translation.infrastructure.config.ConfigManager.get_instance') as mock_get_instance:
        mock_instance = MagicMock()
        mock_instance.get_translator_config.return_value = {} # 默认不返回任何配置
        mock_instance.update_translator_config.return_value = None
        mock_get_instance.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_translation_cache():
    """Mock TranslationCache"""
    # 使用 MagicMock 创建一个模拟的缓存实例
    mock_cache = MagicMock()
    mock_cache.get.return_value = None  # 默认缓存未命中
    mock_cache.set.return_value = None
    mock_cache.add_params.return_value = None

    # 替换 TranslationCache 类，使其返回我们的模拟实例
    with patch('nex_translation.core.translator.TranslationCache', return_value=mock_cache):
        yield mock_cache


# --- Test BaseTranslator ---

class ConcreteTranslator(BaseTranslator):
    """用于测试 BaseTranslator 的具体子类"""
    name = "concrete_test"
    envs = {"API_KEY": "default_concrete_key", "ENDPOINT": "default_concrete_endpoint"}
    CustomPrompt = True # 假设这个测试翻译器支持自定义提示

    def do_translate(self, text: str) -> str:
        return f"Translated by Concrete: {text}"

def test_base_translator_initialization(mock_translation_cache, mock_config_manager):
    """测试 BaseTranslator 初始化"""
    translator = ConcreteTranslator(model="test_model_base", ignore_cache=True)
    assert translator.name == "concrete_test"
    assert translator.model == "test_model_base"
    assert translator.lang_in == "en"
    assert translator.lang_out == "zh"
    assert translator.ignore_cache is True
    assert translator.cache == mock_translation_cache # 验证使用了 mock 的 cache
    assert translator.prompt_template is None
    mock_config_manager.get_translator_config.assert_called_with("concrete_test")


def test_base_translator_set_envs_priority(mock_config_manager, mock_translation_cache):
    """测试 BaseTranslator.set_envs 的优先级和更新逻辑"""
    # 1. 类默认值
    translator = ConcreteTranslator()
    assert translator.envs["API_KEY"] == "default_concrete_key"

    # 2. 配置文件覆盖类默认
    mock_config_manager.get_translator_config.return_value = {"API_KEY": "config_key"}
    translator_config = ConcreteTranslator()
    assert translator_config.envs["API_KEY"] == "config_key"
    assert translator_config.envs["ENDPOINT"] == "default_concrete_endpoint" # 未被覆盖的应保留

    # 3. 环境变量覆盖配置文件和类默认
    with patch.dict(os.environ, {"API_KEY": "env_key", "ENDPOINT": "env_endpoint"}):
        mock_config_manager.get_translator_config.return_value = {"API_KEY": "config_key_for_env_test"}
        translator_env = ConcreteTranslator()
        assert translator_env.envs["API_KEY"] == "env_key"
        assert translator_env.envs["ENDPOINT"] == "env_endpoint"
        # 验证是否尝试更新配置（因为环境变量与配置文件不同）
        mock_config_manager.update_translator_config.assert_any_call(
            "concrete_test", {"API_KEY": "env_key", "ENDPOINT": "env_endpoint"}
        )

    mock_config_manager.update_translator_config.reset_mock() # 重置 mock 调用记录

    # 4. 构造函数传入的 envs 具有最高优先级，并触发配置更新
    mock_config_manager.get_translator_config.return_value = {"API_KEY": "config_key_for_init_test"}
    with patch.dict(os.environ, {"ENDPOINT": "env_key_for_init_test"}):
        init_envs = {"API_KEY": "init_override_key", "NEW_PARAM": "init_new_value"}
        translator_init = ConcreteTranslator(envs=init_envs)
        assert translator_init.envs["API_KEY"] == "init_override_key" # init 覆盖 config
        assert translator_init.envs["ENDPOINT"] == "env_key_for_init_test" # env 覆盖 default
        assert translator_init.envs["NEW_PARAM"] == "init_new_value"
        # 验证构造函数传入的 envs 触发了 update_translator_config
        # 最终的 envs 会合并所有来源，然后用传入的 envs 更新
        expected_envs_after_init = {
            "API_KEY": "init_override_key", # init 覆盖 config
            "ENDPOINT": "env_key_for_init_test", # env 覆盖 default
            "NEW_PARAM": "init_new_value" # init 新增
        }
        mock_config_manager.update_translator_config.assert_any_call(
            "concrete_test", expected_envs_after_init
        )

def test_base_translator_add_cache_impact_parameters(mock_translation_cache, mock_config_manager):
    """测试添加影响缓存的参数"""
    translator = ConcreteTranslator()
    # 使用可序列化的值而不是 MagicMock
    translator.add_cache_impact_parameters("param1", "value1")
    mock_translation_cache.add_params.assert_called_once_with("param1", "value1")

def test_base_translator_translate_logic(mock_translation_cache, mock_config_manager):
    """测试 BaseTranslator.translate 的缓存和调用逻辑"""
    translator = ConcreteTranslator() # ignore_cache 默认为 False

    # 场景1: 缓存命中
    mock_translation_cache.get.return_value = "你好 (来自缓存)"
    result = translator.translate("Hello")
    assert result == "你好 (来自缓存)"
    mock_translation_cache.get.assert_called_once_with("Hello")
    mock_translation_cache.set.assert_not_called() # 缓存命中，不应调用 set

    mock_translation_cache.reset_mock()

    # 场景2: 缓存未命中
    mock_translation_cache.get.return_value = None
    with patch.object(translator, 'do_translate', return_value="Translated by Concrete: Hello") as mock_do_translate:
        result = translator.translate("Hello")
        assert result == "Translated by Concrete: Hello"
        mock_translation_cache.get.assert_called_once_with("Hello")
        mock_do_translate.assert_called_once_with("Hello")
        mock_translation_cache.set.assert_called_once_with("Hello", "Translated by Concrete: Hello")

    mock_translation_cache.reset_mock()

    # 场景3: ignore_cache=True (通过 translate 方法参数)
    mock_translation_cache.get.return_value = "你好 (来自缓存)" # 即使缓存存在
    with patch.object(translator, 'do_translate', return_value="Translated by Concrete: Hello Ignore") as mock_do_translate:
        result = translator.translate("Hello Ignore", ignore_cache=True)
        assert result == "Translated by Concrete: Hello Ignore"
        mock_translation_cache.get.assert_not_called() # 不应检查缓存
        mock_do_translate.assert_called_once_with("Hello Ignore")
        mock_translation_cache.set.assert_called_once_with("Hello Ignore", "Translated by Concrete: Hello Ignore")

    mock_translation_cache.reset_mock()

    # 场景4: self.ignore_cache=True (通过构造函数)
    translator_ignore_init = ConcreteTranslator(ignore_cache=True)
    mock_translation_cache.get.return_value = "你好 (来自缓存)" # 即使缓存存在
    with patch.object(translator_ignore_init, 'do_translate', return_value="Translated by Concrete: Hello InitIgnore") as mock_do_translate:
        result = translator_ignore_init.translate("Hello InitIgnore")
        assert result == "Translated by Concrete: Hello InitIgnore"
        mock_translation_cache.get.assert_not_called()
        mock_do_translate.assert_called_once_with("Hello InitIgnore")
        mock_translation_cache.set.assert_called_once_with("Hello InitIgnore", "Translated by Concrete: Hello InitIgnore")


def test_base_translator_prompt_generation(mock_translation_cache, mock_config_manager):
    """测试 BaseTranslator.prompt 的提示生成"""
    translator = ConcreteTranslator()

    # 测试默认提示
    prompts = translator.prompt("Test text for prompt")
    assert len(prompts) == 1
    assert prompts[0]["role"] == "user"
    assert "Test text for prompt" in prompts[0]["content"]
    assert "你是一个专业的英译中翻译引擎" in prompts[0]["content"]

    # 测试自定义提示
    custom_template_str = "Custom prompt for $text with model $model"
    custom_template = Template(custom_template_str)
    # 假设 translator.model 已经被设置
    translator.model = "gpt-test"

    custom_prompts = translator.prompt("Custom test text", prompt_template=custom_template)
    assert len(custom_prompts) == 1
    assert custom_prompts[0]["role"] == "user"
    # Template.safe_substitute 不会替换 $model 如果它不在字典中
    # BaseTranslator.prompt 的实现只替换了 text
    expected_custom_content = custom_template.safe_substitute({"text": "Custom test text"})
    assert custom_prompts[0]["content"] == expected_custom_content

    # 测试无效模板（例如，Template 实例本身是 None，或格式错误导致 safe_substitute 异常）
    # BaseTranslator.prompt 内部有 try-except，会回退到默认提示
    with patch('string.Template.safe_substitute', side_effect=Exception("Template error")):
        prompts_fallback = translator.prompt("Fallback test")
        assert "Fallback test" in prompts_fallback[0]["content"]
        assert "你是一个专业的英译中翻译引擎" in prompts_fallback[0]["content"]


def test_base_translator_str_method(mock_translation_cache, mock_config_manager):
    """测试 BaseTranslator.__str__"""
    translator = ConcreteTranslator(model="model_for_str")
    assert str(translator) == "concrete_test model_for_str"

    translator_no_model = ConcreteTranslator()
    assert str(translator_no_model) == "concrete_test " # model 为空字符串


# --- Test GoogleTranslator ---

@pytest.fixture
def mock_requests_session():
    """Mock requests.Session for GoogleTranslator"""
    with patch('requests.Session') as mock_session_constructor:
        mock_session_instance = MagicMock()
        mock_session_constructor.return_value = mock_session_instance
        yield mock_session_instance

def test_google_translator_initialization(mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator 初始化"""
    translator = GoogleTranslator(model="google_model")
    assert translator.name == "google"
    assert translator.model == "google_model"
    assert translator.endpoint == "https://translate.google.com/m"
    assert "User-Agent" in translator.headers
    assert translator.session == mock_requests_session # 验证使用了 mock 的 session
    mock_requests_session.headers.update.assert_not_called() # headers 是在实例上设置的，不是 session


@patch('nex_translation.core.google_translator.html.unescape') # Mock html.unescape
def test_google_translator_do_translate_success(mock_unescape, mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate 成功场景"""
    translator = GoogleTranslator()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '<div class="result-container">Translated Text</div>'
    mock_requests_session.get.return_value = mock_response

    mock_unescape.return_value = "Translated Text" # html.unescape 的返回值

    result = translator.do_translate("Hello Google")

    assert result == "Translated Text"
    mock_requests_session.get.assert_called_once_with(
        translator.endpoint,
        params={"tl": "zh", "sl": "en", "q": "Hello Google"},
        headers=translator.headers,
        timeout=30
    )
    mock_unescape.assert_called_once_with("Translated Text")


def test_google_translator_do_translate_text_too_long(mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate 文本过长"""
    translator = GoogleTranslator()
    long_text = "a" * 5001
    with pytest.raises(TranslationError, match="Text too long"):
        translator.do_translate(long_text)
    mock_requests_session.get.assert_not_called()


def test_google_translator_do_translate_api_error_400(mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate API 返回 400 错误"""
    translator = GoogleTranslator()
    mock_response = MagicMock()
    mock_response.status_code = 400
    # mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error") # 可选，如果内部调用了
    mock_requests_session.get.return_value = mock_response

    with pytest.raises(TranslationError, match="Google Translate API error"):
        translator.do_translate("Test 400")


def test_google_translator_do_translate_request_exception(mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate 请求失败"""
    translator = GoogleTranslator()
    mock_requests_session.get.side_effect = requests.exceptions.Timeout("Connection timed out")

    with pytest.raises(TranslationError, match="Request failed: Connection timed out"):
        translator.do_translate("Test Timeout")


def test_google_translator_do_translate_failed_extraction(mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate 无法提取翻译结果"""
    translator = GoogleTranslator()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '<div>No result-container class here</div>' # 不匹配的响应文本
    mock_requests_session.get.return_value = mock_response

    with pytest.raises(TranslationError, match="Failed to extract translation result"):
        translator.do_translate("Test Extraction Fail")


@patch('nex_translation.core.google_translator.re.findall') # Mock re.findall
def test_google_translator_do_translate_unexpected_error(mock_re_findall, mock_requests_session, mock_translation_cache, mock_config_manager):
    """测试 GoogleTranslator.do_translate 内部发生其他异常"""
    translator = GoogleTranslator()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '<div class="result-container">Some Text</div>'
    mock_requests_session.get.return_value = mock_response

    mock_re_findall.side_effect = Exception("Unexpected regex error") # 模拟 re.findall 抛出异常

    with pytest.raises(TranslationError, match="Translation failed: Unexpected regex error"):
        translator.do_translate("Test Unexpected")