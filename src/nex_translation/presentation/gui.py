import asyncio
import cgi
import os
import shutil
import uuid
from pathlib import Path
import typing as T

import gradio as gr
import requests
import tqdm
from gradio_pdf import PDF
from string import Template
import logging

from nex_translation import __version__
from nex_translation.core.pdf_processor import translate
from nex_translation.core.doclayout import ModelInstance
from nex_translation.infrastructure.config import ConfigManager
from nex_translation.core.translator import BaseTranslator
from nex_translation.core.google_translator import GoogleTranslator
from nex_translation.core.doclayout import OnnxModel

# --- 全局初始化 ---
# 加载模型
model = OnnxModel.load_available()
ModelInstance.value = model
logger = logging.getLogger(__name__)

# 获取配置管理器单例
config_manager = ConfigManager.get_instance()

# --- 服务与语言配置 ---
# 定义支持的翻译服务
service_map: dict[str, BaseTranslator] = {
    "Google": GoogleTranslator,
    # "OpenAI": OpenAITranslator, # 示例：可以添加更多服务
    # "DeepL": DeepLTranslator,  # 示例
}

# 固定的语言配置：英文到中文
LANG_FROM = "en"
LANG_TO = "zh"

# The following variable associate strings with page ranges
page_map = {
    "All": None,
    "First": [0],
    "First 5 pages": list(range(0, 5)),
    "Others": None,
}

# --- GUI 配置 ---
# 从配置加载启用的服务
enabled_services_names = config_manager.get_enabled_services()
enabled_services = [k for k in service_map.keys() if k.lower() in enabled_services_names]
if not enabled_services:
    # 如果没有可用的服务，可以抛出错误或默认使用第一个
    default_service = list(service_map.keys())[0]
    enabled_services.append(default_service)
    logger.warning(f"配置文件中未找到启用的服务，将使用默认服务: {default_service}")
else:
    default_service = config_manager.get_default_service()
    if default_service.capitalize() not in enabled_services:
        default_service = enabled_services[0]

# 是否隐藏Gradio界面中的敏感信息
hidden_gradio_details: bool = config_manager.get("HIDDEN_GRADIO_DETAILS", False)

# 全局取消事件映射
cancellation_event_map = {}

# --- 后端函数 ---
def stop_translate_file(state: dict) -> None:
    """停止翻译过程"""
    session_id = state.get("session_id")
    if session_id and session_id in cancellation_event_map:
        logger.info(f"正在停止会话 {session_id} 的翻译任务。")
        cancellation_event_map[session_id].set()


