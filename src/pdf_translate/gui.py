import sys
from pathlib import Path

sys.path.append('src/nex_translation')
import gradio as gr
from gradio_pdf import PDF
import logging
import os
import asyncio
from typing import Optional, Dict, Any
from threading import Event
import uuid
import shutil


from nex_translation.core.doclayout import ModelInstance

# 导入项目内部模块
from nex_translation.core.google_translator import (
    GoogleTranslator,
)
from nex_translation.core.pdf_processor import translate
from nex_translation.infrastructure.config import ConfigManager

# 配置日志
logger = logging.getLogger(__name__)

# 自定义样式
CUSTOM_CSS = """
.container {
    max-width: 1200px;
    margin: auto;
}
.output-panel {
    min-height: 400px;
}
.progress-bar {
    width: 100%;
    height: 20px;
    background-color: #f0f0f0;
    border-radius: 10px;
    overflow: hidden;
}
.progress-bar-fill {
    height: 100%;
    background-color: #4CAF50;
    transition: width 0.3s ease-in-out;
}
"""

class TranslationService:
    """翻译服务管理类"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.supported_services = {
            "google": {
                "name": "Google翻译",
                "class": GoogleTranslator,
                "requires_key": False
            }
        }
        
        self.supported_languages = {
            "en": "English",
            "zh": "简体中文",
            "zh-tw": "繁體中文",
            "ja": "日本語",
            "ko": "한국어",
            "fr": "Français",
            "de": "Deutsch",
            "es": "Español",
            "ru": "Русский",
        }

    def get_translator(self, service_name: str, api_key: Optional[str] = None) -> Any:
        """获取翻译器实例"""
        service_info = self.supported_services.get(service_name)
        if not service_info:
            raise ValueError(f"不支持的翻译服务: {service_name}")
            
        if service_info["requires_key"] and not api_key:
            raise ValueError(f"{service_info['name']}需要API密钥")
            
        return service_info["class"](api_key) if api_key else service_info["class"]()

class PDFTranslator:
    """PDF翻译器界面类"""
    
    def __init__(self):
        self.translation_service = TranslationService()
        self.model_instance = ModelInstance()
        self.current_file = None
        self.cancel_event = Event()
        
    def create_interface(self):
        """创建Gradio界面"""
        with gr.Blocks(css=CUSTOM_CSS) as interface:
            gr.Markdown("# PDF翻译工具")
            
            with gr.Row():
                with gr.Column(scale=2):
                    # 输入区域
                    file_input = gr.File(
                        label="选择PDF文件",
                        file_types=[".pdf"],
                        type="file"
                    )
                    
                    with gr.Row():
                        # 翻译服务选择
                        service_dropdown = gr.Dropdown(
                            choices=list(self.translation_service.supported_services.keys()),
                            value="google",
                            label="翻译服务"
                        )
                        # API密钥输入(可选)
                        api_key_input = gr.Textbox(
                            label="API密钥(可选)",
                            type="password",
                            visible=False
                        )
                    
                    with gr.Row():
                        # 源语言和目标语言选择
                        source_lang = gr.Dropdown(
                            choices=list(self.translation_service.supported_languages.keys()),
                            value="en",
                            label="源语言"
                        )
                        target_lang = gr.Dropdown(
                            choices=list(self.translation_service.supported_languages.keys()),
                            value="zh",
                            label="目标语言"
                        )
                    
                    # 输出格式选择
                    output_format = gr.Radio(
                        choices=["双语对照", "纯译文"],
                        value="双语对照",
                        label="输出格式"
                    )
                    
                    # 进度显示
                    progress = gr.Progress()
                    status_text = gr.Textbox(label="状态", interactive=False)
                    
                    with gr.Row():
                        # 控制按钮
                        translate_btn = gr.Button("开始翻译", variant="primary")
                        cancel_btn = gr.Button("取消", variant="secondary")
                
                with gr.Column(scale=3):
                    # 预览区域
                    preview = PDF(label="预览", visible=False)
                    output_file = gr.File(label="下载翻译结果")
            
            # 事件处理
            def update_api_key_visibility(service):
                """根据选择的服务更新API密钥输入框可见性"""
                service_info = self.translation_service.supported_services.get(service)
                return gr.update(visible=service_info["requires_key"])
            
            async def translate_pdf(
                file, service, api_key, src_lang, tgt_lang, out_format, progress=gr.Progress()
            ):
                """执行PDF翻译"""
                if not file:
                    return None, "请选择PDF文件"
                
                try:
                    # 重置取消事件
                    self.cancel_event.clear()
                    
                    # 创建临时文件路径
                    temp_dir = Path("temp") / str(uuid.uuid4())
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    input_path = temp_dir / "input.pdf"
                    output_path = temp_dir / "output.pdf"
                    
                    # 保存上传的文件
                    shutil.copy(file.name, input_path)
                    
                    # 获取翻译器实例
                    translator = self.translation_service.get_translator(service, api_key)
                    
                    # 翻译参数
                    params = {
                        "lang_in": src_lang,
                        "lang_out": tgt_lang,
                        "service": service,
                        "model": self.model_instance,
                        "bilingual": out_format == "双语对照",
                        "callback": lambda p: progress(p),
                        "cancellation_event": self.cancel_event
                    }
                    
                    # 执行翻译
                    await translate(str(input_path), str(output_path), **params)
                    
                    # 返回结果
                    return output_path, "翻译完成"
                    
                except Exception as e:
                    logger.error(f"翻译失败: {e}")
                    return None, f"翻译失败: {str(e)}"
                    
                finally:
                    # 清理临时文件
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
            
            def cancel_translation():
                """取消翻译任务"""
                self.cancel_event.set()
                return "已取消翻译任务"
            
            # 绑定事件
            service_dropdown.change(
                update_api_key_visibility,
                inputs=[service_dropdown],
                outputs=[api_key_input]
            )
            
            translate_btn.click(
                translate_pdf,
                inputs=[
                    file_input,
                    service_dropdown,
                    api_key_input,
                    source_lang,
                    target_lang,
                    output_format
                ],
                outputs=[output_file, status_text]
            )
            
            cancel_btn.click(
                cancel_translation,
                outputs=[status_text]
            )
            
            return interface

def launch_gui():
    """启动GUI应用"""
    translator = PDFTranslator()
    interface = translator.create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True
    )

if __name__ == "__main__":
    launch_gui()



