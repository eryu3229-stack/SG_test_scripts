# -*- coding: utf-8 -*-
"""通用显示格式化工具（可复用）"""


def format_frequency(frequency):
    """格式化频率显示，根据频率大小自动选择合适的单位

    Args:
        frequency: 频率值，单位Hz

    Returns:
        str: 格式化后的频率字符串（Hz/kHz/MHz/GHz 自动切换）
    """
    if frequency < 1e3:
        return f"{frequency:.0f}Hz"
    elif frequency < 1e6:
        return f"{frequency/1e3:.2f}kHz"
    elif frequency < 1e9:
        return f"{frequency/1e6:.2f}MHz"
    else:
        return f"{frequency/1e9:.2f}GHz"
