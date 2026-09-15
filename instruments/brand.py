# -*- coding: utf-8 -*-
"""仪器品牌识别。

从 `*IDN?` 回读串判定厂商，供驱动门面选择品牌后端。

`*IDN?` 典型返回：
    Rohde&Schwarz,FSWP8,1322.8003K08,4.10
    Keysight Technologies,N9030B,US00000000,A.27.20
    Agilent Technologies,N9020A,US00000000,A.14.50   （早期是德沿用 Agilent 标）
"""

ROHDE = "rohde"
KEYSIGHT = "keysight"
UNKNOWN = "unknown"

# 关键字 → 品牌。注意 "AGILENT" 归入是德（同一 X 系列指令体系）。
_BRAND_KEYWORDS = (
    ("ROHDE", ROHDE),
    ("R&S", ROHDE),
    ("KEYSIGHT", KEYSIGHT),
    ("AGILENT", KEYSIGHT),
)


def detect_brand(idn):
    """从 `*IDN?` 回读串识别品牌。

    Args:
        idn: `*IDN?` 返回的字符串，可为 None

    Returns:
        "rohde" / "keysight" / "unknown"
    """
    if not idn:
        return UNKNOWN
    text = str(idn).upper()
    for keyword, brand_res in _BRAND_KEYWORDS:
        if keyword in text:
            return brand_res
    return UNKNOWN
