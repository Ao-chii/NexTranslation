from pathlib import Path
from threading import RLock
import json
import logging
from typing import Any, Dict, Optional
import copy

# 创建Logger对象进行日志记录
logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器(单例模式实现)
    核心职责：
    1. 管理应用配置
    2. 确保配置一致性
    3. 提供线程安全的配置访问
    """
    _instance = None 
    _lock = RLock()  # 使用RLock以支持同一线程多次获取

    @staticmethod
    def normalize_service_name(service_name: str) -> str:
        """规范化服务名称"""
        return service_name.lower().strip()

    @classmethod
    def get_instance(cls):
        """
        双重检查锁定(Double-Checked Locking)实现单例：
        1. 首次检查：避免不必要的锁获取
        2. 加锁：确保线程安全
        3. 二次检查：防止竞态条件
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        """
        初始化策略：
        1. 防重复初始化检查
        2. 设置配置文件路径
        3. 初始化配置数据
        4. 确保配置文件存在
        """
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        
        self._config_path = Path.home() / ".config" / "NexTranslation" / "config.json"
        self._config_data = {}
        self._ensure_config_exists()

    def _ensure_config_exists(self, isInit=True):
        """
        配置文件管理策略：
        1. 首次运行：创建默认配置
        2. 正常运行：加载已有配置
        3. 配置验证：确保必要配置存在
        
        默认配置结构：
        - translators: 翻译服务配置列表
        - ENABLED_SERVICES: 启用的服务列表
        - DEFAULT_SERVICE: 默认翻译服务
        """
        if not self._config_path.exists():
            if isInit:
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                # 默认配置，专注于英译中
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
                    "ENABLED_SERVICES": ["google", "openai", "deepl"],  # 默认启用的翻译服务
                    "DEFAULT_SERVICE": "google"  # 设置默认翻译服务为谷歌翻译
                }
                self._save_config()
            else:
                raise ValueError(f"Config file {self._config_path} not found!")

    def get_translator_config(self, translator_name: str) -> Dict[str, Any]:
        """
        翻译器配置获取逻辑：
        1. 标准化服务名称
        2. 查找匹配配置
        3. 返回环境变量配置
        """
        normalized_name = self.normalize_service_name(translator_name)
        translators = self._config_data.get("translators", [])
        for translator in translators:
            if self.normalize_service_name(translator.get("name")) == normalized_name:
                return translator.get("envs", {})
        return {}

    def get_default_service(self) -> str:
        """获取默认翻译服务"""
        service = self._config_data.get("DEFAULT_SERVICE", "google")
        return self.normalize_service_name(service)

    def get_enabled_services(self) -> list:
        """获取启用的翻译服务列表"""
        services = self._config_data.get("ENABLED_SERVICES", ["google"])
        return [self.normalize_service_name(s) for s in services]

    def update_translator_config(self, translator_name: str, new_translator_envs: Dict[str, Any]):
        """更新翻译器配置"""
        normalized_name = self.normalize_service_name(translator_name)
        with self._lock:
            translators = self._config_data.get("translators", [])
            for translator in translators:
                if self.normalize_service_name(translator.get("name")) == normalized_name:
                    translator["envs"] = copy.deepcopy(new_translator_envs)
                    self._save_config()
                    return
            
            if "translators" not in self._config_data:
                self._config_data["translators"] = []
                
            self._config_data["translators"].append({
                "name": normalized_name,
                "envs": copy.deepcopy(new_translator_envs)
            })
            self._save_config()

    def set_default_service(self, service_name: str):
        """设置默认翻译服务"""
        self._config_data["DEFAULT_SERVICE"] = service_name
        self._save_config()

    def _save_config(self):
        """保存配置到文件"""
        with self._lock:
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