def translate_file(
    file_input,
    service,
    page_range,
    page_input,
    prompt,
    threads,
    skip_subset_fonts,
    ignore_cache,
    recaptcha_response,
    state,
    progress=gr.Progress(),
    *envs,
):
    """Gradio界面的翻译核心函数"""
    session_id = uuid.uuid4()
    state["session_id"] = session_id
    cancellation_event_map[session_id] = asyncio.Event()

    progress(0, desc="开始翻译...")

    if not file_input:
        raise gr.Error("没有输入文件，请上传一个PDF文件。")

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Gradio 的 file 组件返回的是一个临时路径，需要复制
    try:
        file_path = shutil.copy(file_input.name, output_dir)
    except AttributeError:
         raise gr.Error("文件输入无效，请重新上传。")

    filename = Path(file_path).stem
    file_mono = output_dir / f"{filename}-mono.pdf"
    file_dual = output_dir / f"{filename}-dual.pdf"

    translator_cls = service_map[service]

    # 解析页面范围
    if page_range == "自定义":
        selected_pages = []
        if page_input:
            try:
                for p_part in page_input.split(','):
                    p_part = p_part.strip()
                    if '-' in p_part:
                        start, end = map(int, p_part.split('-'))
                        selected_pages.extend(range(start - 1, end))
                    else:
                        selected_pages.append(int(p_part) - 1)
            except ValueError:
                raise gr.Error("无效的页面范围格式，请使用如 '1, 3-5' 的格式。")
    else:
        selected_pages = page_map[page_range]

    # 准备环境变量
    _envs = {}
    for i, (key, _) in enumerate(translator_cls.envs.items()):
        # 假设 envs 列表与 translator_cls.envs 的顺序匹配
        _envs[key] = envs[i]
        # 如果是API Key且界面上显示为***，从配置加载真实值
        if "API_KEY" in key.upper() and envs[i] == "***":
            real_key = config_manager.get_env_by_translatername(translator_cls, key)
            if not real_key:
                 raise gr.Error(f"未在配置中找到 {service} 的 API 密钥。")
            _envs[key] = real_key

    def progress_bar_callback(t: tqdm):
        """tqdm进度条的回调函数，用于更新Gradio的进度条"""
        desc = getattr(t, "desc", "正在翻译...")
        if not desc:
            desc = "正在翻译..."
        progress(t.n / t.total, desc=desc)

    try:
        # 准备翻译参数
        param = {
            "files": [str(file_path)],
            "pages": selected_pages,
            "lang_in": LANG_FROM,
            "lang_out": LANG_TO,
            "service": service.lower(), # 服务名称使用小写
            "output": str(output_dir),
            "thread": int(threads),
            "callback": progress_bar_callback,
            "cancellation_event": cancellation_event_map.get(session_id),
            "envs": _envs,
            "prompt": Template(prompt) if prompt else None,
            "skip_subset_fonts": skip_subset_fonts,
            "ignore_cache": ignore_cache,
            "model": ModelInstance.value,
        }
        
        # 调用核心翻译函数
        translate(**param)
        
        if not file_mono.exists() or not file_dual.exists():
            raise gr.Error("翻译输出文件未生成，请检查后台日志。")

        progress(1.0, desc="翻译完成！")

        return (
            str(file_mono), # 更新预览窗口
            gr.update(value=str(file_mono), visible=True), # 单语下载链接
            gr.update(value=str(file_dual), visible=True), # 双语下载链接
            gr.update(visible=True), # 显示标题
        )
    except Exception as e:
        logger.error(f"翻译过程中发生错误: {e}")
        # 在界面上向用户显示一个更友好的错误消息
        raise gr.Error(f"翻译失败: {e}")
    finally:
        # 清理取消事件
        if session_id in cancellation_event_map:
            del cancellation_event_map[session_id]

# --- GUI 布局 ---
custom_css = """
footer {visibility: hidden}
.input-file { border: 1.2px dashed #165DFF !important; border-radius: 6px !important; }
.progress-bar { border-radius: 8px !important; }
.pdf-canvas canvas { width: 100%; }
"""

