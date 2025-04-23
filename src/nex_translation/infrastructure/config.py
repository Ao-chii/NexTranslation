# 使用单例模式 (Singleton Pattern) 实现配置管理器
from pathlib import Path
from threading import RLock
import json
import os
import logging
from typing import Any, Dict, Optional

# 创建Logger对象
logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None
    _lock = RLock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        
        self._config_path = Path.home() / ".config" / "NexTranslation" / "config.json"
        self._config_data = {}
        self._ensure_config_exists()

    def _ensure_config_exists(self, isInit=True):
        """确保配置文件存在，如果不存在则创建默认配置"""
        if not self._config_path.exists():
            if isInit:
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                # 简化的默认配置，专注于英译中
                self._config_data = {
                    "translators": [
                        {
                            "name": "google",  # 默认使用谷歌翻译
                            "envs": {}  # 谷歌翻译不需要额外的环境变量
                        },
                        {
                            "name": "openai",
                            "envs": {
                                "OPENAI_API_KEY": "",
                                "OPENAI_MODEL": "gpt-4"
                            }
                        },
                        {
                            "name": "deepl",
                            "envs": {
                                "DEEPL_API_KEY": ""
                            }
                        }
                    ],
                    "ENABLED_SERVICES": ["Google", "OpenAI", "DeepL"],  # 默认启用的翻译服务
                    "DEFAULT_SERVICE": "google"  # 设置默认翻译服务为谷歌翻译
                }
                self._save_config()
            else:
                raise ValueError(f"Config file {self._config_path} not found!")

    def get_translator_config(self, translator_name: str) -> Dict[str, Any]:
        """获取指定翻译器的配置"""
        for translator in self._config_data.get("translators", []):
            if translator["name"] == translator_name:
                return translator
        return {"name": translator_name, "envs": {}}

    def get_default_service(self) -> str:
        """获取默认翻译服务"""
        return self._config_data.get("DEFAULT_SERVICE", "google")

    def get_enabled_services(self) -> list:
        """获取启用的翻译服务列表"""
        return self._config_data.get("ENABLED_SERVICES", ["Google"])

    def update_translator_config(self, translator_name: str, config: Dict[str, Any]):
        """更新翻译器配置"""
        for translator in self._config_data.get("translators", []):
            if translator["name"] == translator_name:
                translator.update(config)
                self._save_config()
                return
        self._config_data["translators"].append({
            "name": translator_name,
            **config
        })
        self._save_config()

    def set_default_service(self, service_name: str):
        """设置默认翻译服务"""
        self._config_data["DEFAULT_SERVICE"] = service_name
        self._save_config()

    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save config: {str(e)}")
            raise

    def _load_config(self):
        """从文件加载配置"""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise