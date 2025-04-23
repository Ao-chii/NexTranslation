from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class TranslatorBase(ABC):
    @abstractmethod
    def translate(self, text: str) -> str:
        """翻译文本"""
        pass

    @abstractmethod
    def batch_translate(self, texts: list[str]) -> list[str]:
        """批量翻译文本"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """翻译器名称"""
        pass

    @property
    @abstractmethod
    def required_envs(self) -> Dict[str, Any]:
        """所需环境变量"""
        pass