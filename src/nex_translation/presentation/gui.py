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

from nex_translation.core import __version__
from nex_translation.core.pdf_processor import translate
from nex_translation.core.doclayout import ModelInstance
from nex_translation.infrastructure.config import ConfigManager
from nex_translation.core.translator import BaseTranslator
from nex_translation.core.google_translator import GoogleTranslator
from nex_translation.core.doclayout import OnnxModel
model = OnnxModel.load_available()
ModelInstance.value = model
logger = logging.getLogger(__name__)
from babeldoc.docvision.doclayout import OnnxModel
# The following variables associate strings with translators
service_map: dict[str, BaseTranslator] = {
    "Google": GoogleTranslator,
}

# The following variables associate strings with specific languages
lang_map = {
    "Simplified Chinese": "zh",
    "Traditional Chinese": "zh-TW",
    "English": "en",
    "French": "fr",
    "German": "de",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "Spanish": "es",
    "Italian": "it",
}

# The following variable associate strings with page ranges
page_map = {
    "All": None,
    "First": [0],
    "First 5 pages": list(range(0, 5)),
    "Others": None,
}


flag_demo = False

# Limit resources
if ConfigManager.get("src_DEMO"):
    flag_demo = True
    service_map = {
        "Google": GoogleTranslator,
    }
    page_map = {
        "First": [0],
        "First 20 pages": list(range(0, 20)),
    }
    client_key = ConfigManager.get("src_CLIENT_KEY")
    server_key = ConfigManager.get("src_SERVER_KEY")


# Limit Enabled Services
enabled_services: T.Optional[T.List[str]] = ConfigManager.get("ENABLED_SERVICES")
if isinstance(enabled_services, list):
    default_services = ["Google", "Bing"]
    enabled_services_names = [str(_).lower().strip() for _ in enabled_services]
    enabled_services = [
        k
        for k in service_map.keys()
        if str(k).lower().strip() in enabled_services_names
    ]
    if len(enabled_services) == 0:
        raise RuntimeError(f"No services available.")
    enabled_services = default_services + enabled_services
else:
    enabled_services = list(service_map.keys())


# Configure about Gradio show keys
hidden_gradio_details: bool = bool(ConfigManager.get("HIDDEN_GRADIO_DETAILS"))


# Public demo control
def verify_recaptcha(response):
    """
    This function verifies the reCAPTCHA response.
    """
    recaptcha_url = "https://www.google.com/recaptcha/api/siteverify"
    data = {"secret": server_key, "response": response}
    result = requests.post(recaptcha_url, data=data).json()
    return result.get("success")


