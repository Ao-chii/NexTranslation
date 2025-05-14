import logging
import os
import unicodedata
from copy import copy
from string import Template
from typing import cast

from src.nex_translation.infrastructure.cache import TranslationCache
from src.nex_translation.infrastructure.config import ConfigManager

logger = logging.getLogger(__name__)


class BaseTranslator:
    name = "base"
    envs = {}
    lang_map: dict[str, str] = {}
    CustomPrompt = False

    def __init__(self, lang_in: str, lang_out: str, model: str, ignore_cache: bool):
        lang_in = self.lang_map.get(lang_in.lower(), lang_in)
        lang_out = self.lang_map.get(lang_out.lower(), lang_out)
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.model = model
        self.ignore_cache = ignore_cache

        self.cache = TranslationCache(
            self.name,
            {
                "lang_in": lang_in,
                "lang_out": lang_out,
                "model": model,
            },
        )

    def set_envs(self, envs):
        # Detach from self.__class__.envs
        # Cannot use self.envs = copy(self.__class__.envs)
        # because if set_envs called twice, the second call will override the first call
        self.envs = copy(self.envs)
        if ConfigManager.get_translator_by_name(self.name):
            self.envs = ConfigManager.get_translator_by_name(self.name)
        needUpdate = False
        for key in self.envs:
            if key in os.environ:
                self.envs[key] = os.environ[key]
                needUpdate = True
        if needUpdate:
            ConfigManager.set_translator_by_name(self.name, self.envs)
        if envs is not None:
            for key in envs:
                self.envs[key] = envs[key]
            ConfigManager.set_translator_by_name(self.name, self.envs)

    def add_cache_impact_parameters(self, k: str, v):
        """
        Add parameters that affect the translation quality to distinguish the translation effects under different parameters.
        :param k: key
        :param v: value
        """
        self.cache.add_params(k, v)

    def translate(self, text: str, ignore_cache: bool = False) -> str:
        """
        Translate the text, and the other part should call this method.
        :param text: text to translate
        :return: translated text
        """
        if not (self.ignore_cache or ignore_cache):
            cache = self.cache.get(text)
            if cache is not None:
                return cache

        translation = self.do_translate(text)
        self.cache.set(text, translation)
        return translation

    def do_translate(self, text: str) -> str:
        """
        Actual translate text, override this method
        :param text: text to translate
        :return: translated text
        """
        raise NotImplementedError

    def prompt(
        self, text: str, prompt_template: Template | None = None
    ) -> list[dict[str, str]]:
        try:
            return [
                {
                    "role": "user",
                    "content": cast(Template, prompt_template).safe_substitute(
                        {
                            "lang_in": self.lang_in,
                            "lang_out": self.lang_out,
                            "text": text,
                        }
                    ),
                }
            ]
        except AttributeError:  # `prompt_template` is None
            pass
        except Exception:
            logging.exception("Error parsing prompt, use the default prompt.")

        return [
            {
                "role": "user",
                "content": (
                    "You are a professional, authentic machine translation engine. "
                    "Only Output the translated text, do not include any other text."
                    "\n\n"
                    f"Translate the following markdown source text to {self.lang_out}. "
                    "Keep the formula notation {v*} unchanged. "
                    "Output translation directly without any additional text."
                    "\n\n"
                    f"Source Text: {text}"
                    "\n\n"
                    "Translated Text:"
                ),
            },
        ]

    def __str__(self):
        return f"{self.name} {self.lang_in} {self.lang_out} {self.model}"