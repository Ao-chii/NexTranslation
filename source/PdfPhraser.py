import fitz  # PyMuPDF
import os
import logging
import asyncio
from typing import Optional, Dict, List, BinaryIO
from pathlib import Path
import numpy as np
from dataclasses import dataclass
from enum import Enum
import tempfile

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFProcessError(Exception):
    """PDF处理相关的自定义异常"""
    pass

class OutputFormat(Enum):
    """输出格式枚举"""
    TEXT = "text"
    HTML = "html"
    XML = "xml"
    JSON = "json"

@dataclass
class PDFConfig:
    """PDF处理配置类"""
    output_format: OutputFormat = OutputFormat.TEXT
    extract_images: bool = True
    image_format: str = "png"
    dpi: int = 300
    thread_count: int = 1
    page_range: Optional[List[int]] = None

class PDFParser:
    def __init__(self, pdf_path: str, config: Optional[PDFConfig] = None):
        """
        初始化PDF解析器
        
        Args:
            pdf_path: PDF文件路径
            config: 处理配置，如果为None则使用默认配置
        """
        self.pdf_path = pdf_path
        self.config = config or PDFConfig()
        self.text = ""
        self.images = []
        self.document = None
        self._page_count = 0
        self._current_page = 0

    def __enter__(self):
        """上下文管理器入口"""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()

    def open(self):
        """打开PDF文件"""
        try:
            self.document = fitz.open(self.pdf_path)
            self._page_count = self.document.page_count
            logger.info(f"成功打开PDF文件: {self.pdf_path}, 页数: {self._page_count}")
        except Exception as e:
            logger.error(f"打开PDF文件失败: {e}")
            raise PDFProcessError(f"无法打开PDF文件: {e}")

    def close(self):
        """关闭PDF文件"""
        if self.document:
            self.document.close()
            logger.info("PDF文件已关闭")

    def is_valid_pdf(self) -> bool:
        """
        检查文件是否为有效的PDF
        
        Returns:
            bool: 是否为有效的PDF文件
        """
        if not os.path.exists(self.pdf_path):
            logger.error("文件不存在")
            return False
        
        if not self.pdf_path.lower().endswith('.pdf'):
            logger.error("文件格式错误：文件必须是PDF格式")
            return False

        try:
            with fitz.open(self.pdf_path) as doc:
                if doc.page_count == 0:
                    logger.error("PDF文件无效：没有页面")
                    return False
            return True
        except Exception as e:
            logger.error(f"PDF文件无效: {e}")
            return False

    async def extract_text_async(self, page_num: int) -> str:
        """
        异步提取单页文本
        
        Args:
            page_num: 页码
            
        Returns:
            str: 提取的文本内容
        """
        try:
            page = self.document.load_page(page_num)
            text = page.get_text(self.config.output_format.value)
            logger.debug(f"成功提取第 {page_num + 1} 页文本")
            return text
        except Exception as e:
            logger.error(f"提取第 {page_num + 1} 页文本失败: {e}")
            return ""

    async def extract_text(self, callback=None) -> Optional[str]:
        """
        从PDF中提取文本
        
        Args:
            callback: 进度回调函数
            
        Returns:
            Optional[str]: 提取的文本内容，失败返回None
        """
        if not self.is_valid_pdf():
            return None

        try:
            pages = self.config.page_range or range(self._page_count)
            tasks = [self.extract_text_async(page_num) for page_num in pages]
            
            texts = []
            for i, task in enumerate(asyncio.as_completed(tasks)):
                text = await task
                texts.append(text)
                self._current_page = i + 1
                if callback:
                    callback(self._current_page, self._page_count)

            self.text = "\n".join(texts)
            logger.info("成功提取所有文本")
            return self.text

        except Exception as e:
            logger.error(f"提取文本失败: {e}")
            return None

    async def extract_image_async(self, page_num: int) -> List[bytes]:
        """
        异步提取单页图像
        
        Args:
            page_num: 页码
            
        Returns:
            List[bytes]: 图像数据列表
        """
        try:
            page = self.document.load_page(page_num)
            image_list = page.get_images(full=True)
            page_images = []
            
            for img in image_list:
                xref = img[0]
                base_image = self.document.extract_image(xref)
                image_bytes = base_image["image"]
                page_images.append(image_bytes)
                
            logger.debug(f"成功提取第 {page_num + 1} 页图像")
            return page_images
        except Exception as e:
            logger.error(f"提取第 {page_num + 1} 页图像失败: {e}")
            return []

    async def extract_images(self, callback=None) -> Optional[List[bytes]]:
        """
        提取PDF中的图像
        
        Args:
            callback: 进度回调函数
            
        Returns:
            Optional[List[bytes]]: 图像数据列表，失败返回None
        """
        if not self.is_valid_pdf():
            return None

        try:
            pages = self.config.page_range or range(self._page_count)
            tasks = [self.extract_image_async(page_num) for page_num in pages]
            
            for i, task in enumerate(asyncio.as_completed(tasks)):
                images = await task
                self.images.extend(images)
                self._current_page = i + 1
                if callback:
                    callback(self._current_page, self._page_count)

            logger.info(f"成功提取 {len(self.images)} 张图像")
            return self.images

        except Exception as e:
            logger.error(f"提取图像失败: {e}")
            return None

    def save_images(self, output_dir: str) -> bool:
        """
        保存提取的图像到指定目录
        
        Args:
            output_dir: 输出目录路径
            
        Returns:
            bool: 是否保存成功
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            for i, img_bytes in enumerate(self.images):
                img_filename = f"image_{i+1}.{self.config.image_format}"
                img_path = output_path / img_filename
                
                with open(img_path, "wb") as img_file:
                    img_file.write(img_bytes)
                logger.info(f"图像已保存：{img_path}")
            
            return True

        except Exception as e:
            logger.error(f"保存图像失败: {e}")
            return False

    async def process_pdf(self, callback=None) -> Dict:
        """
        综合处理PDF，提取文本和图像
        
        Args:
            callback: 进度回调函数
            
        Returns:
            Dict: 包含文本和图像的结果字典
        """
        try:
            self.open()
            
            # 并行处理文本和图像
            text_task = self.extract_text(callback)
            images_task = self.extract_images(callback)
            
            text, images = await asyncio.gather(text_task, images_task)
            
            return {
                "text": text,
                "images": images,
                "page_count": self._page_count,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"处理PDF失败: {e}")
            return {
                "text": None,
                "images": None,
                "page_count": 0,
                "success": False,
                "error": str(e)
            }
        finally:
            self.close()

def progress_callback(current: int, total: int):
    """进度回调示例函数"""
    percentage = (current / total) * 100
    print(f"处理进度: {percentage:.2f}% ({current}/{total})")

async def main():
    """使用示例"""
    # 配置
    config = PDFConfig(
        output_format=OutputFormat.TEXT,
        extract_images=True,
        image_format="png",
        dpi=300,
        thread_count=4
    )
    
    # 使用上下文管理器处理PDF
    pdf_path = "./test/file/translate.cli.text.with.figure.pdf"  # 替换为实际的PDF文件路径
    parser = PDFParser(pdf_path, config)
    
    # 处理PDF
    result = await parser.process_pdf(callback=progress_callback)
    
    if result["success"]:
        print(f"提取的文本:\n{result['text'][:500]}...")  # 显示文本的前500个字符
        print(f"提取的图像数量: {len(result['images'])}")
        
        # 保存图像
        output_dir = 'extracted_images'
        parser.save_images(output_dir)
    else:
        print(f"处理失败: {result.get('error')}")

if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())