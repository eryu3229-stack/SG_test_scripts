# -*- coding: utf-8 -*-
"""频谱仪门面类（多品牌 SCPI 适配入口）。

职责：
1. 读取 `*IDN?` 判定仪器品牌（可用 `brand=` 参数显式覆盖）；
2. 按品牌装配 `instruments/backends/` 下的后端实现；
3. 对外暴露与原单品牌实现**完全一致的方法签名**，因此
   `procedures/`、`run_scripts/` 无需任何改动。

品牌策略：
- 自动识别：`Rohde&Schwarz` → rohde；`Keysight` / `Agilent` → keysight
- 识别失败或未支持的品牌 → 回退通用后端（只下发通用 SCPI 子集，逐项告警，不中断）
- 未知品牌也可在调用处显式指定，例如
      SpectrumAnalyzer(instrument, brand="keysight")

用法（与改造前一致）：
    sa = SpectrumAnalyzer(visa_instrument)
    sa.set_center_frequency(1e9)
"""
import os
import sys

# 保证以「顶层模块」方式导入本文件时，同目录的 brand / backends 可被解析
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import brand as _brand  # noqa: E402
from backends.sa_base import GenericSpectrumAnalyzer  # noqa: E402
from backends.sa_rohde import RohdeSpectrumAnalyzer  # noqa: E402
from backends.sa_keysight import KeysightSpectrumAnalyzer  # noqa: E402

# 品牌 → 后端实现
_BACKENDS = {
    _brand.ROHDE: RohdeSpectrumAnalyzer,
    _brand.KEYSIGHT: KeysightSpectrumAnalyzer,
}

_BRAND_ALIASES = {
    "rs": _brand.ROHDE,
    "r&s": _brand.ROHDE,
    "rohde": _brand.ROHDE,
    "rohde&schwarz": _brand.ROHDE,
    "keysight": _brand.KEYSIGHT,
    "agilent": _brand.KEYSIGHT,
}


