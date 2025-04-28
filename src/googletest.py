import unittest
from unittest.mock import patch, Mock
import requests
from nex_translation.core.google_translator import GoogleTranslator
from nex_translation.utils.exceptions import TranslationError

class TestGoogleTranslator(unittest.TestCase):
    def setUp(self):
        # 每个测试用例前创建翻译器实例
        self.translator = GoogleTranslator()
        
    def test_basic_translation(self):
        """测试基本翻译功能"""
        with patch('requests.Session') as mock_session:
            # 模拟Google翻译返回的HTML响应
            mock_response = Mock()
            mock_response.text = '<div class="result-container">测试翻译结果</div>'
            mock_response.status_code = 200
            mock_session.return_value.get.return_value = mock_response
            
            result = self.translator.do_translate("test text")
            self.assertEqual(result, "测试翻译结果")
            
    def test_long_text_error(self):
        """测试超长文本（>5000字符）"""
        long_text = "x" * 5001
        with self.assertRaises(TranslationError):
            self.translator.do_translate(long_text)
            
    def test_network_error(self):
        """测试网络请求失败的情况"""
        with patch('requests.Session') as mock_session:
            mock_session.return_value.get.side_effect = requests.RequestException()
            with self.assertRaises(TranslationError):
                self.translator.do_translate("test")
                
    def test_bad_response(self):
        """测试错误的响应状态码"""
        with patch('requests.Session') as mock_session:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_session.return_value.get.return_value = mock_response
            
            with self.assertRaises(TranslationError):
                self.translator.do_translate("test")
                
    def test_no_translation_result(self):
        """测试无法提取翻译结果的情况"""
        with patch('requests.Session') as mock_session:
            mock_response = Mock()
            mock_response.text = '<div>没有翻译结果</div>'
            mock_response.status_code = 200
            mock_session.return_value.get.return_value = mock_response
            
            with self.assertRaises(TranslationError):
                self.translator.do_translate("test")

if __name__ == '__main__':
    unittest.main()