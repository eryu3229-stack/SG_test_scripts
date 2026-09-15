# -*- coding: utf-8 -*-
"""频谱仪品牌后端包。

门面类 `instruments/spectrum_analyzer.py` 读取 `*IDN?` 判定品牌后，
从本包装配对应后端。新增品牌只需在本目录增加一个后端文件并在
`spectrum_analyzer.py` 的 `_BACKENDS` 中登记。

- sa_base.py     公共基类 + 未知品牌回退实现
- sa_rohde.py    罗德 R&S（FSWP / FSW，手册 1177.5656.02）
- sa_keysight.py 是德 Keysight（X 系列 SA，手册 N9060-90041）
"""
