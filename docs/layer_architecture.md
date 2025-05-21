# NexTranslation 架构设计文档

## 1. 引言

本文档旨在详细描述 NexTranslation 项目的软件架构。NexTranslation 是一个专注于英文到中文 PDF 文档翻译的工具，致力于在翻译过程中保持原始文档的布局和格式。本文档将概述系统的主要组件、它们之间的交互以及关键的设计决策。

## 2. 系统概述

NexTranslation 采用模块化设计，将系统划分为不同的层次和组件，以便于开发、维护和扩展。主要架构层次包括：

*   **表示层 (Presentation Layer)**：负责用户交互，提供命令行界面 (CLI) 和图形用户界面 (GUI)。
*   **核心层 (Core Layer)**：包含项目的主要业务逻辑，如 PDF 解析、布局分析、文本翻译和 PDF 重建。
*   **基础设施层 (Infrastructure Layer)**：提供底层支持功能，如配置管理和翻译缓存。
*   **工具层 (Utils Layer)**：包含通用的辅助工具，如日志记录和自定义异常处理。

## 3. 模块详细设计

### 3.1. 表示层 (`src/nex_translation/presentation`)

此层是用户与系统交互的入口。

*   **`gui.py`**:
    *   **功能**: 提供一个基于 Gradio 的图形用户界面，允许用户通过可视化界面上传 PDF 文件、选择翻译选项并查看翻译结果。
    *   **主要类/函数**:
        *   `translate_file()`: 处理 GUI 的文件上传、参数设置和调用核心翻译逻辑。
        *   `setup_gui()`: 初始化并启动 Gradio 应用。
    *   **交互**: 调用核心层的 `translate()` 函数执行翻译任务，并使用基础设施层的 `ConfigManager` 获取配置。

*   **`cli.py`**:
    *   **功能**: 提供一个命令行界面，允许用户通过命令行参数指定输入文件、输出目录和翻译选项。支持单个文件和批量文件处理。
    *   **主要类/函数**:
        *   `main()`: 解析命令行参数，调用核心翻译逻辑。
        *   `parse_page_ranges()`: 解析用户输入的页面范围字符串。
    *   **交互**: 调用核心层的 `translate()` 函数执行翻译任务，并使用基础设施层的 `ConfigManager` 和核心层的 `DocLayoutModel`。

### 3.2. 核心层 (`src/nex_translation/core`)

此层是系统的核心，实现了 PDF 翻译的主要流程。

*   **`pdf_processor.py`**:
    *   **功能**: 高层指挥模块，协调 PDF 文件的整个翻译流程，包括解析、翻译和导出。专注于英译中场景。
    *   **主要类/函数**:
        *   `translate()`: 处理单个或多个 PDF 文件的翻译，管理文件读写和调用 `translate_stream()`。
        *   `translate_stream()`: 处理 PDF 文件的二进制流，注册字体，调用 `translate_patch()` 进行核心翻译和布局保留。
        *   `translate_patch()`: 逐页分析布局，生成修补后的 PDF 内容流。实例化并使用 `TranslateConverter` 和 `PDFPageInterpreterEx`。
        *   `download_remote_fonts()`: 下载并管理中文字体（如思源宋体）。
        *   `check_files()`: 检查输入文件是否存在。
    *   **交互**: 使用 `DocLayoutModel` 进行布局分析，`TranslateConverter` 进行内容翻译和转换，`PDFPageInterpreterEx` 进行 PDF 内容解析。

*   **`converter.py`**:
    *   **功能**: 负责接收 `pdfminer.six` 解析的 PDF 内容流，进行文本块的识别、翻译，并生成翻译后的 PDF 指令流，以保留原始布局。专注于英译中。
    *   **主要类/函数**:
        *   `TranslateConverter`: 继承自 `PDFConverterEx` (自定义的 PDFConverter)，实现对 PDF 页面元素的处理，识别文本块，调用翻译器进行翻译，并使用 `pymupdf` Font 对象进行字符宽度计算和排版。
    *   **交互**: 接收来自 `PDFPageInterpreterEx` 的页面对象，使用 `BaseTranslator` (如 `GoogleTranslator`) 进行文本翻译。

