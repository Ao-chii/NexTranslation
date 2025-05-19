#!/usr/bin/env python3

import argparse
import sys
import os
from pathlib import Path
from string import Template
from typing import List, Optional
import time
import logging

# 从项目中导入
from nex_translation import __version__, logger # 使用 __init__ 中的 logger
from nex_translation.core.pdf_processor import translate
from nex_translation.core.doclayout import DocLayoutModel
from nex_translation.infrastructure.config import ConfigManager
from nex_translation.utils.logger import set_log_level, enable_debug
from nex_translation.utils.exceptions import NexTranslationError

def parse_page_ranges(page_str: Optional[str]) -> Optional[List[int]]:
    """将 '1,3,5-7' 这样的字符串解析为页面索引列表 [0, 2, 4, 5, 6]。"""
    if not page_str:
        return None
    pages = set()
    try:
        for part in page_str.split(','):
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                if start < 1 or end < start:
                    raise ValueError(f"无效的页面范围: {part}")
                # 使用 0-based 索引
                pages.update(range(start - 1, end))
            else:
                page_num = int(part)
                if page_num < 1:
                    raise ValueError(f"无效的页码: {part}")
                # 使用 0-based 索引
                pages.add(page_num - 1)
        return sorted(list(pages))
    except ValueError as e:
        logger.error(f"无效的页面范围格式: {page_str}。错误: {e}")
        # 重新抛出异常以停止执行
        raise

