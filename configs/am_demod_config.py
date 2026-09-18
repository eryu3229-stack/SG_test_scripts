# -*- coding: utf-8 -*-
"""AM（幅度调制）测量配置。

口径（用户 2026-09-18 定案）：
    要读 **调制深度 + 调制速率 + 正负峰值不平衡**；
    寄生交叉调制（AM→FM / FM→AM）**不做**；
    Bessel 零点法交叉验证**暂缓**（先跑通驱动指令树）；
    最大深度上限属"设置问题"，**不在读数侧测**。

测量链路：
    信号源（内部 LF1 正弦）→ 设 AM 深度 → 射频输出
    频谱仪 ADEMOD 模式 → 解调 → `:FETC:AM?` 18 项 → 深度 / 速率 / 不平衡

深度取哪一个量（重要，别改错）：
    手册 p157 结果表里 `#8~#11` 是 **Modulation Depth (Peak+) / (Peak-) /
    (Pk-Pk)/2 / RMS**（单位 %）。本配置把 **(Pk-Pk)/2** 作为"调制深度"主指标：
    它是 AM 深度的标准定义；Peak+ / Peak- 另列，两者之差即正负峰值不平衡。
"""

project_name = "AM 幅度调制测量"

# ============================================================
# 载波频率
# ============================================================
# "step" = 用下面起止步进自动生成；"list" = 用 frequency_list 显式列表
frequency_mode = "list"

frequency_config = {
    'start_frequency': 1e9,      # 起始频率（含），Hz
    'end_frequency': 40e9,       # 终止频率（含），Hz
    'step_frequency': 1e9,       # 频率步进，Hz
    'include_end': True,         # 末点不落在步进网格上时，是否补一个终止点
}

# 显式频率列表，仅 frequency_mode = "list" 时使用
frequency_list = [
    1e9,
]

# 载波功率，单位 dBm
carrier_power_dbm = -10

# ============================================================
# 调制参数的扫描列表
# ============================================================
# 调制深度列表，单位 %（信号源 `SOUR:AM1:DEPTH`，范围 0~100）
# 一次运行按「频率 × 深度 × 速率」三重循环展开，每组合输出一行。
am_depth_list_pct = [
    30.0,
    50.0,
    80.0,
]

# 调制速率（= 内部 LF 源频率）列表，单位 Hz（信号源 `SOUR:LFO1:FREQ`）
mod_rate_list_hz = [
    1000.0,
]

# ============================================================
# 信号源侧
# ============================================================
lf_shape = "SINE"          # 内部 LF 波形：SINE / SQUare / PULSe / TRIangle / TRAPeze
mod_source = "LF1"         # AM1 的调制源：LF1|LF2|EXT1|NOISe|INTernal
frequency_settling_time_s = 0.5    # 切频后的稳定等待
power_settling_time_s = 0.5        # 改功率后的稳定等待
source_settling_time_s = 0.5       # 改调制参数 / 速率后的稳定等待

# ============================================================
# 频谱仪解调设置
# ============================================================
# Meas Preset：切测量时发 `:CONFigure:AM`（复位该测量的设置）而不是
# `:CONFigure:AM:NDEFault`（保留现状）。
# 取 True 的理由：复位会把「调制量度显示」`:DISP:AM:VIEW:METR:MMAG` 一并回到
# 预设值 ALL。手册 p206 明写该设置不为 ALL 时，**其余调制量度会被装入
# "not a number"** —— 若固件对 `:FETC:AM?` 走同一套计算，那些位置就会回
# NaN，读数静默失效。每点复位一次，等于把这种历史状态彻底清掉。
# 代价：每换一个测量（本流程只在起始时切一次）多一次复位，可忽略。
demod_preset = True

# RF 跨度（`SENS:AM:FREQ:SPAN`，手册 p221）。None = 自动推导（见下）
demod_span_hz = None
# 自动推导：先算所需通道带宽，再乘余量，并保证不小于 min_demod_span_hz
span_margin_factor = 1.5
min_demod_span_hz = 20e3

# 解调通道带宽（`SENS:AM:BAND:CHAN`，手册 p204）。None = 自动推导
channel_bw_hz = None
# AM 占空带宽 ≈ 2×fm（双边带）。乘余量覆盖调制边带，再取不小于 min_channel_bw_hz。
# 通道带宽必须 <= RF 跨度，代码会自动夹逼并打印告警。
channel_bw_margin_factor = 1.5
min_channel_bw_hz = 8e3

# RF 分辨率带宽（`SENS:AM:BAND:RES`）。
# 默认 None + demod_rbw_auto = True → 用仪器自动耦合（手册 p204：约 Span/106，
# 上限 3 MHz）。自动耦合比自己拍一个数更稳：跨度一变它就跟着变。
demod_rbw_hz = None
demod_rbw_auto = True

# AF（音频）频谱范围（`SENS:AM:AFSP:FREQ:STAR/STOP`，手册 p223-224）。
# AF 范围必须覆盖调制速率与其谐波，否则 SINAD/THD 只统计到截断后的带宽。
af_start_hz = 0.0
af_stop_hz = None              # None = 自动 = max(af_span_margin × fm, min_af_stop_hz)
af_span_margin = 20.0
min_af_stop_hz = 20e3

