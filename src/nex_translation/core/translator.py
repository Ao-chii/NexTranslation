from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from string import Template
import logging
from ..infrastructure.cache import TranslationCache
from ..infrastructure.config import ConfigManager
from copy import copy
import os
from ..utils.logger import get_logger

logger = get_logger(__name__)

class BaseTranslator(ABC):
    """翻译器基类"""

    name: str = ""  # 翻译器名称
    envs: Dict[str, Any] = {}  # 所需环境变量
    CustomPrompt: bool = False  # 是否支持自定义prompt

    def __init__(
        self,
        model: str = "",
        envs: Optional[Dict] = None,
        prompt: Optional[Template] = None,
        ignore_cache: bool = False,
        lang_in: str = "en",
        lang_out: str = "zh-CN",
    ):
        """
        初始化翻译器
        Args:
            model: 模型名称
            envs: 环境变量配置
            prompt: 自定义prompt模板
            ignore_cache: 是否忽略缓存
            lang_in: 输入语言代码
            lang_out: 输出语言代码
        """
        self.model = model
        self.lang_in = lang_in  # 输入语言
        self.lang_out = lang_out  # 输出语言
        self.ignore_cache = ignore_cache
        self.set_envs(envs)
        self.cache = TranslationCache()
        self.prompt_template = prompt
        # 只在DEBUG级别打印初始化信息
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"BaseTranslator initialized with lang_in={self.lang_in}, lang_out={self.lang_out}")

    def set_envs(self, envs: Optional[Dict] = None):
        """设置环境变量"""
        try:
            # 使用单例模式获取配置管理器实例
            config_manager = ConfigManager.get_instance()

            # 复制类默认值
            self.envs = copy(self.envs)

            # 获取配置文件中的设置
            try:
                saved_config = config_manager.get_translator_config(self.name)
                if saved_config:
                    self.envs.update(saved_config)
            except Exception as e:
                logger.warning(f"Failed to load config for {self.name}: {str(e)}")

            # 检查环境变量是否有更新
            need_update = False
            for key in self.envs:
                if key in os.environ:
                    if self.envs[key] != os.environ[key]:
                        self.envs[key] = os.environ[key]
                        need_update = True

            # 如果环境变量有更新，保存到配置文件
            if need_update:
                try:
                    config_manager.update_translator_config(self.name, self.envs)
                except Exception as e:
                    logger.warning(f"Failed to save updated config for {self.name}: {str(e)}")

            # 处理传入的配置参数
            if envs:
                self.envs.update(envs)
                try:
                    config_manager.update_translator_config(self.name, self.envs)
                except Exception as e:
                    logger.warning(f"Failed to save config with new envs for {self.name}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in set_envs for {self.name}: {str(e)}")
            raise e


    def add_cache_impact_parameters(self, k: str, v: Any):
        """添加影响翻译质量的参数以区分不同参数下的翻译效果"""
        self.cache.add_params(k, v)

    def translate(self, text: str, ignore_cache: bool = False) -> str:
        """
        翻译文本，这是其他部分应该调用的方法
        Args:
            text: 要翻译的文本
            ignore_cache: 是否忽略缓存
        Returns:
            翻译后的文本
        """
        if not (self.ignore_cache or ignore_cache):
            cache = self.cache.get(text)
            if cache is not None:
                return cache

        translation = self.do_translate(text)
        self.cache.set(text, translation)
        return translation

    @abstractmethod
    def do_translate(self, text: str) -> str:
        """
        实际执行翻译的方法，子类必须实现
        Args:
            text: 要翻译的文本
        Returns:
            翻译后的文本
        """
        raise NotImplementedError

    def prompt(self, text: str, prompt_template: Template | None = None) -> list[dict[str, str]]:
        """
        生成翻译提示 - 专注于英译中场景
        Args:
            text: 要翻译的文本
            prompt_template: 提示模板
        Returns:
            提示消息列表
        """
        try:
            if prompt_template:
                return [{
                    "role": "user",
                    "content": prompt_template.safe_substitute({
                        "text": text,
                    })
                }]
        except Exception:
            logging.exception("解析提示模板时出错，使用默认提示。")

        return [{
            "role": "user",
            "content": (
                "你是一个专业的英译中翻译引擎。请将以下英文文本翻译成中文，"
                "保持公式标记 {v*} 不变。直接输出翻译结果，不要包含其他文本。"
                "\n\n"
                f"原文：{text}"
                "\n\n"
                "译文："
            )
        }]

    def __str__(self):
        return f"{self.name} {self.model}"