def download_with_limit(url: str, save_path: str, size_limit: int) -> str:
    """
    This function downloads a file from a URL and saves it to a specified path.

    Inputs:
        - url: The URL to download the file from
        - save_path: The path to save the file to
        - size_limit: The maximum size of the file to download

    Returns:
        - The path of the downloaded file
    """
    chunk_size = 1024
    total_size = 0
    with requests.get(url, stream=True, timeout=10) as response:
        response.raise_for_status()
        content = response.headers.get("Content-Disposition")
        try:  # filename from header
            _, params = cgi.parse_header(content)
            filename = params["filename"]
        except Exception:  # filename from url
            filename = os.path.basename(url)
        filename = os.path.splitext(os.path.basename(filename))[0] + ".pdf"
        with open(save_path / filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                total_size += len(chunk)
                if size_limit and total_size > size_limit:
                    raise gr.Error("Exceeds file size limit")
                file.write(chunk)
    return save_path / filename


def stop_translate_file(state: dict) -> None:
    """
    This function stops the translation process.

    Inputs:
        - state: The state of the translation process

    Returns:- None
    """
    session_id = state["session_id"]
    if session_id is None:
        return
    if session_id in cancellation_event_map:
        logger.info(f"Stopping translation for session {session_id}")
        cancellation_event_map[session_id].set()


def translate_file(
    file_type,
    file_input,
    link_input,
    service,
    lang_from,
    lang_to,
    page_range,
    page_input,
    prompt,
    threads,
    skip_subset_fonts,
    ignore_cache,
    use_babeldoc,
    recaptcha_response,
    state,
    progress=gr.Progress(),
    *envs,
):
    """
    This function translates a PDF file from one language to another.

    Inputs:
        - file_type: The type of file to translate
        - file_input: The file to translate
        - link_input: The link to the file to translate
        - service: The translation service to use
        - lang_from: The language to translate from
        - lang_to: The language to translate to
        - page_range: The range of pages to translate
        - page_input: The input for the page range
        - prompt: The custom prompt for the llm
        - threads: The number of threads to use
        - recaptcha_response: The reCAPTCHA response
        - state: The state of the translation process
        - progress: The progress bar
        - envs: The environment variables

    Returns:
        - The translated file
        - The translated file
        - The translated file
        - The progress bar
        - The progress bar
        - The progress bar
    """
    session_id = uuid.uuid4()
    state["session_id"] = session_id
    cancellation_event_map[session_id] = asyncio.Event()
    # Translate PDF content using selected service.
    if flag_demo and not verify_recaptcha(recaptcha_response):
        raise gr.Error("reCAPTCHA fail")

    progress(0, desc="Starting translation...")

    output = Path("src_files")
    output.mkdir(parents=True, exist_ok=True)

    if file_type == "File":
        if not file_input:
            raise gr.Error("No input")
        file_path = shutil.copy(file_input, output)
    else:
        if not link_input:
            raise gr.Error("No input")
        file_path = download_with_limit(
            link_input,
            output,
            5 * 1024 * 1024 if flag_demo else None,
        )

    filename = os.path.splitext(os.path.basename(file_path))[0]
    file_raw = output / f"{filename}.pdf"
    file_mono = output / f"{filename}-mono.pdf"
    file_dual = output / f"{filename}-dual.pdf"

    translator = service_map[service]
    if page_range != "Others":
        selected_page = page_map[page_range]
    else:
        selected_page = []
        for p in page_input.split(","):
            if "-" in p:
                start, end = p.split("-")
                selected_page.extend(range(int(start) - 1, int(end)))
            else:
                selected_page.append(int(p) - 1)
    lang_from = lang_map[lang_from]
    lang_to = lang_map[lang_to]

    _envs = {}
    for i, env in enumerate(translator.envs.items()):
        _envs[env[0]] = envs[i]
    for k, v in _envs.items():
        if str(k).upper().endswith("API_KEY") and str(v) == "***":
            # Load Real API_KEYs from local configure file
            real_keys: str = ConfigManager.get_env_by_translatername(
                translator, k, None
            )
            _envs[k] = real_keys

    print(f"Files before translation: {os.listdir(output)}")

    def progress_bar(t: tqdm.tqdm):
        desc = getattr(t, "desc", "Translating...")
        if desc == "":
            desc = "Translating..."
        progress(t.n / t.total, desc=desc)

    try:
        threads = int(threads)
    except ValueError:
        threads = 1

    param = {
        "files": [str(file_raw)],
        "pages": selected_page,
        "lang_in": lang_from,
        "lang_out": lang_to,
        "service": f"{translator.name}",
        "output": output,
        "thread": int(threads),
        "callback": progress_bar,
        "cancellation_event": cancellation_event_map[session_id],
        "envs": _envs,
        "prompt": Template(prompt) if prompt else None,
        "skip_subset_fonts": skip_subset_fonts,
        "ignore_cache": ignore_cache,
        "model": ModelInstance.value,
    }

    translate(**param)
    print(f"Files after translation: {os.listdir(output)}")

    if not file_mono.exists() or not file_dual.exists():
        raise gr.Error("No output")

    progress(1.0, desc="Translation complete!")

    return (
        str(file_mono),
        str(file_mono),
        str(file_dual),
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(visible=True),
    )

# Global setup
custom_blue = gr.themes.Color(
    c50="#E8F3FF",
    c100="#BEDAFF",
    c200="#94BFFF",
    c300="#6AA1FF",
    c400="#4080FF",
    c500="#165DFF",  # Primary color
    c600="#0E42D2",
    c700="#0A2BA6",
    c800="#061D79",
    c900="#03114D",
    c950="#020B33",
)

custom_css = """
    .secondary-text {color: #999 !important;}
    footer {visibility: hidden}
    .env-warning {color: #dd5500 !important;}
    .env-success {color: #559900 !important;}

    /* Add dashed border to input-file class */
    .input-file {
        border: 1.2px dashed #165DFF !important;
        border-radius: 6px !important;
    }

    .progress-bar-wrap {
        border-radius: 8px !important;
    }

    .progress-bar {
        border-radius: 8px !important;
    }

    .pdf-canvas canvas {
        width: 100%;
    }
    """

demo_recaptcha = """
    <script src="https://www.google.com/recaptcha/api.js?render=explicit" async defer></script>
    <script type="text/javascript">
        var onVerify = function(token) {
            el=document.getElementById('verify').getElementsByTagName('textarea')[0];
            el.value=token;
            el.dispatchEvent(new Event('input'));
        };
    </script>
    """

from babeldoc import __version__ as babeldoc_version


cancellation_event_map = {}


# The following code creates the GUI
with gr.Blocks(
    title="NexTranslation",
    theme=gr.themes.Default(
        primary_hue=custom_blue, spacing_size="lg", radius_size="md"
    ),
    css=custom_css,
    head="",
) as demo:
    gr.Markdown(
        "# [NexTranslation @ GitHub](https://github.com/Ao-chii/NexTranslation)"
    )
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## File | < 5 MB" if flag_demo else "## File")
            file_type = gr.Radio(
                choices=["File", "Link"],
                label="Type",
                value="File",
                visible=False,
            )
            file_input = gr.File(
                label="input a file",
                file_count="single",
                file_types=[".pdf"],
                type="filepath",
                elem_classes=["input-file"],
            )
            link_input = gr.Textbox(
                label="Link",
                visible=False,
                interactive=True,
            )
            service = gr.Dropdown(
                label="Service",
                choices=enabled_services,
                visible = False,
                value=enabled_services[0],
            )
            envs = []
            for i in range(3):
                envs.append(
                    gr.Textbox(
                        visible=False,
                        interactive=True,
                    )
                )
            lang_from = gr.Dropdown(
                label="Translate from",
                choices=lang_map.keys(),
                value=ConfigManager.get("src_LANG_FROM", "English"),
                visible=False,
            )
            lang_to = gr.Dropdown(
                label="Translate to",
                choices=lang_map.keys(),
                value=ConfigManager.get("src_LANG_TO", "Simplified Chinese"),
                visible=False,
            )
            page_range = gr.Radio(
                choices=page_map.keys(),
                label="Pages",
                value=list(page_map.keys())[0],
            )

            page_input = gr.Textbox(
                label="Page range",
                visible=False,
                interactive=True,
            )

            with gr.Accordion("Open for More Experimental Options!", open=False, visible=False):
                visible=False,
                gr.Markdown("#### Experimental")
                threads = gr.Textbox(
                    label="number of threads", interactive=True, value="4"
                )
                skip_subset_fonts = gr.Checkbox(
                    label="Skip font subsetting", interactive=True, value=False
                )
                ignore_cache = gr.Checkbox(
                    label="Ignore cache", interactive=True, value=False
                )
                prompt = gr.Textbox(
                    label="Custom Prompt for llm", interactive=True, visible=False
                )
                use_babeldoc = gr.Checkbox(
                    label="Use BabelDOC", interactive=True, value=False
                )
                envs.append(prompt)

            def on_select_service(service, evt: gr.EventData):
                translator = service_map[service]
                _envs = []
                for i in range(4):
                    _envs.append(gr.update(visible=False, value=""))
                for i, env in enumerate(translator.envs.items()):
                    label = env[0]
                    value = ConfigManager.get_env_by_translatername(
                        translator, env[0], env[1]
                    )
                    visible = True
                    if hidden_gradio_details:
                        if (
                            "MODEL" not in str(label).upper()
                            and value
                            and hidden_gradio_details
                        ):
                            visible = False
                        # Hidden Keys From Gradio
                        if "API_KEY" in label.upper():
                            value = "***"  # We use "***" Present Real API_KEY
                    _envs[i] = gr.update(
                        visible=visible,
                        label=label,
                        value=value,
                    )
                _envs[-1] = gr.update(visible=translator.CustomPrompt)
                return _envs

            def on_select_filetype(file_type):
                return (
                    gr.update(visible=file_type == "File"),
                    gr.update(visible=file_type == "Link"),
                )

            def on_select_page(choice):
                if choice == "Others":
                    return gr.update(visible=True)
                else:
                    return gr.update(visible=False)

            output_title = gr.Markdown("## Translated Sussessfully", visible=False)
            output_file_mono = gr.File(
                label="Download Translation (Mono)", visible=False
            )
            output_file_dual = gr.File(
                label="Download Translation (Dual)", visible=False
            )
            recaptcha_response = gr.Textbox(
                label="reCAPTCHA Response", elem_id="verify", visible=False
            )
            recaptcha_box = gr.HTML('<div id="recaptcha-box"></div>')
            translate_btn = gr.Button("Translate", variant="primary")
            cancellation_btn = gr.Button("Cancel", variant="secondary")
            page_range.select(on_select_page, page_range, page_input)
            service.select(
                on_select_service,
                service,
                envs,
            )
            file_type.select(
                on_select_filetype,
                file_type,
                [file_input, link_input],
                js=(
                    f"""
                    (a,b)=>{{
                        try{{
                            grecaptcha.render('recaptcha-box',{{
                                'sitekey':'{client_key}',
                                'callback':'onVerify'
                            }});
                        }}catch(error){{}}
                        return [a];
                    }}
                    """
                    if flag_demo
                    else ""
                ),
            )

        with gr.Column(scale=2):
            gr.Markdown("## Preview")
            preview = PDF(label="Document Preview", visible=True, height=2000)

    # Event handlers
    file_input.upload(
        lambda x: x,
        inputs=file_input,
        outputs=preview,
        js=(
            f"""
            (a,b)=>{{
                try{{
                    grecaptcha.render('recaptcha-box',{{
                        'sitekey':'{client_key}',
                        'callback':'onVerify'
                    }});
                }}catch(error){{}}
                return [a];
            }}
            """
            if flag_demo
            else ""
        ),
    )

    state = gr.State({"session_id": None})

    translate_btn.click(
        translate_file,
        inputs=[
            file_type,
            file_input,
            link_input,
            service,
            lang_from,
            lang_to,
            page_range,
            page_input,
            prompt,
            threads,
            skip_subset_fonts,
            ignore_cache,
            use_babeldoc,
            recaptcha_response,
            state,
            *envs,
        ],
        outputs=[
            output_file_mono,
            preview,
            output_file_dual,
            output_file_mono,
            output_file_dual,
            output_title,
        ],
    ).then(lambda: None, js="()=>{grecaptcha.reset()}" if flag_demo else "")

    cancellation_btn.click(
        stop_translate_file,
        inputs=[state],
    )

def setup_gui(server_port=7860) -> None:
    """
    Setup the GUI on local port 7860.

    Inputs:
        - server_port: The port to run the server on (default: 7860).

    Outputs:
        - None
    """
    try:
        demo.launch(
            server_name="127.0.0.1",
            debug=True,
            inbrowser=True,
            share=False,
            server_port=server_port,
        )
    except Exception as e:
        print(f"Error launching GUI: {str(e)}")
        print("Trying alternative launch method...")
        demo.launch(
            debug=True,
            inbrowser=True,
            server_port=server_port
        )


# For auto-reloading while developing
if __name__ == "__main__":
    logging.basicConfig()
    setup_gui()