"""NexTranslation - An intelligent PDF translation tool with formula preservation"""

__version__ = "0.1.0"
__author__ = "Ao-chii"
__email__ = "2543327978@qq.com"

from .core.pdf_processor import PDFProcessor
from .core.translator import TranslatorService
from .core.document_builder import DocumentBuilder

__all__ = ['PDFProcessor', 'TranslatorService', 'DocumentBuilder']