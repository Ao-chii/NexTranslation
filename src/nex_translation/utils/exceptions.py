"""NexTranslation异常定义模块

按照分层架构设计，定义了系统中所有自定义异常类，包括:
1. PDF处理异常
2. 翻译服务异常
3. 资源异常
4. 业务逻辑异常
5. 通用异常
"""
from typing import Optional, Dict, Any
from datetime import datetime

class NexTranslationError(Exception):
    """所有自定义异常的基类"""
    def __init__(self, message: str, is_retryable: bool = False):
        super().__init__(message)
        self.is_retryable = is_retryable
        self.timestamp = datetime.now()

# =============== PDF处理异常 ===============
class PDFError(NexTranslationError):
    """PDF处理相关异常的基类"""
    pass

class FileReadError(PDFError):
    """文件读取异常"""
    def __init__(self, file_path: str, reason: str):
        super().__init__(f"Failed to read file {file_path}: {reason}", is_retryable=False)
        self.file_path = file_path

class PDFFormatError(PDFError):
    """PDF格式异常"""
    def __init__(self, details: str):
        super().__init__(f"Invalid PDF format: {details}", is_retryable=False)

class ContentExtractionError(PDFError):
    """内容提取异常"""
    def __init__(self, page_number: int, element_type: str):
        super().__init__(
            f"Failed to extract {element_type} content from page {page_number}", 
            is_retryable=True
        )
        self.page_number = page_number
        self.element_type = element_type

class LayoutAnalysisError(PDFError):
    """布局分析异常"""
    def __init__(self, page_number: int, details: str):
        super().__init__(f"Layout analysis failed on page {page_number}: {details}")
        self.page_number = page_number

# =============== 翻译服务异常 ===============
class TranslationError(NexTranslationError):
    """翻译服务相关异常的基类"""
    pass

class APICallError(TranslationError):
    """API调用异常"""
    def __init__(self, service_name: str, error_code: str, message: str):
        super().__init__(
            f"{service_name} API error ({error_code}): {message}", 
            is_retryable=True
        )
        self.service_name = service_name
        self.error_code = error_code

class RateLimitError(TranslationError):
    """服务限流异常"""
    def __init__(self, service_name: str, retry_after: int = 60):
        super().__init__(
            f"{service_name}: Rate limit exceeded. Retry after {retry_after}s",
            is_retryable=True
        )
        self.service_name = service_name
        self.retry_after = retry_after

class TranslationQualityError(TranslationError):
    """翻译质量异常"""
    def __init__(self, text_id: str, confidence_score: float):
        super().__init__(
            f"Translation quality below threshold for text {text_id} (score: {confidence_score})",
            is_retryable=True
        )
        self.text_id = text_id
        self.confidence_score = confidence_score

# =============== 资源异常 ===============
class ResourceError(NexTranslationError):
    """资源相关异常的基类"""
    pass

class OutOfMemoryError(ResourceError):
    """内存不足异常"""
    def __init__(self, required_mb: int, available_mb: int):
        super().__init__(
            f"Out of memory: required {required_mb}MB, available {available_mb}MB",
            is_retryable=False
        )
        self.required_mb = required_mb
        self.available_mb = available_mb

class DiskSpaceError(ResourceError):
    """磁盘空间不足"""
    def __init__(self, required_mb: int, available_mb: int):
        super().__init__(
            f"Insufficient disk space: required {required_mb}MB, available {available_mb}MB",
            is_retryable=False
        )
        self.required_mb = required_mb
        self.available_mb = available_mb

class ConcurrencyLimitError(ResourceError):
    """并发限制异常"""
    def __init__(self, max_concurrent: int):
        super().__init__(
            f"Concurrency limit reached (max: {max_concurrent})",
            is_retryable=True
        )
        self.max_concurrent = max_concurrent

# =============== 业务逻辑异常 ===============
class BusinessError(NexTranslationError):
    """业务逻辑相关异常的基类"""
    pass

class ConfigurationError(BusinessError):
    """配置错误"""
    def __init__(self, config_key: str, reason: str):
        super().__init__(f"Configuration error for {config_key}: {reason}")
        self.config_key = config_key

class ValidationError(BusinessError):
    """参数验证异常"""
    def __init__(self, field: str, value: Any, reason: str):
        super().__init__(f"Validation failed for {field}: {reason}")
        self.field = field
        self.value = value

class TaskStateError(BusinessError):
    """任务状态异常"""
    def __init__(self, task_id: str, current_state: str, expected_state: str):
        super().__init__(
            f"Invalid task state for {task_id}: expected {expected_state}, got {current_state}"
        )
        self.task_id = task_id
        self.current_state = current_state
        self.expected_state = expected_state

# =============== 通用异常 ===============
class NetworkError(NexTranslationError):
    """网络连接异常"""
    def __init__(self, host: str, port: Optional[int] = None):
        message = f"Network error connecting to {host}"
        if port:
            message += f":{port}"
        super().__init__(message, is_retryable=True)
        self.host = host
        self.port = port

class TimeoutError(NexTranslationError):
    """超时异常"""
    def __init__(self, operation: str, timeout_seconds: int):
        super().__init__(
            f"Operation {operation} timed out after {timeout_seconds}s",
            is_retryable=True
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds

class CancellationError(NexTranslationError):
    """任务取消异常"""
    def __init__(self, task_id: str, reason: str):
        super().__init__(f"Task {task_id} cancelled: {reason}")
        self.task_id = task_id