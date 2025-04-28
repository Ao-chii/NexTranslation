import unittest
import json
import tempfile
from pathlib import Path
from nex_translation.infrastructure.cache import (
    TranslationCache, 
    init_test_db,
    clean_test_db
)

class TestTranslationCache(unittest.TestCase):
    def setUp(self):
        """每个测试用例前的设置"""
        self.test_db = init_test_db()
        
    def tearDown(self):
        """每个测试用例后的清理"""
        clean_test_db(self.test_db)

    def test_basic_set_get(self):
        """测试基本的设置和获取操作"""
        cache = TranslationCache("test_engine")
        
        # 测试获取不存在的条目
        result = cache.get("hello")
        self.assertIsNone(result)
        
        # 测试设置和获取
        cache.set("hello", "你好")
        result = cache.get("hello")
        self.assertEqual(result, "你好")

    def test_params_handling(self):
        """测试参数处理"""
        # 测试基本参数
        params = {"model": "gpt-3.5", "temperature": 0.7}
        cache = TranslationCache("test_engine", params)
        cache.set("hello", "你好")
        self.assertEqual(cache.get("hello"), "你好")
        
        # 测试嵌套参数
        nested_params = {
            "model": {
                "name": "gpt-3.5",
                "settings": {"temp": 0.8}
            }
        }
        cache = TranslationCache("test_engine", nested_params)
        cache.set("hello", "你好2")
        self.assertEqual(cache.get("hello"), "你好2")

    def test_params_order_independence(self):
        """测试参数顺序无关性"""
        params1 = {"a": 1, "b": {"x": 2, "y": 3}}
        params2 = {"b": {"y": 3, "x": 2}, "a": 1}
        
        cache1 = TranslationCache("test_engine", params1)
        cache2 = TranslationCache("test_engine", params2)
        
        # 验证两个缓存实例使用相同的参数字符串
        self.assertEqual(
            cache1.translate_engine_params,
            cache2.translate_engine_params
        )
        
        # 验证缓存共享
        cache1.set("test", "测试")
        self.assertEqual(cache2.get("test"), "测试")

    def test_engine_distinction(self):
        """测试不同引擎的缓存隔离"""
        cache1 = TranslationCache("engine1")
        cache2 = TranslationCache("engine2")
        
        cache1.set("hello", "你好1")
        cache2.set("hello", "你好2")
        
        self.assertEqual(cache1.get("hello"), "你好1")
        self.assertEqual(cache2.get("hello"), "你好2")

    def test_params_update(self):
        """测试参数更新功能"""
        cache = TranslationCache("test_engine", {"a": 1})
        
        # 测试更新参数
        cache.update_params({"b": 2})
        self.assertEqual(cache.params, {"a": 1, "b": 2})
        
        # 测试添加单个参数
        cache.add_params("c", 3)
        self.assertEqual(cache.params, {"a": 1, "b": 2, "c": 3})
        
        # 验证更新后的缓存功能
        cache.set("test", "测试")
        self.assertEqual(cache.get("test"), "测试")

    def test_error_handling(self):
        """测试错误处理"""
        # 测试引擎名称长度限制
        with self.assertRaises(AssertionError):
            TranslationCache("x" * 21)
        
        # 测试空参数处理
        cache = TranslationCache()
        self.assertEqual(cache.params, {})
        
        # 测试None参数处理
        cache.update_params(None)
        self.assertEqual(cache.params, {})

    def test_cache_overwrite(self):
        """测试缓存覆写功能"""
        cache = TranslationCache("test_engine")
        
        # 设置初始翻译
        cache.set("hello", "你好")
        self.assertEqual(cache.get("hello"), "你好")
        
        # 覆写翻译
        cache.set("hello", "您好")
        self.assertEqual(cache.get("hello"), "您好")

if __name__ == '__main__':
    unittest.main()