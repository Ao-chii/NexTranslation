#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDFMathTranslate 主入口程序
在本地端口7860上启动PDF翻译工具GUI界面
"""

import os
import sys
import logging
from pathlib import Path

# 添加src目录到Python路径
current_dir = Path(__file__).parent.absolute()
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir.parent))
else:
    # 如果没有src目录，则添加当前目录
    sys.path.insert(0, str(current_dir))

# 设置日志
logging.basicConfig(
    level=logging.INFO,  # 使用INFO级别，减少日志输出
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PDFMathTranslate")

def main():
    """
    主函数，启动PDF翻译工具GUI界面在端口7860
    """
    try:
        logger.info("正在启动PDFMathTranslate GUI界面...")

        # 导入必要的模块
        from nex_translation.core.gui import setup_gui
        from nex_translation.core.doclayout import OnnxModel, ModelInstance

        # 加载布局分析模型
        logger.info("正在加载布局分析模型...")
        model = OnnxModel.load_available()
        if not model:
            logger.error("加载布局分析模型失败，请确保模型文件存在")
            return 1

        # 设置模型实例
        ModelInstance.value = model
        logger.info("布局分析模型已加载")

        # 启动GUI界面在端口7860
        logger.info("正在启动GUI界面在端口7860...")
        setup_gui(server_port=7860)

        return 0
    except ImportError as e:
        logger.error(f"导入错误: {e}")
        logger.error("请确保已安装所有依赖: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.error(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
