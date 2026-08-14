# -*- coding: utf-8 -*-
"""GUI 字体工具。"""

import ctypes
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


def enable_dpi_awareness():
    """在创建 Tk 窗口前启用 Windows DPI 感知，避免界面被拉伸模糊。"""
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _apply_dpi_scaling(root):
    """按系统 DPI 调整 Tk 坐标缩放，保证文字和控件清晰。"""
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass


def apply_gui_font(root, size=11):
    """统一调大 Tk/ttk 各组件的默认字号。"""
    _apply_dpi_scaling(root)

    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkTooltipFont",
        "TkFixedFont",
    ):
        try:
            tkfont.nametofont(name).configure(size=size)
        except tk.TclError:
            pass

    style = ttk.Style(root)
    style.configure(".", font=("Microsoft YaHei UI", size))
    style.configure("TButton", font=("Microsoft YaHei UI", size))
    style.configure("TEntry", font=("Microsoft YaHei UI", size))
    style.configure("TCombobox", font=("Microsoft YaHei UI", size))
    style.configure("TCheckbutton", font=("Microsoft YaHei UI", size))
    style.configure("TLabel", font=("Microsoft YaHei UI", size))
    style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", size, "bold"))
    style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", size))
    style.configure("Treeview", font=("Microsoft YaHei UI", size))
    style.configure("Treeview.Heading", font=("Microsoft YaHei UI", size, "bold"))