*   **`translator.py`**:
    *   **功能**: 定义翻译器的抽象基类。
    *   **主要类/函数**:
        *   `BaseTranslator`: 抽象基类，定义了翻译器的通用接口，如 `translate()` 和 `do_translate()`。包含对翻译缓存 (`TranslationCache`) 的调用和自定义 `prompt` 的处理。
    *   **交互**: 被具体的翻译器实现（如 `GoogleTranslator`）继承。

*   **`google_translator.py`**:
    *   **功能**: 实现了使用 Google Translate API进行文本翻译的具体逻辑。
    *   **主要类/函数**:
        *   `GoogleTranslator`: 继承自 `BaseTranslator`，实现了 `do_translate()` 方法，通过 HTTP 请求与 Google Translate 服务交互。
    *   **交互**: 被 `TranslateConverter` 实例化和调用。

*   **`pdfinterpreter.py`**:
    *   **功能**: 扩展 `pdfminer.six` 的 `PDFPageInterpreter`，以更好地控制页面内容流的处理，并与 `TranslateConverter` 配合。
    *   **主要类/函数**:
        *   `PDFPageInterpreterEx`: 自定义的 PDF 页面解释器。
    *   **交互**: 由 `translate_patch()` 调用，用于处理 PDF 页面。

*   **`doclayout.py`**:
    *   **功能**: 负责文档布局分析，通常使用 ONNX 模型来识别页面中的文本块、图像、表格等元素。
    *   **主要类/函数**:
        *   `OnnxModel` / `DocLayoutModel`: 加载和运行布局分析模型，预测页面元素的边界框和类别。
        *   `ModelInstance`: 用于在 GUI 中共享模型实例。
    *   **交互**: 被 `pdf_processor.py` 中的 `translate_patch()` 调用，为每个页面生成布局信息。

### 3.3. 基础设施层 (`src/nex_translation/infrastructure`)

此层提供应用运行所需的基础服务。

*   **`config.py`**:
    *   **功能**: 管理应用的配置信息，如翻译服务凭证、默认设置等。采用单例模式确保配置的一致性。
    *   **主要类/函数**:
        *   `ConfigManager`: 提供获取和更新配置项的方法。处理配置文件的读取和保存 (JSON格式)，专注于英译中相关的默认配置。
    *   **交互**: 被系统中几乎所有需要配置信息的模块调用。

*   **`cache.py`**:
    *   **功能**: 实现翻译结果的缓存，以避免重复翻译相同文本，提高效率。使用 Peewee ORM 和 SQLite 数据库。
    *   **主要类/函数**:
        *   `TranslationCache`: 提供 `get()` 和 `set()` 方法来存取缓存。使用 `db_proxy` 实现数据库的延迟初始化和多环境支持。
        *   `_TranslationCache` (Peewee Model): 定义缓存数据库的表结构。
        *   `init_db()` / `init_test_db()`: 初始化生产和测试数据库。
    *   **交互**: 主要被 `translator.py` 中的 `BaseTranslator` 调用。

### 3.4. 工具层 (`src/nex_translation/utils`)

此层包含项目通用的辅助模块。

*   **`logger.py`**:
    *   **功能**: 提供统一的日志记录功能，支持不同级别的日志输出和灵活的配置。
    *   **主要类/函数**:
        *   `get_logger()`: 获取配置好的日志记录器实例。
        *   `set_log_level()` / `enable_debug()`: 控制日志级别。
    *   **交互**: 被项目中所有需要记录日志的模块使用。

*   **`exceptions.py`**:
    *   **功能**: 定义项目中使用的自定义异常类。
    *   **主要类/函数**:
        *   `NexTranslationError` (基类)及其派生类，如 `PDFError`, `TranslationError`, `LayoutAnalysisError` 等。
    *   **交互**: 在项目中各模块中抛出和捕获，用于更精确的错误处理。

