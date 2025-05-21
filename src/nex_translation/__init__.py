"""NexTranslation - An intelligent PDF translation tool with formula preservation"""
from nex_translation.utils.logger import get_logger
from nex_translation.core.pdf_processor import translate, translate_stream

logger = get_logger(__name__)

__version__ = "0.3.0"
__author__ = "Ao-chii"
__email__ = "2543327978@qq.com"
__all__ = ["translate", "translate_stream"]