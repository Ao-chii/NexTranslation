import re
import html
import logging
import requests
from typing import Optional
from string import Template
from ..core.translator import BaseTranslator
from ..utils.exceptions import TranslationError
from ..utils.logger import get_logger

logger = get_logger(__name__)

class GoogleTranslator(BaseTranslator):
    """Google翻译实现类"""
    name = "google"

    def __init__(
        self,
        model: str = "",
        envs: Optional[dict] = None,
        prompt: Optional[Template] = None,
        ignore_cache: bool = False,
        lang_in: str = "en",
        lang_out: str = "zh-CN",
    ):
        super().__init__(model, envs, prompt, ignore_cache)
        self.endpoint = "https://translate.google.com/m"
        self.headers = {
            "User-Agent": "Mozilla/4.0 (compatible;MSIE 6.0;Windows NT 5.1;SV1;.NET CLR 1.1.4322;.NET CLR 2.0.50727;.NET CLR 3.0.04506.30)"  # noqa: E501
        }
        self.session = requests.Session()
        # 设置输入和输出语言
        self.lang_in = lang_in
        self.lang_out = lang_out
        # 只在DEBUG级别打印初始化信息
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Initialized {self.name} translator with lang_in={self.lang_in}, lang_out={self.lang_out}")

    def do_translate(self, text: str) -> str:
        """执行翻译"""
        if len(text) > 5000:
            logger.error(f"Text length ({len(text)}) exceeds limit (5000)")
            raise TranslationError("Text too long for Google Translate (max 5000 chars)")

        try:
            # 只在DEBUG级别打印请求信息
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Sending translation request for text: {text[:100]}...")
            # 发送请求到Google翻译，减少超时时间为15秒
            response = self.session.get(
                self.endpoint,
                params={
                    "tl": self.lang_out,
                    "sl": self.lang_in,
                    "q": text,
                },
                headers=self.headers,
                timeout=15,
            )

            if response.status_code == 400:
                logger.error("Google Translate API returned 400 error")
                raise TranslationError("Google Translate API error")

            response.raise_for_status()

            # 使用正则表达式提取翻译结果
            result = re.findall(r'(?s)class="(?:t0|result-container)">(.*?)<', response.text)
            if not result:
                logger.error("Failed to extract translation from response")
                # 如果无法提取翻译结果，返回原文而不是抛出异常
                logger.warning("Returning original text as fallback")
                return text

            # 解码HTML实体(如&quot;)并去除首尾空白
            translated_text = html.unescape(result[0]).strip()
            # 只在DEBUG级别打印翻译结果
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Translation successful. Result: {translated_text[:100]}...")
            return translated_text

        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            # 网络请求失败时返回原文而不是抛出异常
            logger.warning("Network error, returning original text as fallback")
            return text
        except Exception as e:
            logger.error(f"Unexpected error during translation: {str(e)}")
            # 其他错误时返回原文而不是抛出异常
            logger.warning("Translation error, returning original text as fallback")
            return text