## 4. 数据流和交互

1.  **用户启动 (CLI/GUI)**: 用户通过 CLI 输入命令或在 GUI 上传文件并设置选项。
2.  **表示层处理**:
    *   CLI (`cli.py`) 解析参数。
    *   GUI (`gui.py`) 获取用户输入。
    *   两者都调用核心层的 `translate()` 函数。
3.  **核心层 - `pdf_processor.py`**:
    *   `translate()` 函数接收文件列表和参数。
    *   对于每个文件，调用 `translate_stream()`。
    *   `translate_stream()`:
        *   加载中文字体。
        *   使用 `pymupdf` 打开原始 PDF 和创建用于翻译的副本。
        *   调用 `translate_patch()`。
    *   `translate_patch()`:
        *   使用 `PDFParser` 和 `PDFDocument` (来自 `pdfminer.six`) 解析 PDF 结构。
        *   对于每个目标页面：
            *   使用 `DocLayoutModel` (`doclayout.py`) 分析页面布局，识别文本区域和非文本区域。
            *   实例化 `TranslateConverter` (`converter.py`)，传入布局信息、翻译服务配置和字体对象。
            *   实例化 `PDFPageInterpreterEx` (`pdfinterpreter.py`) 并处理页面，将页面元素传递给 `TranslateConverter`。
4.  **核心层 - `converter.py`**:
    *   `TranslateConverter` 接收从 `PDFPageInterpreterEx` 传递过来的 `LTChar` (字符)等布局元素。
    *   组合字符形成文本块。
    *   对识别出的文本块，调用 `GoogleTranslator` (`google_translator.py`) 进行翻译。
    *   `GoogleTranslator` (继承自 `BaseTranslator`):
        *   首先检查 `TranslationCache` (`cache.py`) 中是否有缓存的翻译结果。
        *   如果没有缓存或忽略缓存，则调用 `do_translate()` 方法通过 Google Translate API 执行翻译。
        *   将新的翻译结果存入缓存。
    *   `TranslateConverter` 根据翻译后的文本和原始布局信息（包括字体、大小、位置），生成新的 PDF 页面指令流，尝试保留原始排版。
5.  **核心层 - `pdf_processor.py` (续)**:
    *   `translate_patch()` 返回包含已翻译页面指令的对象。
    *   `translate_stream()` 将这些新指令更新到 PDF 文档中。
    *   保存生成单语（纯中文）和双语（英中对照）的 PDF 文件。
6.  **基础设施层与工具层**:
    *   `ConfigManager` (`config.py`) 在整个过程中被各模块调用以获取配置信息（如API密钥、默认服务等）。
    *   `TranslationCache` (`cache.py`) 被翻译器调用以存取翻译结果。
    *   `logger.py` 和 `exceptions.py` 在所有模块中用于日志记录和错误处理。

## 5. 关键设计决策

*   **模块化设计**: 将系统划分为清晰的层次和模块，提高了代码的可维护性和可扩展性。
*   **专注于英译中**: 简化了语言处理逻辑，字体管理也主要围绕英文和中文进行。
*   **布局保留**: 核心挑战在于翻译后尽可能保留原始 PDF 的布局。这通过 `pdfminer.six` 解析结构、`doclayout.py` 分析布局、`converter.py` 精细处理文本块和重新排版实现。
*   **配置管理**: 使用 `ConfigManager` 单例进行集中配置管理，方便修改和部署。
*   **翻译缓存**: 通过 `TranslationCache` 提高重复文本的翻译效率。
*   **用户界面**: 提供 CLI 和 GUI 两种交互方式，满足不同用户需求。
*   **错误处理**: 定义了自定义异常，并在关键路径进行捕获和记录。

## 6. 未来展望 (可选)

*   支持更多翻译引擎。
*   优化布局分析模型的准确性和性能。
*   提供更高级的字体替换和样式匹配策略。
*   增强对复杂 PDF（如图表、公式密集型文档）的处理能力。 