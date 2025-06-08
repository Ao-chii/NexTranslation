<h1 align = "center">NexTranslation</h1>

`NexTranslation` 是一个智能 PDF 翻译工具，能够保留原始文档的排版布局。它使用先进的文档分析模型来识别文本、图表和公式，确保翻译后的文档保持原有的结构和美观度。

## 一、功能特点

- 保留原始 PDF 文档的排版和布局
- 目前支持谷歌翻译（默认设置），未来可接入更多翻译服务
- 智能识别公式和特殊符号，避免错误翻译
- 提供单语和双语对照输出
- 翻译缓存功能，提高翻译效率
- 支持命令行和图形界面操作

## 二、安装

### 从源码安装

```bash
git clone https://github.com/Ao-chii/NexTranslation.git
cd NexTranslation
pip install -e .
```

### 可选依赖

- 图形界面功能: `pip install -e .[gui]`
- 开发工具: `pip install -e .[dev]`

## 三、使用方法

### 1. 命令行界面

```bash
# 基本用法
nex-translate your_file.pdf

# 指定输出目录
nex-translate --output output_folder your_file.pdf

# 指定翻译服务
nex-translate --service google your_file.pdf

# 翻译特定页面
nex-translate --pages 1,3,5-7 your_file.pdf

# 更多选项请查看帮助
nex-translate --help
```

### 2. GUI





### 3. 配置文件

NexTranslation 使用位于 `~/.config/NexTranslation/config.json` 的配置文件。您可以在其中设置：

- 翻译服务 API 密钥（OpenAI、DeepL）
- 默认翻译服务
- 中文字体路径
- 缓存目录位置
- 其他全局设置

