"""NexTranslation - An intelligent PDF translation tool with formula preservation"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .core.pdf_processor import PDFProcessor
from .core.translator import TranslatorService
from .core.document_builder import DocumentBuilder

__all__ = ['PDFProcessor', 'TranslatorService', 'DocumentBuilder']