#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
NexTranslation GUI模块
使用Gradio提供图形用户界面
"""

import os
import sys
import time
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
from string import Template

import gradio as gr
import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from ..utils.logger import get_logger
from ..infrastructure.config import ConfigManager
from ..core.pdf_processor import translate
from ..core.doclayout import OnnxModel, ModelInstance

# 获取日志记录器
logger = get_logger(__name__)

class TranslationProgress:
    """翻译进度跟踪类"""
    def __init__(self):
        self.progress = 0.0
        self.status = "准备中..."
        self.is_cancelled = False
        self.cancellation_event = asyncio.Event()
    
    def update(self, progress_bar: tqdm.tqdm) -> None:
        """更新进度"""
        self.progress = progress_bar.n / progress_bar.total if progress_bar.total else 0
        self.status = f"正在翻译... {int(self.progress * 100)}%"
        
    def cancel(self) -> None:
        """取消翻译"""
        self.is_cancelled = True
        self.cancellation_event.set()
        self.status = "已取消"
        
    def reset(self) -> None:
        """重置进度"""
        self.progress = 0.0
        self.status = "准备中..."
        self.is_cancelled = False
        self.cancellation_event = asyncio.Event()

def setup_gui(server_name: str = "0.0.0.0", server_port: int = 7860) -> None:
    """
    设置并启动GUI界面
    
    Args:
        server_name: 服务器名称/IP
        server_port: 服务器端口
    """
    # 获取配置管理器
    config_manager = ConfigManager.get_instance()
    
    # 获取已启用的翻译服务
    enabled_services = config_manager.get_enabled_services()
    default_service = config_manager.get_default_service()
    
    # 获取配置中的语言设置
    pdf_lang_from = config_manager._config_data.get("PDF_LANG_FROM", "English")
    pdf_lang_to = config_manager._config_data.get("PDF_LANG_TO", "Simplified Chinese")
    
    # 语言映射
    language_map = {
        "English": "en",
        "Chinese": "zh",
        "Simplified Chinese": "zh-CN",
        "Traditional Chinese": "zh-TW",
        "Japanese": "ja",
        "Korean": "ko",
        "French": "fr",
        "German": "de",
        "Spanish": "es",
        "Russian": "ru"
    }
    
    # 创建进度跟踪器
    progress_tracker = TranslationProgress()
    
    # 定义翻译函数
    async def translate_pdf(
        files: List[tempfile._TemporaryFileWrapper],
        service: str,
        lang_from: str,
        lang_to: str,
        thread_count: int,
        progress=gr.Progress()
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """
        异步翻译PDF文件
        
        Args:
            files: 上传的PDF文件列表
            service: 翻译服务
            lang_from: 源语言
            lang_to: 目标语言
            thread_count: 线程数
            progress: Gradio进度条
            
        Returns:
            状态消息和结果文件路径列表
        """
        if not files:
            return "请上传PDF文件", []
        
        # 重置进度
        progress_tracker.reset()
        
        # 创建临时输出目录
        output_dir = Path(tempfile.mkdtemp())
        
        # 准备文件路径列表
        file_paths = [f.name for f in files]
        file_names = [Path(f.name).name for f in files]
        
        # 获取语言代码
        lang_from_code = language_map.get(lang_from, "en")
        lang_to_code = language_map.get(lang_to, "zh-CN")
        
        # 获取模型实例
        model = ModelInstance.value
        
        try:
            # 更新状态
            progress_tracker.status = f"正在翻译 {len(file_paths)} 个文件..."
            progress(0, desc=progress_tracker.status)
            
            # 执行翻译
            result_files = await asyncio.to_thread(
                translate,
                files=file_paths,
                output=str(output_dir),
                service=service,
                thread=thread_count,
                cancellation_event=progress_tracker.cancellation_event,
                model=model,
                callback=progress_tracker.update,
                lang_from=lang_from_code,
                lang_to=lang_to_code
            )
            
            # 如果取消了，返回取消消息
            if progress_tracker.is_cancelled:
                return "翻译已取消", []
            
            # 更新状态
            progress_tracker.status = "翻译完成！"
            progress(1.0, desc=progress_tracker.status)
            
            # 返回结果
            return progress_tracker.status, result_files
            
        except Exception as e:
            logger.error(f"翻译过程中发生错误: {str(e)}")
            progress_tracker.status = f"翻译失败: {str(e)}"
            return progress_tracker.status, []
    
    # 定义取消翻译函数
    def cancel_translation() -> str:
        """取消正在进行的翻译"""
        progress_tracker.cancel()
        return "翻译已取消"
    
    # 创建Gradio界面
    with gr.Blocks(title="NexTranslation - PDF翻译工具") as app:
        gr.Markdown("# NexTranslation PDF翻译工具")
        gr.Markdown("上传PDF文件，选择翻译服务和语言，然后点击翻译按钮开始翻译。")
        
        with gr.Row():
            with gr.Column(scale=2):
                # 文件上传区域
                files_input = gr.File(
                    label="上传PDF文件",
                    file_types=[".pdf"],
                    file_count="multiple"
                )
                
                # 翻译设置
                with gr.Group():
                    gr.Markdown("### 翻译设置")
                    service_dropdown = gr.Dropdown(
                        choices=enabled_services,
                        value=default_service,
                        label="翻译服务"
                    )
                    
                    with gr.Row():
                        lang_from_dropdown = gr.Dropdown(
                            choices=list(language_map.keys()),
                            value=pdf_lang_from,
                            label="源语言"
                        )
                        lang_to_dropdown = gr.Dropdown(
                            choices=list(language_map.keys()),
                            value=pdf_lang_to,
                            label="目标语言"
                        )
                    
                    thread_slider = gr.Slider(
                        minimum=1,
                        maximum=16,
                        value=4,
                        step=1,
                        label="线程数"
                    )
                
                # 操作按钮
                with gr.Row():
                    translate_btn = gr.Button("开始翻译", variant="primary")
                    cancel_btn = gr.Button("取消翻译", variant="stop")
            
            with gr.Column(scale=1):
                # 状态和结果显示
                status_output = gr.Textbox(label="状态", value="准备就绪")
                
                # 结果文件列表
                result_files_output = gr.File(
                    label="翻译结果",
                    file_count="multiple",
                    type="file"
                )
        
        # 设置事件处理
        translate_btn.click(
            fn=translate_pdf,
            inputs=[
                files_input,
                service_dropdown,
                lang_from_dropdown,
                lang_to_dropdown,
                thread_slider
            ],
            outputs=[status_output, result_files_output]
        )
        
        cancel_btn.click(
            fn=cancel_translation,
            inputs=[],
            outputs=[status_output]
        )
        
        # 添加页脚
        gr.Markdown("### 关于")
        gr.Markdown("NexTranslation 是一个智能PDF翻译工具，支持保留原始布局和公式。")
    
    # 启动Gradio应用
    hidden_details = config_manager._config_data.get("HIDDEN_GRADIO_DETAILS", True)
    
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=False,
        inbrowser=True,
        show_api=False,
        show_error=True,
        quiet=hidden_details
    )
