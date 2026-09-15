# -*- coding: utf-8 -*-
"""正式环境端到端冒烟（灵敏度改动）：用假仪器对象跑完整杂散流程。

覆盖本轮改动：
1. 段级输入衰减（35 / 25 / 20 dB）真的被下发，并写进 B 区
2. 参数读回校验被调用（read_key_settings）
3. 每段先用 WRITE 覆盖旧迹线再累积 MAXHold
4. 真实平均底噪（AVER 迹线 + 低参考电平）写入新列，且低于 POS/MAXH 门限基准
5. dBm/Hz 归一正确
6. 载波被剔除、谐波被剔除、真实杂散被报出
7. CSV 表头 == FIELDNAMES（24 列）
"""
import os
import sys
import tempfile
import csv

ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, "procedures"), os.path.join(ROOT, "configs")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import spurious_config as cfg  # noqa: E402
import spurious_procedure as sproc  # noqa: E402
from spurious_procedure import SpuriousProcedure  # noqa: E402


# ----------------------------------------------------------------------
# 时间提速：流程里的固定等待对本测试无意义
# ----------------------------------------------------------------------
class _TimeShim:
    @staticmethod
    def sleep(_seconds):
        pass


sproc.time = _TimeShim


CARRIER = 1e9
TARGETS = [
    # (频率, 电平 dBm, 期望结果)
    (CARRIER, 10.0, "carrier"),          # 载波：应被 guard 剔除
    (CARRIER + 20e6, -40.0, "spur"),     # near_100MHz 内：应报出
    (CARRIER + 200e6, -30.0, "spur"),    # far 段内：应报出
    (2 * CARRIER, -50.0, "harmonic"),    # 2×CF：应被谐波窗剔除
]


def _danl0(rbw):
    """0 dB 衰减、无预放时的平均底噪（本测试用的解析模型）。"""
    return -150.0 + 10.0 * np.log10(rbw)


