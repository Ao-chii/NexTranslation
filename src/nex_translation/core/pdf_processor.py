# pdf文件从解析到翻译到导出的高层指挥，分别实例化三个类：
# DoclayoutModel(进行布局分析), TranslateConverter(进行翻译), PDFPageInterpreterEx(内容解析)
# 以利用这三个类完成工作

# 注意此python文件最终只对外暴露两个函数：
# 直接处理pdf二进制流的translate_stream()以及直接处理pdf文件的translate()

import asyncio
import io
import os
import re
import sys
import logging
import tempfile
from asyncio import CancelledError
from pathlib import Path
from string import Template
from typing import Any, BinaryIO, List, Optional, Dict

import numpy as np
import requests
import tqdm
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfexceptions import PDFValueError
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pymupdf import Document
from babeldoc.assets.assets import get_font_and_metadata

from .doclayout import OnnxModel
from .converter import TranslateConverter
from .pdfinterpreter import PDFPageInterpreterEx

from ..utils.exceptions import (
    PDFError,
    PDFFormatError,
    ContentExtractionError,
    LayoutAnalysisError
)
from ..utils.logger import get_logger
from ..infrastructure.config import ConfigManager

logger = get_logger(__name__)


# 检查文件是否存在
def check_files(files: List[str]) -> List[str]:
    missing_files = [file for file in files if not os.path.exists(file)]
    return missing_files

# 对pdf文件二进制流进行修补处理
# 逐页分析布局，生成修补的文件流
# 输入：原始pdf内容流 输出：修补后的对象字典
def translate_patch(
    inf: BinaryIO,
    pages: Optional[list[int]] = None,
    vfont: str = "",
    vchar: str = "",
    thread: int = 0,
    doc_zh: Document = None,
    service: str = "",
    callback: object = None,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    ignore_cache: bool = False,
    lang_from: str = "en",
    lang_to: str = "zh-CN",
    **kwarg: Any,
) -> None:
    try:
        rsrcmgr = PDFResourceManager()
        layout = {}
        device = TranslateConverter(
            rsrcmgr,
            vfont,
            vchar,
            thread,
            layout,
            lang_in=lang_from,
            lang_out=lang_to,
            service=service,
            envs=envs,
            prompt=prompt,
            ignore_cache=ignore_cache,
        )

        if device is None:
            raise PDFError("Failed to initialize TranslateConverter")

        obj_patch = {}
        interpreter = PDFPageInterpreterEx(rsrcmgr, device, obj_patch)

        if pages:
            total_pages = len(pages)
        else:
            total_pages = doc_zh.page_count

        parser = PDFParser(inf)
        try:
            doc = PDFDocument(parser)
        except PDFValueError as e:
            raise PDFFormatError(str(e))

        logger.info(f"Starting PDF translation with {total_pages} pages")

        with tqdm.tqdm(total=total_pages) as progress:
            for pageno, page in enumerate(PDFPage.create_pages(doc)):
                if cancellation_event and cancellation_event.is_set():
                    logger.info("Translation cancelled by user")
                    raise CancelledError("task cancelled")

                if pages and (pageno not in pages):
                    continue

                # 只在DEBUG级别打印页面处理信息
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Processing page {pageno}")
                # 确保进度条更新在页面处理完成后
                if callback:
                    callback(progress)

                try:
                    page.pageno = pageno
                    pix = doc_zh[page.pageno].get_pixmap()
                    image = np.fromstring(pix.samples, np.uint8).reshape(
                        pix.height, pix.width, 3
                    )[:, :, ::-1]

                    page_layout = model.predict(image, imgsz=int(pix.height / 32) * 32)[0]
                    if not page_layout:
                        raise LayoutAnalysisError(pageno, "Failed to predict page layout")

                    # Layout processing
                    box = np.ones((pix.height, pix.width))
                    h, w = box.shape
                    vcls = ["abandon", "figure", "table", "isolate_formula", "formula_caption"]

                    for i, d in enumerate(page_layout.boxes):
                        if page_layout.names[int(d.cls)] not in vcls:  # 非特殊区域
                            x0, y0, x1, y1 = d.xyxy.squeeze()
                            x0, y0, x1, y1 = (
                                np.clip(int(x0 - 1), 0, w - 1),
                                np.clip(int(h - y1 - 1), 0, h - 1),
                                np.clip(int(x1 + 1), 0, w - 1),
                                np.clip(int(h - y0 + 1), 0, h - 1),
                            )
                            box[y0:y1, x0:x1] = i + 2
                    for i, d in enumerate(page_layout.boxes):
                        if page_layout.names[int(d.cls)] in vcls: # 特殊区域
                            x0, y0, x1, y1 = d.xyxy.squeeze()
                            x0, y0, x1, y1 = (
                                np.clip(int(x0 - 1), 0, w - 1),
                                np.clip(int(h - y1 - 1), 0, h - 1),
                                np.clip(int(x1 + 1), 0, w - 1),
                                np.clip(int(h - y0 + 1), 0, h - 1),
                            )
                            box[y0:y1, x0:x1] = 0
                    layout[page.pageno] = box
                    # 新建一个 xref 存放新指令流
                    page.page_xref = doc_zh.get_new_xref()  # hack 插入页面的新 xref
                    doc_zh.update_object(page.page_xref, "<<>>")
                    doc_zh.update_stream(page.page_xref, b"")
                    doc_zh[page.pageno].set_contents(page.page_xref)
                    interpreter.process_page(page)

                    # 在页面处理完成后更新进度条
                    progress.update()
                    if callback:
                        callback(progress)

                except Exception as e:
                    logger.error(f"Error processing page {pageno}: {str(e)}")
                    raise ContentExtractionError(pageno, "text")

        logger.info("PDF translation completed successfully")
        device.close()
        return obj_patch

    except Exception as e:
        logger.error(f"PDF translation failed: {str(e)}")
        raise

