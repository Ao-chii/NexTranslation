import logging
from nex_translation.core.pdf_processor import translate, translate_stream

log = logging.getLogger(__name__)

__version__ = "1.9.6"
__author__ = "Byaidu"
__all__ = ["translate", "translate_stream"]
