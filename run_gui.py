#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDF翻译工具 - GUI界面启动程序
用于调试和运行GUI界面
"""

import os
import sys
from pathlib import Path

# 获取项目根目录
project_root = Path(__file__).resolve().parent
# 将项目根目录添加到Python路径
print(str(project_root))
sys.path.append(str(project_root))

def main():
    """主函数，启动GUI界面"""
    try:
        # 设置调试日志
        import logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger("GUI_Launcher")
        logger.info("正在启动PDF翻译工具GUI界面...")

        print("正在加载布局分析模型...")
        # 加载布局分析模型
        from src.nex_translation.core.doclayout import DocLayoutModel, ModelInstance
        layout_model = DocLayoutModel.load_available()
        if not layout_model:
            logger.error("加载布局分析模型失败。正在退出。")
            sys.exit(1)
        # 设置ModelInstance.value
        ModelInstance.value = layout_model
        logger.info("布局分析模型已加载。")

        print("正在导入GUI模块...")
        # 导入GUI模块
        from src.nex_translation.core.gui import launch_gui

        print("正在启动GUI界面...")
        # 启动GUI，使用7861端口（避免与可能正在运行的实例冲突）
        launch_gui(port=7861)
    except ImportError as e:
        print(f"导入错误: {e}")
        print("\n请确保已安装所有依赖:")
        print("pip install gradio gradio-pdf babeldoc")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()