import re
import html
import requests
from typing import Optional
from string import Template
from ..core.translator import BaseTranslator
from ..utils.exceptions import TranslationError

class GoogleTranslator(BaseTranslator):
    """Google翻译实现类"""
    name = "google"
    
    def __init__(
        self,
        model: str = "",
        envs: Optional[dict] = None,
        prompt: Optional[Template] = None,
        ignore_cache: bool = False,
    ):
        super().__init__(model, envs, prompt, ignore_cache)
        self.endpoint = "https://translate.google.com/m"
        self.headers = {
            "User-Agent": "Mozilla/4.0 (compatible;MSIE 6.0;Windows NT 5.1;SV1;.NET CLR 1.1.4322;.NET CLR 2.0.50727;.NET CLR 3.0.04506.30)"  # noqa: E501
        }
        self.session = requests.Session()
        
    def do_translate(self, text: str) -> str:
        """执行翻译"""
        if len(text) > 5000:
            raise TranslationError("Text too long for Google Translate (max 5000 chars)")
            
        try:
            # 发送请求到Google翻译
            response = self.session.get(
                self.endpoint,
                params={
                    "tl": self.lang_out,
                    "sl": self.lang_in,
                    "q": text,
                },
                headers=self.headers,
                timeout=30,
            )
            
            if response.status_code == 400:
                raise TranslationError("Google Translate API error")
                
            response.raise_for_status()
            
            # 使用正则表达式提取翻译结果
            result = re.findall(r'(?s)class="(?:t0|result-container)">(.*?)<', response.text)
            if not result:
                raise TranslationError("Failed to extract translation result")

            # 解码HTML实体(如&quot;)并去除首尾空白    
            return html.unescape(result[0]).strip()
            
        except requests.RequestException as e:
            raise TranslationError(f"Request failed: {str(e)}")
        except Exception as e:
            raise TranslationError(f"Translation failed: {str(e)}")