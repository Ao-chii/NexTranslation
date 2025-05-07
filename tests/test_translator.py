import pytest
from unittest.mock import patch, MagicMock
from string import Template
from nex_translation.core.translator import BaseTranslator

# 创建一个具体的翻译器子类用于测试
class TestTranslator(BaseTranslator):
    name = "test_translator"
    envs = {"api_key": "default_key"}
    
    def do_translate(self, text):
        return f"Translated: {text}"

def test_translator_initialization():
    """测试翻译器初始化"""
    translator = TestTranslator(model="test_model")
    assert translator.name == "test_translator"
    assert translator.model == "test_model"
    assert translator.lang_in == "en"
    assert translator.lang_out == "zh"

def test_translate_with_cache():
    """测试带缓存的翻译"""
    translator = TestTranslator()
    
    # 模拟缓存
    translator.cache.set("Hello", "你好")
    
    # 应该直接返回缓存结果
    assert translator.translate("Hello") == "你好"
    
    # 忽略缓存
    assert translator.translate("Hello", ignore_cache=True) == "Translated: Hello"

def test_prompt_generation():
    """测试提示生成"""
    translator = TestTranslator()
    
    # 测试默认提示
    prompts = translator.prompt("Test text")
    assert len(prompts) == 1
    assert "Test text" in prompts[0]["content"]
    
    # 测试自定义提示
    custom_template = Template("Custom prompt: $text")
    custom_prompts = translator.prompt("Test text", custom_template)
    assert custom_prompts[0]["content"] == "Custom prompt: Test text"