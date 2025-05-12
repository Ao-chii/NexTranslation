"""NexTranslation - An intelligent PDF translation tool with formula preservation"""
from .utils.logger import LoggerManager
from .core.pdf_processor import translate

__version__ = "0.2.0"
__author__ = "Ao-chii"
__email__ = "2543327978@qq.com"

# 初始化日志管理器
_logger_manager = LoggerManager()

# 获取根日志记录器
logger = _logger_manager.get_logger(__name__)

# 初始化缓存系统
def init_cache():
    """初始化缓存系统"""
    try:
        from .infrastructure.cache import init_db
        init_db()
        logger.info("Cache system initialized")
    except Exception as e:
        logger.error(f"Failed to initialize cache system: {e}")

# 初始化应用
def init_app():
    """初始化应用"""
    init_cache()

# 导出主要API
__all__ = ['translate']

# 初始化应用
init_app()

# 记录应用启动信息
logger.info(f"NexTranslation v{__version__} initialized")