def format_time(seconds: float) -> str:
    """将秒数格式化为人类可读的时间字符串"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def main():
    parser = argparse.ArgumentParser(
        description="NexTranslation: 翻译 PDF 文档并保留布局。",
        # 自动显示默认值
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "files",
        type=str,
        nargs="+",
        help="一个或多个输入 PDF 文件的路径。",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output",
        help="保存翻译后 PDF 文件的目录。",
    )
    parser.add_argument(
        "--pages", "-p",
        type=str,
        default=None,
        help="指定要翻译的页面范围，例如 '1,3,5-7'。如果未指定，则翻译所有页面。",
    )
    parser.add_argument(
        "--service", "-s",
        type=str,
        # 将从配置中获取默认值
        default=None,
        help="要使用的翻译服务（例如 'google', 'openai', 'deepl'）。覆盖配置中的默认值。",
    )
    parser.add_argument(
        "--thread", "-t",
        type=int,
        default=4,
        help="用于并行翻译的线程数。",
    )
    parser.add_argument(
        "--vfont", "-f",
        type=str,
        default="",
        help="用于匹配被视为公式一部分的字体名称的正则表达式模式。",
    )
    parser.add_argument(
        "--vchar", "-c",
        type=str,
        default="",
        help="用于匹配被视为公式一部分的字符的正则表达式模式。",
    )
    parser.add_argument(
        "--compatible", "-cp",
        action="store_true",
        default=False,
        help="将输出 PDF 转换为 PDF/A 格式以提高兼容性（需要 pikepdf）。",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="用于翻译的自定义提示模板文件的路径。",
    )
    parser.add_argument(
        "--ignore-cache",
        action="store_true",
        default=False,
        help="忽略现有的翻译缓存并强制重新翻译。",
    )
    parser.add_argument(
        "--skip-subset-fonts",
        action="store_true",
        default=False,
        help="在输出 PDF 中跳过字体子集化（可能会增加文件大小）。",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        default=False,
        help="启用详细的调试日志记录。",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"NexTranslation v{__version__}",
    )

    args = parser.parse_args()

    # --- 设置 ---
    if args.debug:
        # 设置日志级别为 DEBUG
        enable_debug()
        logger.debug("调试模式已启用。")
    else:
        # 确保非调试模式下为 INFO 级别
        set_log_level(logging.INFO)

    logger.info(f"启动 NexTranslation v{__version__}")

    try:
        # 加载配置和模型
        config_manager = ConfigManager.get_instance()
        layout_model = DocLayoutModel.load_available()
        if not layout_model:
            logger.error("加载布局分析模型失败。正在退出。")
            sys.exit(1)
        logger.info("布局分析模型已加载。")

        # 确定翻译服务
        service_to_use = args.service or config_manager.get_default_service()
        enabled_services = config_manager.get_enabled_services()
        if service_to_use not in enabled_services:
            logger.warning(f"服务 '{service_to_use}' 不在启用列表中: {enabled_services}。将使用默认服务: '{config_manager.get_default_service()}'")
            service_to_use = config_manager.get_default_service()
        logger.info(f"使用的翻译服务: {service_to_use}")
        
        # 解析页面
        page_list = parse_page_ranges(args.pages)
        if page_list is not None:
             logger.info(f"目标页面 (0-based 索引): {page_list}")
        else:
             logger.info("翻译所有页面。")

        # 加载自定义提示
        prompt_template = None
        if args.prompt:
            try:
                prompt_path = Path(args.prompt)
                if prompt_path.is_file():
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_template = Template(f.read())
                    logger.info(f"已从以下位置加载自定义提示模板: {args.prompt}")
                else:
                    logger.warning(f"未找到提示文件: {args.prompt}。将使用默认提示。")
            except Exception as e:
                logger.error(f"加载提示文件 {args.prompt} 时出错: {e}。将使用默认提示。")

        # 创建输出目录
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录: {output_dir.resolve()}")

        # --- 执行翻译 ---
        logger.info(f"正在处理 {len(args.files)} 个文件...")
        start_time = time.time()
        
        # 创建进度回调函数
        from tqdm import tqdm

        def progress_callback(t: tqdm):
            """翻译进度回调函数"""
            # 这里可以实现进度显示逻辑
            # 例如，打印当前进度
            print(f"\r翻译进度: {t.n}/{t.total} ({t.n/t.total*100:.1f}%)", end="")
        
        # 准备环境变量
        envs = {}
        
        result_files = translate(
            files=args.files,
            # translate 需要字符串路径
            output=str(output_dir),
            pages=page_list,
            service=service_to_use,
            thread=args.thread,
            vfont=args.vfont,
            vchar=args.vchar,
            compatible=args.compatible,
            # CLI 尚不支持取消
            cancellation_event=None,
            model=layout_model,
            # 传递语言环境变量
            envs=envs,
            prompt=prompt_template,
            skip_subset_fonts=args.skip_subset_fonts,
            ignore_cache=args.ignore_cache,
            # 传递进度回调
            callback=progress_callback
        )

        end_time = time.time()
        elapsed_time = end_time - start_time
        
        logger.info(f"翻译成功完成。总耗时: {format_time(elapsed_time)}")
        
        # 显示结果文件信息
        for i, (mono_path, dual_path) in enumerate(result_files, 1):
            logger.info(f"文件 {i}/{len(result_files)}:")
            logger.info(f"  - 单语输出: {mono_path}")
            logger.info(f"  - 双语输出: {dual_path}")
            
            # 计算文件大小
            mono_size = os.path.getsize(mono_path) / (1024 * 1024)  # MB
            dual_size = os.path.getsize(dual_path) / (1024 * 1024)  # MB
            logger.info(f"  - 单语文件大小: {mono_size:.2f} MB")
            logger.info(f"  - 双语文件大小: {dual_size:.2f} MB")

        sys.exit(0)

    except NexTranslationError as e:
        logger.error(f"发生错误: {e}")
        if args.debug:
            # 仅在调试模式下记录回溯
            logger.exception("详细回溯:")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        sys.exit(1)
    except ValueError as e: # 捕获页面范围解析错误
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户中断操作。正在退出...")
        sys.exit(130)  # 标准的用户中断退出码
    except Exception as e:
        logger.error(f"发生意外错误: {e}")
        if args.debug:
            logger.exception("详细回溯:")
        sys.exit(1)

if __name__ == "__main__":
    main()