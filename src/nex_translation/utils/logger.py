"""日志管理模块

提供统一的日志配置和管理功能，包括:
1. 日志格式化
2. 日志级别控制
3. 多目标输出(控制台、文件)
4. 上下文追踪
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Union, Dict
from datetime import datetime

class LoggerManager:
    """日志管理器
    
    负责统一配置和管理项目中的所有日志记录器
    """
    
    # 默认日志格式
    DEFAULT_FORMAT = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
    # 详细日志格式（用于文件日志）
    DETAILED_FORMAT = '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s'
    
    def __init__(self):
        # 确保日志目录存在
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # 初始化根日志记录器
        self.root_logger = logging.getLogger("nex_translation")
        self.root_logger.setLevel(logging.INFO)
        
        # 避免日志重复
        self.root_logger.propagate = False
        
        # 清除现有的处理器
        self.root_logger.handlers.clear()
        
        # 初始化处理器
        self._setup_console_handler()
        self._setup_file_handler()
    
    def _setup_console_handler(self):
        """配置控制台日志处理器"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(self.DEFAULT_FORMAT)
        console_handler.setFormatter(console_formatter)
        self.root_logger.addHandler(console_handler)
    
    def _setup_file_handler(self):
        """配置文件日志处理器"""
        log_file = self.log_dir / f"nex_translation_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(self.DETAILED_FORMAT)
        file_handler.setFormatter(file_formatter)
        self.root_logger.addHandler(file_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志记录器
        
        Args:
            name: 日志记录器名称，通常使用模块名称
            
        Returns:
            logging.Logger: 配置好的日志记录器
        """
        return logging.getLogger(f"nex_translation.{name}")
    
    def set_level(self, level: Union[str, int]):
        """设置日志级别
        
        Args:
            level: 日志级别，可以是字符串('DEBUG', 'INFO'等)或对应的数字
        """
        self.root_logger.setLevel(level)
        for handler in self.root_logger.handlers:
            handler.setLevel(level)
    
    def disable_console_output(self):
        """禁用控制台输出"""
        for handler in self.root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and \
               handler.stream == sys.stdout:
                self.root_logger.removeHandler(handler)
    
    def enable_debug_mode(self):
        """启用调试模式，增加日志详细程度"""
        self.set_level(logging.DEBUG)
        # 更新控制台处理器格式
        for handler in self.root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and \
               handler.stream == sys.stdout:
                handler.setFormatter(logging.Formatter(self.DETAILED_FORMAT))

# 全局日志管理器实例
_logger_manager = LoggerManager()

def get_logger(name: str) -> logging.Logger:
    """获取日志记录器的便捷方法
    
    Args:
        name: 模块名称
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    return _logger_manager.get_logger(name)

def set_log_level(level: Union[str, int]):
    """设置全局日志级别的便捷方法"""
    _logger_manager.set_level(level)

def enable_debug():
    """启用调试模式的便捷方法"""
    _logger_manager.enable_debug_mode()

# 使用示例：
if __name__ == "__main__":
    # 获取日志记录器
    logger = get_logger(__name__)
    
    # 记录不同级别的日志
    logger.debug("这是一条调试日志")
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    
    # 启用调试模式
    enable_debug()
    logger.debug("这是启用调试模式后的日志")