# 解调时间（`SENS:AM:DEM:TIME`，秒）。None = 自动推导。
# 下面这个周期数是自动推导的下限依据：手册 p366 明确提示"记录内少于 10 个
# 调制周期"会让载波频率自动估计产生偏差，进而给 Peak+/Peak- 引入 DC 偏置。
# 取 20 个周期留一倍余量。
demod_time_s = None
demod_time_cycles = 20.0
min_demod_time_s = 0.01

# 仪器平均（`SENS:AM:AVER:STAT/COUN`）。
# 默认**关闭**：本流程用"N 次独立采集 + N 次读数"做重复性统计（见 repeat_count），
# 打开仪器平均会让 N 次 FETC 返回同一个值，标准差恒为 0 —— 重复性判据失效。
sa_average_on = False
sa_average_count = 10

# 下发设置后的稳定等待（秒）
sa_settling_time_s = 0.5

# AM 解调类型：DSB（双边带，含载波，预设）| SSB（抑制载波单边带）
# ⚠ 它决定 `:FETC:AM?` 用哪张结果表：DSB 18 项（#8~#11 是深度 %），
#   SSB 17 项（#8~#11 是解调波形幅度 V）。两表同索引含义完全不同。
am_genre = "DSB"

# ============================================================
# 重复采样（重复性判据的唯一来源）
# ============================================================
# 每个测点独立采集 + 读数 N 次 → 平均值入 CSV，标准差作为重复性指标。
repeat_count = 3

# ============================================================
# 判定容差
# ============================================================
# 调制深度相对误差上限（%）：|实测 − 设定| / 设定 × 100
param_tolerance_rel_pct = 5.0
# 调制速率相对误差上限（%）
mod_rate_tolerance_rel_pct = 1.0
# SINAD 下限（dB）：低于它说明解调质量差（噪声/失真大），读数仅供参考
sinad_min_db = 20.0
# 重复性上限（%）：N 次采样的标准差 / 均值 × 100
repeat_limit_rel_pct = 2.0


def generate_frequency_list():
    """按 `frequency_mode` 生成载波频率列表（单位 Hz，升序）。

    - "step"：用 `start + i×step` 生成，**不做逐次累加**，避免浮点漂移；
      末点若不在步进网格上，按 `include_end` 决定是否补一个终止点。
    - "list"：直接用 `frequency_list`（排序后返回）。

    Returns:
        list[float]: 频率列表（Hz）；范围非法（end < start）时返回空列表

    Raises:
        ValueError: step_frequency <= 0（否则会生成无限/异常点数）
    """
    if frequency_mode == "list":
        return sorted(float(f) for f in frequency_list)

    start = float(frequency_config['start_frequency'])
    end = float(frequency_config['end_frequency'])
    step = float(frequency_config['step_frequency'])
    if step <= 0:
        raise ValueError(f"frequency_config['step_frequency'] 必须 > 0，当前为 {step}")
    if end < start:
        return []

    tol = max(1e-9, abs(step) * 1e-9)
    count = int((end - start) // step) + 1
    frequencies = [start + i * step for i in range(count)]
    while len(frequencies) > 1 and frequencies[-1] > end + tol:
        frequencies.pop()
    if frequency_config.get('include_end', True) and abs(frequencies[-1] - end) > tol:
        frequencies.append(end)
    return frequencies


def get_config():
    """返回完整配置字典"""
    return {
        # 信号源
        "lf_shape": lf_shape,
        "mod_source": mod_source,
        "frequency_settling_time_s": frequency_settling_time_s,
        "power_settling_time_s": power_settling_time_s,
        "source_settling_time_s": source_settling_time_s,
        # 频谱仪解调
        "demod_preset": demod_preset,
        "demod_span_hz": demod_span_hz,
        "span_margin_factor": span_margin_factor,
        "min_demod_span_hz": min_demod_span_hz,
        "channel_bw_hz": channel_bw_hz,
        "channel_bw_margin_factor": channel_bw_margin_factor,
        "min_channel_bw_hz": min_channel_bw_hz,
        "demod_rbw_hz": demod_rbw_hz,
        "demod_rbw_auto": demod_rbw_auto,
        "af_start_hz": af_start_hz,
        "af_stop_hz": af_stop_hz,
        "af_span_margin": af_span_margin,
        "min_af_stop_hz": min_af_stop_hz,
        "demod_time_s": demod_time_s,
        "demod_time_cycles": demod_time_cycles,
        "min_demod_time_s": min_demod_time_s,
        "sa_average_on": sa_average_on,
        "sa_average_count": sa_average_count,
        "sa_settling_time_s": sa_settling_time_s,
        "am_genre": am_genre,
        # 采样与判定
        "repeat_count": repeat_count,
        "param_tolerance_rel_pct": param_tolerance_rel_pct,
        "mod_rate_tolerance_rel_pct": mod_rate_tolerance_rel_pct,
        "sinad_min_db": sinad_min_db,
        "repeat_limit_rel_pct": repeat_limit_rel_pct,
    }
