from pathlib import Path
from threading import RLock
import json

class ConfigManager:
    _instance = None
    _lock = RLock()

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        
        # 修改默认配置路径
        self._config_path = Path.home() / ".config" / "NexTranslation" / "config.json"
        self._config_data = {}
        self._ensure_config_exists()

    def _ensure_config_exists(self, isInit=True):
        """确保配置文件存在，如果不存在则创建默认配置"""
        if not self._config_path.exists():
            if isInit:
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                # 设置默认配置
                self._config_data = {
                    "translators": [],
                    "PDF2ZH_LANG_FROM": "English",
                    "PDF2ZH_LANG_TO": "Simplified Chinese",
                    "ENABLED_SERVICES": ["OpenAI", "DeepL"],
                    "HIDDEN_GRADIO_DETAILS": False
                }
                self._save_config()
            else:
                raise ValueError(f"Config file {self._config_path} not found!")