# -*- coding: utf-8 -*-
"""参数解析工具，支持科学计数法和常见单位后缀。"""


_FREQUENCY_UNITS = {
    "thz": 1e12,
    "ghz": 1e9,
    "mhz": 1e6,
    "khz": 1e3,
    "hz": 1.0,
}

_TIME_UNITS = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
}


def _parse_with_unit(value, label, units):
    text = str(value).strip().lower().replace(" ", "")
    text = text.replace("μs", "us").replace("µs", "us")
    if not text:
        raise ValueError(f"{label}不能为空。")

    for unit, factor in sorted(units.items(), key=lambda item: -len(item[0])):
        if text.endswith(unit):
            number_part = text[: -len(unit)]
            if not number_part:
                raise ValueError(f"{label}格式错误: {value}")
            try:
                return float(number_part) * factor
            except ValueError:
                raise ValueError(f"{label}格式错误: {value}")

    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{label}格式错误: {value}")


def parse_frequency(value, label="频率"):
    """解析频率，支持 1e9、1GHz、10 MHz 等写法。"""
    return _parse_with_unit(value, label, _FREQUENCY_UNITS)


def parse_time(value, label="时间"):
    """解析时间，支持 1s、500ms、1.5 s 等写法。"""
    return _parse_with_unit(value, label, _TIME_UNITS)


def parse_power(value, label="功率"):
    """解析功率，支持 10dBm、-40、1.5 dBm 等写法。"""
    text = str(value).strip().lower().replace(" ", "")
    if text.endswith("dbm"):
        text = text[:-3]
    if not text:
        raise ValueError(f"{label}不能为空。")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{label}格式错误: {value}")


def parse_float(value, label="数值"):
    """解析普通浮点数。"""
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label}不能为空。")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{label}格式错误: {value}")