with gr.Blocks(title="NexTranslation", css=custom_css) as demo:
    gr.Markdown("# NexTranslation - PDF文档翻译工具")
    gr.Markdown("专注于英文到中文的PDF文档翻译，保留原始布局。")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. 上传文件和选择服务")
            file_input = gr.File(
                label="上传PDF文件",
                file_count="single",
                file_types=[".pdf"],
                elem_classes=["input-file"],
            )
            
            service = gr.Dropdown(
                label="翻译服务",
                choices=enabled_services,
                value=default_service.capitalize(),
                interactive=True,
            )
            
            # 动态生成环境变量输入框
            envs_inputs = []
            with gr.Group() as envs_group:
                # 预先创建所有可能的输入框，然后根据选择的服务显示/隐藏
                for service_name, translator_cls in service_map.items():
                    for env_key, default_val in translator_cls.envs.items():
                        # 从配置加载值
                        config_val = config_manager.get_env_by_translatername(translator_cls, env_key, default_val)
                        
                        # 如果需要隐藏，且有值，则显示***
                        is_api_key = "API_KEY" in env_key.upper()
                        display_val = "***" if hidden_gradio_details and is_api_key and config_val else config_val
                        
                        textbox = gr.Textbox(
                            label=f"{service_name} - {env_key}",
                            value=display_val,
                            interactive=True,
                            visible=service_name.lower() == default_service.lower()
                        )
                        envs_inputs.append(textbox)

            gr.Markdown("### 2. 设置页面范围")
            page_range = gr.Radio(
                choices=list(page_map.keys()),
                label="页面范围",
                value="全部页面",
            )

            page_input = gr.Textbox(
                label="自定义页面",
                placeholder="例如: 1, 3-5",
                visible=False,
                interactive=True,
            )

            with gr.Accordion("高级选项", open=False):
                threads = gr.Slider(
                    label="翻译线程数", minimum=1, maximum=16, value=4, step=1
                )
                skip_subset_fonts = gr.Checkbox(
                    label="跳过字体子集化 (可减小文件大小但可能导致字符缺失)", value=False
                )
                ignore_cache = gr.Checkbox(
                    label="忽略翻译缓存", value=False
                )
                prompt = gr.Textbox(
                    label="自定义LLM提示 (留空使用默认)", lines=3
                )
                use_babeldoc = gr.Checkbox(
                    label="使用 BabelDOC (实验性)", value=False, visible=False # 暂时隐藏
                )

            translate_btn = gr.Button("开始翻译", variant="primary")
            cancellation_btn = gr.Button("取消", variant="secondary")

        with gr.Column(scale=2):
            gr.Markdown("### 3. 预览和下载")
            output_title = gr.Markdown("## 翻译结果", visible=False)
            preview = PDF(label="翻译预览", visible=True, height=2000)
            output_file_mono = gr.File(
                label="下载单语版本", visible=False
            )
            output_file_dual = gr.File(
                label="下载双语版本", visible=False
            )
    
    # --- 事件处理 ---
    state = gr.State({"session_id": None})
    
    # 文件上传后直接在预览窗口显示
    file_input.upload(lambda x: x, inputs=file_input, outputs=preview)

    # 切换页面范围选项时，显示/隐藏自定义输入框
    page_range.select(
        lambda choice: gr.update(visible=choice == "自定义"),
        inputs=page_range,
        outputs=page_input,
    )

    # 切换翻译服务时，更新环境变量输入框的可见性
    def on_select_service(service_choice):
        updates = []
        for service_name, translator_cls in service_map.items():
            for _ in translator_cls.envs:
                updates.append(gr.update(visible=service_name.lower() == service_choice.lower()))
        return updates if len(updates) > 1 else updates[0] # Gradio 需要正确的返回格式

    if len(envs_inputs) > 0:
        service.select(
            on_select_service,
            service,
            envs_inputs,
        )

    # 点击翻译按钮
    translate_btn.click(
        translate_file,
        inputs=[
            file_input, service, page_range, page_input,
            prompt, threads, skip_subset_fonts, ignore_cache, use_babeldoc,
            state, *envs_inputs
        ],
        outputs=[preview, output_file_mono, output_file_dual, output_title],
    )

    # 点击取消按钮
    cancellation_btn.click(stop_translate_file, inputs=[state])

# --- 启动函数 ---
def setup_gui(server_port=7860, share=False):
    """启动Gradio界面"""
    try:
        demo.launch(
            server_name="0.0.0.0", # 允许局域网访问
            server_port=server_port,
            inbrowser=True,
            share=share, # 控制是否创建公网链接
            debug=True,
        )
    except Exception as e:
        logger.error(f"启动Gradio界面失败: {e}")
        logger.info("尝试使用备用方式启动...")
        demo.launch(
            server_port=server_port,
            inbrowser=True,
            share=share,
            debug=True
        )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # 可以通过命令行参数控制端口和分享
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action='store_true')
    args = parser.parse_args()
    
    setup_gui(server_port=args.port, share=args.share)