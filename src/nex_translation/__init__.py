"""NexTranslation - An intelligent PDF translation tool with formula preservation"""
from .utils.logger import LoggerManager
from .core.pdf_processor import translate

__version__ = "0.1.0"
__author__ = "Ao-chii"
__email__ = "2543327978@qq.com"

# 初始化日志管理器
_logger_manager = LoggerManager()

# 获取根日志记录器
logger = _logger_manager.get_logger(__name__)

# 导出主要API
__all__ = ['translate']

# 记录应用启动信息
logger.info(f"NexTranslation v{__version__} initialized")