def translate_stream(
    stream: bytes,
    pages: Optional[list[int]] = None,
    service: str = "",
    thread: int = 0,
    vfont: str = "",
    vchar: str = "",
    callback: object = None,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    skip_subset_fonts: bool = False,
    ignore_cache: bool = False,
    lang_from: str = "en",
    lang_to: str = "zh-CN",
    **kwarg: Any,
):
    # 只保留基本字体配置
    font_list = [("tiro", None)]  # 拉丁字体

    # 加载思源字体
    cjk_font_path = download_remote_fonts()
    font_list.append(("SourceHanSerifCN", cjk_font_path))

    doc_en = Document(stream=stream)
    stream = io.BytesIO()
    doc_en.save(stream)
    doc_zh = Document(stream=stream)
    page_count = doc_zh.page_count

    # 字体注册
    font_id = {}
    for page in doc_zh:
        for font in font_list:
            font_id[font[0]] = page.insert_font(font[0], font[1])
    xreflen = doc_zh.xref_length()
    for xref in range(1, xreflen):
        for label in ["Resources/", ""]:  # 可能是基于 xobj 的 res
            try:  # xref 读写可能出错
                font_res = doc_zh.xref_get_key(xref, f"{label}Font")
                target_key_prefix = f"{label}Font/"
                if font_res[0] == "xref":
                    resource_xref_id = re.search("(\\d+) 0 R", font_res[1]).group(1)
                    xref = int(resource_xref_id)
                    font_res = ("dict", doc_zh.xref_object(xref))
                    target_key_prefix = ""

                if font_res[0] == "dict":
                    for font in font_list:
                        target_key = f"{target_key_prefix}{font[0]}"
                        font_exist = doc_zh.xref_get_key(xref, target_key)
                        if font_exist[0] == "null":
                            doc_zh.xref_set_key(
                                xref,
                                target_key,
                                f"{font_id[font[0]]} 0 R",
                            )
            except Exception:
                pass

    # 处理翻译
    if not envs:
        envs = {}
    # 从 ConfigManager 获取翻译器配置
    translator_envs = ConfigManager.get_instance().get_translator_config(service)
    if translator_envs:
        envs.update(translator_envs)

    fp = io.BytesIO()

    doc_zh.save(fp)
    # 确保传递语言参数
    obj_patch: dict = translate_patch(
        fp,
        pages=pages,
        vfont=vfont,
        vchar=vchar,
        thread=thread,
        doc_zh=doc_zh,
        service=service,
        callback=callback,
        cancellation_event=cancellation_event,
        model=model,
        envs=envs,
        prompt=prompt,
        ignore_cache=ignore_cache,
        lang_from=lang_from,
        lang_to=lang_to,
    )

    for obj_id, ops_new in obj_patch.items():
        # ops_old=doc_en.xref_stream(obj_id)
        # print(obj_id)
        # print(ops_old)
        # print(ops_new.encode())
        doc_zh.update_stream(obj_id, ops_new.encode())

    doc_en.insert_file(doc_zh)
    for id in range(page_count):
        doc_en.move_page(page_count + id, id * 2 + 1)
    if not skip_subset_fonts:
        doc_zh.subset_fonts(fallback=True)
        doc_en.subset_fonts(fallback=True)
    return (
        doc_zh.write(deflate=True, garbage=3, use_objstms=1),
        doc_en.write(deflate=True, garbage=3, use_objstms=1),
    )