class SpectrumAnalyzer:
    """频谱仪控制门面：按品牌转发到对应后端。"""

    def __init__(self, instrument, brand=None):
        """初始化频谱仪。

        Args:
            instrument: pyvisa 仪器对象
            brand: 显式指定品牌（"rohde" / "keysight"）；None 则读 *IDN? 自动识别
        """
        self.instrument = instrument
        self.idn = self._read_idn()
        self.brand = self._resolve_brand(brand)

        backend_cls = _BACKENDS.get(self.brand)
        if backend_cls is None:
            print(f"警告: 未识别频谱仪品牌(IDN={self.idn!r})，"
                  f"回退通用后端（品牌相关设置将被跳过）")
            backend_cls = GenericSpectrumAnalyzer

        self.backend = backend_cls(instrument)
        print(f"频谱仪品牌: {self.brand}（后端 {backend_cls.__name__}）")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _read_idn(self, retries=2):
        """读取 `*IDN?`；失败重试，仍失败返回 None。"""
        for attempt in range(retries + 1):
            try:
                return self.instrument.query("*IDN?")
            except Exception as e:
                if attempt >= retries:
                    print(f"读取仪器ID失败: {e}")
                    return None
        return None

    def _resolve_brand(self, brand):
        """确定使用的品牌：显式参数优先于 *IDN? 自动识别。"""
        if brand:
            key = str(brand).strip().lower()
            return _BRAND_ALIASES.get(key, key)
        return _brand.detect_brand(self.idn)

    # ------------------------------------------------------------------
    # 身份
    # ------------------------------------------------------------------
    def get_idn(self):
        """获取仪器 ID 信息。"""
        return self.backend.get_idn()

    def query_raw(self, command):
        """只读查询任意 SCPI 命令（用于读回校验，不做任何写入）。"""
        return self.backend.query(command)

    def read_key_settings(self):
        """读回影响测量结论的关键设置（RBW/VBW/点数/参考电平/输入衰减）。

        Returns:
            dict；读不到的项为 None（调用方按"无法校验"处理）。
        """
        return self.backend.read_key_settings()

    # ------------------------------------------------------------------
    # 频率与扫宽
    # ------------------------------------------------------------------
    def set_center_frequency(self, frequency):
        """设置中心频率。"""
        return self.backend.set_center_frequency(frequency)

    def set_span(self, span):
        """设置频率跨度。"""
        return self.backend.set_span(span)

    # ------------------------------------------------------------------
    # 幅度
    # ------------------------------------------------------------------
    def set_reference_level(self, level):
        """设置参考电平。"""
        return self.backend.set_reference_level(level)

    def set_attenuation(self, attenuation):
        """设置输入衰减。"""
        return self.backend.set_attenuation(attenuation)

    def set_attenuation_auto(self, state=True):
        """设置衰减自动/手动耦合。"""
        return self.backend.set_attenuation_auto(state)

    def set_preamp(self, state=True, band=None):
        """设置内置预放。

        Args:
            state: True 开，False 关
            band: 罗德 = 增益值(15/30 dB) 或 "LOW"/"FULL"；
                  是德 = "LOW"/"FULL" 波段（兼容传 15/30）
        """
        return self.backend.set_preamp(state, band)

    # ------------------------------------------------------------------
    # 标记点
    # ------------------------------------------------------------------
    def peak_search(self, marker_num=1):
        """执行峰值搜索。"""
        return self.backend.peak_search(marker_num)

    def set_marker_frequency(self, marker_num, frequency):
        """设置标记器频率。"""
        return self.backend.set_marker_frequency(marker_num, frequency)

    def measure_marker_power(self, marker_num):
        """测量标记器功率。"""
        return self.backend.measure_marker_power(marker_num)

    def get_marker_frequency(self, marker_num):
        """获取标记器频率。"""
        return self.backend.get_marker_frequency(marker_num)

    def measure_power(self, marker_num=1):
        """峰值搜索后测量功率。"""
        return self.backend.measure_power(marker_num)

    # ------------------------------------------------------------------
    # 带宽
    # ------------------------------------------------------------------
    def set_rbw(self, rbw):
        """设置分辨率带宽。"""
        return self.backend.set_rbw(rbw)

    def set_vbw(self, vbw):
        """设置视频带宽。"""
        return self.backend.set_vbw(vbw)

    def set_rbw_auto(self, state=True):
        """设置 RBW 自动/手动耦合。"""
        return self.backend.set_rbw_auto(state)

    def set_vbw_auto(self, state=True):
        """设置 VBW 自动/手动耦合。"""
        return self.backend.set_vbw_auto(state)

    # ------------------------------------------------------------------
    # 输入
    # ------------------------------------------------------------------
    def set_input_coupling(self, coupling):
        """设置输入耦合（AC / DC）。"""
        return self.backend.set_input_coupling(coupling)

    # ------------------------------------------------------------------
    # 迹线与检波器
    # ------------------------------------------------------------------
    def set_trace_mode(self, mode="MAXHold", trace=1):
        """设置 trace 模式。"""
        return self.backend.set_trace_mode(mode, trace)

    def set_detector(self, detector="POSitive", trace=1):
        """设置检波器。"""
        return self.backend.set_detector(detector, trace)

    def set_detector_auto(self, state=True, trace=1):
        """设置检波器自动耦合（后端不支持时为无操作）。"""
        handler = getattr(self.backend, "set_detector_auto", None)
        if handler:
            return handler(state, trace)
        print("警告: 当前后端不支持检波器自动耦合设置，已跳过")
        return None

    def get_trace(self, trace=1):
        """读取频谱 trace 数据。"""
        return self.backend.get_trace(trace)

    # ------------------------------------------------------------------
    # 扫描同步
    # ------------------------------------------------------------------
    def wait_for_sweep(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        """宽 SPAN 扫描同步（保守等待）。"""
        return self.backend.wait_for_sweep(sweep_count, span_hz=span_hz,
                                           factor=factor, margin=margin)

    def wait_for_sweep_fast(self, sweep_count=1, span_hz=None, factor=1.5,
                            margin=0.15, extra_margin=0.0):
        """小 SPAN 快速扫描同步。"""
        return self.backend.wait_for_sweep_fast(sweep_count, span_hz=span_hz,
                                                factor=factor, margin=margin,
                                                extra_margin=extra_margin)

    def trigger_single(self):
        """显式触发一次单次扫描并等待完成（`INIT:CONT OFF`+`INIT:IMM`+`*OPC?`）。

        用于读取 marker 之前，确保 trace 已刷新为有效数据。
        """
        handler = getattr(self.backend, "trigger_single", None)
        if handler:
            return handler()
        print("警告: 当前后端不支持单次触发，已跳过")
        return False

    def get_error_queue(self, limit=30):
        """读取 SCPI 错误队列，返回错误字符串列表（无错误为空列表）。"""
        handler = getattr(self.backend, "get_error_queue", None)
        if handler:
            return handler(limit)
        print("警告: 当前后端不支持错误队列读取，已跳过")
        return []

    # ------------------------------------------------------------------
    # 品牌扩展能力（可选，后端未实现时告警并返回 None）
    # ------------------------------------------------------------------
    def set_sweep_points(self, points):
        """设置扫描点数（后端不支持时跳过）。"""
        handler = getattr(self.backend, "set_sweep_points", None)
        if handler:
            return handler(points)
        print("警告: 当前后端不支持扫描点数设置，已跳过")
        return None
