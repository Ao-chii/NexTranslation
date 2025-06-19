<h1 align="center">NexTranslation</h1>


<p align="center">
  📖 一个能够保留文档排版的智能 PDF 文档翻译工具，支持 GUI 和命令行操作。
</p>

`NexTranslation` 旨在解决翻译 PDF 文档时排版混乱的痛点。它利用先进的文档布局分析技术，能够精确识别文本块、图片、表格甚至公式，在翻译后尽可能地还原文档的原始外观，提供流畅的阅读体验。

## ✨ 核心功能

- **保留布局**: 翻译后精确重建原始 PDF 的排版和布局。
- **多翻译引擎**: 支持 Google、OpenAI (GPT)、DeepL 等多种翻译服务。
- **图形用户界面 (GUI)**: 提供简洁易用的图形界面，方便非技术用户操作。
- **命令行支持**: 为开发者和高级用户提供强大的命令行工具。
- **双语/单语输出**: 可同时生成仅译文和中英对照两种格式的 PDF 文件。
- **智能识别**: 自动识别并保留文档中的公式、特殊字符，避免错误翻译。
- **缓存机制**: 自动缓存已翻译内容，重复翻译时无需再次请求，节省时间和成本。
- **高度可定制**: 支持自定义翻译提示（Prompt），满足个性化的翻译需求。

## 🚀 安装

通过 TestPyPI 可以轻松安装 NexTranslation：

```bash
pip install -i https://test.pypi.org/simple/ NexTranslation
```
如果安装后显示`ERROR: No matching distribution found for babeldoc==0.3.59`，可以自己尝试以下命令或者直接无视该错误：
```bash
pip install babeldoc==0.3.59
```

## ⚙️ 配置

首次运行 NexTranslation 时，程序会自动在用户主目录下创建配置文件。您需要在此文件中填入所使用翻译服务的 API 密钥。

- **配置文件路径**:
  - **Windows**: `C:\\Users\\<你的用户名>\\.config\\NexTranslation\\config.json`
  - **Linux / macOS**: `~/.config/NexTranslation/config.json`

- **默认配置内容 (`config.json`)**:
  ```json
  {
      "translators": [
          {
              "name": "google",
              "envs": {}
          },
          {
              "name": "openai",
              "envs": {
                  "OPENAI_API_KEY": "sk-...",
                  "OPENAI_MODEL": "gpt-4"
              }
          },
          {
              "name": "deepl",
              "envs": {
                  "DEEPL_API_KEY": "your_deepl_key..."
              }
          }
      ],
      "ENABLED_SERVICES": ["google", "openai", "deepl"],
      "DEFAULT_SERVICE": "google",
      "HIDDEN_GRADIO_DETAILS": false,
      "DEMO_MODE": false
  }
  ```

请根据需要，将 `OPENAI_API_KEY` 和 `DEEPL_API_KEY` 的值替换为您自己的密钥。

## 📖 使用方法

NexTranslation 提供两种操作模式：图形用户界面 (GUI) 和命令行界面 (CLI)。

### 1. 图形用户界面 (GUI)

直接在终端输入以下命令即可启动 GUI：

```bash
nex-translate --gui
```

GUI 提供了所有核心功能的可视化操作，包括：
1. 选择文件: 通过点击"选择文件"按钮或直接将PDF文件拖拽到程序窗口。
2. 配置参数 (可选):
    - 页面范围: 选择"全部"、"首页"或自定义范围（如1-5, 8, 10-12）。
    - 输出模式: 选择生成"单语（纯中文）"或"双语（英中对照）"文档。
    - 高级选项: 翻译线程、是否忽略翻译缓存等等。
3. 开始翻译: 点击"开始翻译"按钮。
4. 查看进度: 界面上会显示当前处理状态、进度条和耗时信息。
5. 获取结果: 任务完成后，程序会自动在源文件目录生成译文PDF，用户可以预览结果并提供下载文件的链接。

### 2. 命令行界面 (CLI)

对于习惯使用命令行的用户，NexTranslation 提供了丰富的参数选项。

```bash
# 基本用法 (使用默认配置的服务翻译整个文档)
nex-translate your_document.pdf

# 指定翻译服务为 OpenAI
nex-translate your_document.pdf --service openai

# 翻译特定页面 (例如第1、3页以及第5到7页)
nex-translate your_document.pdf --pages 1,3,5-7

# 指定输出目录
nex-translate your_document.pdf -o translated_files

# 强制重新翻译，忽略缓存
nex-translate your_document.pdf --ignore-cache

# 获取所有可用选项
nex-translate --help
```

## 🛠️ 命令行选项

```
usage: nex-translate [-h] [--output OUTPUT] [--pages PAGES] [--service SERVICE] [--thread THREAD] [--vfont VFONT] [--vchar VCHAR] [--compatible] [--prompt PROMPT] [--ignore-cache]
                     [--skip-subset-fonts] [--debug] [--version] [--gui]
                     [files ...]

NexTranslation: 翻译 PDF 文档并保留布局。

positional arguments:
  files                 一个或多个输入 PDF 文件的路径。

options:
  -h, --help            提供帮助信息
  --output OUTPUT, -o OUTPUT
                        保存翻译后 PDF 文件的目录。 (default: output)
  --pages PAGES, -p PAGES
                        指定要翻译的页面范围，例如 '1,3,5-7'。如果未指定，则翻译所有页面。 (default: None)
  --service SERVICE, -s SERVICE
                        要使用的翻译服务（例如 'google', 'openai', 'deepl'）。覆盖配置中的默认值。 (default: None)
  --thread THREAD, -t THREAD
                        用于并行翻译的线程数。 (default: 4)
  --vfont VFONT, -f VFONT
                        用于匹配被视为公式一部分的字体名称的正则表达式模式。 (default: )
  --vchar VCHAR, -c VCHAR
                        用于匹配被视为公式一部分的字符的正则表达式模式。 (default: )
  --compatible, -cp     将输出 PDF 转换为 PDF/A 格式以提高兼容性（需要 pikepdf）。 (default: False)
  --prompt PROMPT       用于翻译的自定义提示模板文件的路径。 (default: None)
  --ignore-cache        忽略现有的翻译缓存并强制重新翻译。 (default: False)
  --skip-subset-fonts   在输出 PDF 中跳过字体子集化（可能会增加文件大小）。 (default: False)
  --debug, -d           启用详细的调试日志记录。 (default: False)
  --version, -v         显示程序版本号
  --gui                 启动图形用户界面 (GUI) 模式。 (default: False)
```

## 📄 许可证

本项目采用 GPL-3.0 许可证。详情请见 `LICENSE` 文件。