def convert_to_pdfa(input_path, output_path):
    """
    Convert PDF to PDF/A format

    Args:
        input_path: Path to source PDF file
        output_path: Path to save PDF/A file
    """
    from pikepdf import Dictionary, Name, Pdf

    # Open the PDF file
    pdf = Pdf.open(input_path)

    # Add PDF/A conformance metadata
    metadata = {
        "pdfa_part": "2",
        "pdfa_conformance": "B",
        "title": pdf.docinfo.get("/Title", ""),
        "author": pdf.docinfo.get("/Author", ""),
        "creator": "PDF Math Translate",
    }

    with pdf.open_metadata() as meta:
        meta.load_from_docinfo(pdf.docinfo)
        meta["pdfaid:part"] = metadata["pdfa_part"]
        meta["pdfaid:conformance"] = metadata["pdfa_conformance"]

    # Create OutputIntent dictionary
    output_intent = Dictionary(
        {
            "/Type": Name("/OutputIntent"),
            "/S": Name("/GTS_PDFA1"),
            "/OutputConditionIdentifier": "sRGB IEC61966-2.1",
            "/RegistryName": "http://www.color.org",
            "/Info": "sRGB IEC61966-2.1",
        }
    )

    # Add output intent to PDF root
    if "/OutputIntents" not in pdf.Root:
        pdf.Root.OutputIntents = [output_intent]
    else:
        pdf.Root.OutputIntents.append(output_intent)

    # Save as PDF/A
    pdf.save(output_path, linearize=True)
    pdf.close()


def translate(
    files: list[str],
    output: str = "",
    pages: Optional[list[int]] = None,
    service: str = "",
    thread: int = 0,
    vfont: str = "",
    vchar: str = "",
    callback: object = None,
    compatible: bool = False,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    skip_subset_fonts: bool = False,
    ignore_cache: bool = False,
    lang_from: str = "en",
    lang_to: str = "zh-CN",
    **kwarg: Any,
):
    if not files:
        raise PDFValueError("No files to process.")

    missing_files = check_files(files)

    if missing_files:
        print("The following files do not exist:", file=sys.stderr)
        for file in missing_files:
            print(f"  {file}", file=sys.stderr)
        raise PDFValueError("Some files do not exist.")

    result_files = []

    for file in files:
        if type(file) is str and (
            file.startswith("http://") or file.startswith("https://")
        ):
            print("Online files detected, downloading...")
            try:
                r = requests.get(file, allow_redirects=True)
                if r.status_code == 200:
                    with tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False
                    ) as tmp_file:
                        print(f"Writing the file: {file}...")
                        tmp_file.write(r.content)
                        file = tmp_file.name
                else:
                    r.raise_for_status()
            except Exception as e:
                raise PDFValueError(
                    f"Errors occur in downloading the PDF file. Please check the link(s).\nError:\n{e}"
                )
        filename = os.path.splitext(os.path.basename(file))[0]

        # If the commandline has specified converting to PDF/A format
        # --compatible / -cp
        if compatible:
            with tempfile.NamedTemporaryFile(
                suffix="-pdfa.pdf", delete=False
            ) as tmp_pdfa:
                print(f"Converting {file} to PDF/A format...")
                convert_to_pdfa(file, tmp_pdfa.name)
                doc_raw = open(tmp_pdfa.name, "rb")
                os.unlink(tmp_pdfa.name)
        else:
            doc_raw = open(file, "rb")
        s_raw = doc_raw.read()
        doc_raw.close()

        temp_dir = Path(tempfile.gettempdir())
        file_path = Path(file)
        try:
            if file_path.exists() and file_path.resolve().is_relative_to(
                temp_dir.resolve()
            ):
                file_path.unlink(missing_ok=True)
                logger.debug(f"Cleaned temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean temp file {file_path}", exc_info=True)

        s_mono, s_dual = translate_stream(
            stream=s_raw,
            pages=pages,
            service=service,
            thread=thread,
            vfont=vfont,
            vchar=vchar,
            callback=callback,
            cancellation_event=cancellation_event,
            model=model,
            envs=envs,
            prompt=prompt,
            skip_subset_fonts=skip_subset_fonts,
            ignore_cache=ignore_cache,
            lang_from=lang_from,
            lang_to=lang_to,
        )
        file_mono = Path(output) / f"{filename}-mono.pdf"
        file_dual = Path(output) / f"{filename}-dual.pdf"
        doc_mono = open(file_mono, "wb")
        doc_dual = open(file_dual, "wb")
        doc_mono.write(s_mono)
        doc_dual.write(s_dual)
        doc_mono.close()
        doc_dual.close()
        result_files.append((str(file_mono), str(file_dual)))

    return result_files


def download_remote_fonts() -> str:
    """下载并返回思源字体路径"""
    font_name = "SourceHanSerifCN-Regular.ttf"
    # 使用 ConfigManager 获取字体路径配置
    font_path = ConfigManager.get_instance()._config_data.get("CJK_FONT_PATH", Path("/app", font_name).as_posix())

    if not Path(font_path).exists():
        font_path, _ = get_font_and_metadata(font_name)
        font_path = font_path.as_posix()
        # 更新配置
        with ConfigManager.get_instance()._lock:
            ConfigManager.get_instance()._config_data["CJK_FONT_PATH"] = font_path
            ConfigManager.get_instance()._save_config()

    logger.info(f"use font: {font_path}")

    return font_path