class FakeSA:
    """假频谱仪：只实现流程真正调用的接口，并记录调用序列。"""

    def __init__(self):
        self.center = 1e9
        self.span = 1e6
        self.rbw = 1e3
        self.vbw = 3e3
        self.att = 10.0
        self.ref = 0.0
        self.trace_mode = "WRITE"
        self.detector = "POS"
        self.points = 1001
        self.preamp = False
        self.events = []
        self.marker_freq = None
        self.marker_level = None
        self.trace_modes_by_config = []

    # --- 频率/幅度/带宽 -------------------------------------------------
    def set_center_frequency(self, f):
        self.center = f

    def set_span(self, s):
        self.span = s

    def set_rbw(self, v):
        self.rbw = v

    def set_vbw(self, v):
        self.vbw = v

    def set_reference_level(self, v):
        self.ref = v
        self.events.append(("ref", v))

    def set_attenuation(self, v):
        self.att = v
        self.events.append(("att", v))

    def set_attenuation_auto(self, state):
        self.events.append(("att_auto", state))

    def set_preamp(self, state=True, band=None):
        self.preamp = state

    def set_sweep_points(self, points):
        self.points = points

    def set_trace_mode(self, mode, trace=1):
        self.trace_mode = mode
        self.events.append(("mode", self.center, self.span, mode))

    def set_detector(self, detector, trace=1):
        self.detector = detector

    def set_input_coupling(self, coupling):
        pass

    def wait_for_sweep(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        return True

    # --- 读回校验 -------------------------------------------------------
    def read_key_settings(self):
        self.events.append(("readback", self.center, self.span))
        return {
            "rbw_hz": self.rbw,
            "vbw_hz": self.vbw,
            "sweep_points": float(self.points),
            "ref_level_dbm": self.ref,
            "input_att_db": self.att,
        }

    # --- trace ----------------------------------------------------------
    def _grid(self, n=None):
        n = n or self.points
        step = self.span / n
        return self.center - self.span / 2 + (np.arange(n) + 0.5) * step, step

    def get_trace(self, trace=1):
        freqs, _ = self._grid()
        if self.detector.upper().startswith("AVER"):
            level = _danl0(self.rbw) + self.att
            return list(np.random.default_rng(7).normal(level, 0.6, len(freqs)))
        # POS/MAXH：峰值噪声包络 = 平均底噪 + 约 10 dB
        data = np.random.default_rng(11).normal(
            _danl0(self.rbw) + self.att + 10.0, 1.0, len(freqs)
        )
        for target_freq, level_dbm, _kind in TARGETS:
            if self.center - self.span / 2 <= target_freq <= self.center + self.span / 2:
                idx = int(np.argmin(np.abs(freqs - target_freq)))
                data[idx] = level_dbm
        return list(data)

    # --- 标记 -----------------------------------------------------------
    def peak_search(self, marker_num=1):
        best = None
        for target_freq, level_dbm, _kind in TARGETS:
            if abs(target_freq - self.center) <= self.span / 2:
                if best is None or level_dbm > best[1]:
                    best = (target_freq, level_dbm)
        if best is None:
            self.marker_freq = None
            self.marker_level = _danl0(self.rbw) + self.att + 10.0
        else:
            self.marker_freq, self.marker_level = best

    def get_marker_frequency(self, marker_num=1):
        return self.marker_freq

    def set_marker_frequency(self, marker_num, frequency):
        self.marker_freq = frequency
        self.marker_level = None

    def measure_marker_power(self, marker_num=1):
        return self.marker_level


class FakeSG:
    def __init__(self):
        self.output = None

    def set_frequency(self, f):
        pass

    def set_power(self, p):
        pass

    def enable_output(self, state):
        self.output = state


def main():
    config = cfg.get_config()
    config["carrier_frequency_list"] = [CARRIER]
    config["peak_detection"] = dict(config["peak_detection"])
    config["output"] = dict(config["output"])
    config["output"]["max_candidates_per_segment"] = 5   # 缩短测试

    proc = SpuriousProcedure(None)
    sa = FakeSA()
    sg = FakeSG()

    tmp = os.path.join(tempfile.gettempdir(), "wb_spurious_sensitivity.csv")
    if os.path.exists(tmp):
        os.remove(tmp)
    proc.start_csv_stream(tmp)

    proc.run_spurious_test(sg, sa, CARRIER, 10.0, config)
    proc.finish_csv()

    problems = []

    # --- 1. CSV 表头 ----------------------------------------------------
    with open(tmp, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(tmp, "r", encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    if header != SpuriousProcedure.FIELDNAMES:
        problems.append(f"表头与 FIELDNAMES 不一致: {header}")
    print(f"[1] CSV 列数 {len(header)}，行数 {len(rows)}")

    # --- 2/3. 段级衰减 + 读回校验 + 迹线初始化 ---------------------------
    att_by_segment = {}
    for r in rows:
        att_by_segment.setdefault(r["segment_name"], set()).add(float(r["sa_input_att_db"]))
    print(f"[2] 各段行内 sa_input_att_db: { {k: sorted(v) for k, v in att_by_segment.items()} }")
    if att_by_segment.get("near_100MHz") != {25.0}:
        problems.append(f"near_100MHz 衰减应为 25，实际 {att_by_segment.get('near_100MHz')}")
    far_atts = {a for k, v in att_by_segment.items() if k.startswith("far_") for a in v}
    if far_atts != {20.0}:
        problems.append(f"far 段衰减应为 20，实际 {far_atts}")

    readbacks = [e for e in sa.events if e[0] == "readback"]
    print(f"[3] 读回校验调用 {len(readbacks)} 次（期望 >= 3 个段）")
    if len(readbacks) < 3:
        problems.append(f"读回校验次数不足：{len(readbacks)}")

    mode_events = [e for e in sa.events if e[0] == "mode"]
    expected_segments = [(CARRIER, 10e6), (CARRIER, 100e6)]
    far_centers = [c for c in (0.5e9, 1.5e9)]
    expected_segments += [(c, 1e9) for c in far_centers]
    primes = 0
    for center, span in expected_segments:
        ms = [e[3] for e in mode_events if abs(e[1] - center) < 1 and abs(e[2] - span) < 1]
        if not ms or ms[0] != "WRITE" or "MAXH" not in ms:
            problems.append(f"段 ({center/1e6:.0f} MHz, {span/1e6:.0f} MHz) 迹线序列异常: {ms}")
            continue
        primes += 1
    print(f"[4] 迹线初始化：{primes}/{len(expected_segments)} 段先 WRITE 覆盖再 MAXH")
    if primes != len(expected_segments):
        problems.append("迹线初始化未覆盖所有段")

    # --- 5. 底噪两口径 + dBm/Hz ----------------------------------------
    bad_pairs = 0
    bad_hz = 0
    for r in rows:
        gate = float(r["sa_noise_floor_dbm"])
        avg = float(r["sa_noise_floor_avg_dbm"])
        per_hz = float(r["sa_noise_floor_dbm_per_hz"])
        if not avg < gate:
            bad_pairs += 1
        if abs(per_hz - (avg - 10 * np.log10(100.0))) > 0.05:
            bad_hz += 1
    print(f"[5] 底噪两口径：平均 < 门限基准 违反 {bad_pairs} 行；dBm/Hz 归一不符 {bad_hz} 行")
    if bad_pairs or bad_hz:
        problems.append("底噪两口径或 dBm/Hz 归一异常")

    # --- 6. 载波 / 谐波 / 真杂散 ----------------------------------------
    spurs = [float(r["spurious_freq_hz"]) for r in rows]

    def near(target):
        return any(abs(s - target) < 1e6 for s in spurs)

    print(f"[6] 报出频点: {[f'{s/1e6:.3f} MHz' for s in sorted(spurs)]}")
    if near(CARRIER):
        problems.append("载波被报出（应被 guard 剔除）")
    if near(2 * CARRIER):
        problems.append("2×CF 谐波被报出（应被谐波窗剔除）")
    if not near(CARRIER + 20e6):
        problems.append("CF+20 MHz 真实杂散未被报出")
    if not near(CARRIER + 200e6):
        problems.append("CF+200 MHz 真实杂散未被报出")

    print()
    if problems:
        print("FAIL:")
        for p in problems:
            print(" -", p)
        return 1
    print("ALL PASS（正式环境真实 numpy 端到端）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
