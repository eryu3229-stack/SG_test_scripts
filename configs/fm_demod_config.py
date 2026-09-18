# -*- coding: utf-8 -*-
"""FM（频率调制）测量配置。

口径（用户 2026-09-18 定案）：
    要读 **频偏 + 调制速率 + 正负峰值不平衡**；
    寄生交叉调制不做；Bessel 零点法暂缓；
    最大频偏上限属"设置问题"，**不在读数侧测**。

测量链路：
    信号源（内部 LF1 正弦）→ 设 FM 频偏 → 射频输出
    频谱仪 ADEMOD 模式 → 解调 → `:FETC:FM?` 16 项 → 频偏 / 速率 / 不平衡

频偏取哪一个量：
    手册 FM 结果表 `#8~#11` = **Deviation (Peak+) / (Peak-) / (Pk-Pk)/2 / RMS**（Hz）。
    本配置把 **(Pk-Pk)/2** 作为"频偏"主指标；Peak+/Peak- 另列，
    两者之差即正负峰值不平衡（DC 偏置会直接表现为这个差）。

⚠ FM 与 PM 在信号源侧**硬件互斥**：手册 p454 明确"激活相位调制会关闭频率调制"。
  流程在设调制前会显式关掉 **PM**（**只关 PM，不关 AM** —— AM 与 FM 无互斥关系，
  流程不替用户改动本测量用不到的开关状态）。残留的 AM 仅由回读告警提示，不主动清理。
"""

project_name = "FM 频率调制测量"

# ============================================================
# 载波频率
# ============================================================
frequency_mode = "step"

frequency_config = {
    'start_frequency': 1e9,
    'end_frequency': 40e9,
    'step_frequency': 1e9,
    'include_end': True,
}

frequency_list = [
    1e9,
    2e9,
    5e9,
    10e9,
    20e9,
]

carrier_power_dbm = 10

# ============================================================
# 调制参数的扫描列表
# ============================================================
# 频偏列表，单位 Hz（信号源 `SOUR:FM1:DEV`）
# 上限随 RF 频率与机型变化，越界会被仪器拒绝（信号源驱动会在参数非法时不下发）。
fm_deviation_list_hz = [
    1e3,
    5e3,
    10e3,
]

# 调制速率（= 内部 LF 源频率）列表，单位 Hz
mod_rate_list_hz = [
    1000.0,
]

# ============================================================
# 信号源侧
# ============================================================
lf_shape = "SINE"
mod_source = "LF1"
frequency_settling_time_s = 0.5
power_settling_time_s = 0.5
source_settling_time_s = 0.5

# ============================================================
# 频谱仪解调设置
# ============================================================
# 见 am_demod_config.py 里的同一项说明：Meas Preset 会把
# `:DISP:FM:VIEW:METR:MMAG`（调制量度显示）复位到预设 ALL，避免
# "其余量度被装入 not a number" 导致 `:FETC:FM?` 静默回 NaN。
demod_preset = True

# RF 跨度（`SENS:FM:FREQ:SPAN`）。None = 自动推导
demod_span_hz = None
span_margin_factor = 1.5
min_demod_span_hz = 20e3

# 解调通道带宽（`SENS:FM:BAND:CHAN`）。None = 自动推导
channel_bw_hz = None
# FM 按 Carson 带宽推导：BW ≈ 2 × (Δf + fm)。
# 通道带宽不足会切掉边带 → 解调出来的频偏偏低、THD 上升，
# 看起来像"信号源频偏不准"，实际是仪器侧带宽不够。
channel_bw_margin_factor = 1.5
min_channel_bw_hz = 8e3

demod_rbw_hz = None
demod_rbw_auto = True

af_start_hz = 0.0
af_stop_hz = None              # None = max(af_span_margin × fm, min_af_stop_hz)
af_span_margin = 20.0
min_af_stop_hz = 20e3

demod_time_s = None
demod_time_cycles = 20.0
min_demod_time_s = 0.01

# 仪器平均：默认关闭（理由同 AM —— 打开会让重复性标准差恒为 0）
sa_average_on = False
sa_average_count = 10

sa_settling_time_s = 0.5

# FM 去加重：OFF（预设）| US25 | US50 | US75 | US750
# 去加重是接收端固定时间常数网络，用于抵掉发射端预加重。
# 测"信号源频偏准不准"必须保持 OFF —— 打开会改变解调后的幅度-频率响应，
# 使 SINAD/THD 与频偏读数都不再反映真实调制。除非规范明确要求预加重/去加重配对。
fm_deemphasis = "OFF"

# ============================================================
# 重复采样
# ============================================================
repeat_count = 3

# ============================================================
# 判定容差
# ============================================================
# 频偏相对误差上限（%）：|实测 − 设定| / 设定 × 100
param_tolerance_rel_pct = 5.0
mod_rate_tolerance_rel_pct = 1.0
sinad_min_db = 20.0
repeat_limit_rel_pct = 2.0


def generate_frequency_list():
    """按 `frequency_mode` 生成载波频率列表（单位 Hz，升序）。

    实现与 am_demod_config.generate_frequency_list 相同（三个调制配置各自
    独立，不跨文件 import，避免配置层互相耦合）。
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
        "lf_shape": lf_shape,
        "mod_source": mod_source,
        "frequency_settling_time_s": frequency_settling_time_s,
        "power_settling_time_s": power_settling_time_s,
        "source_settling_time_s": source_settling_time_s,
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
        "fm_deemphasis": fm_deemphasis,
        "repeat_count": repeat_count,
        "param_tolerance_rel_pct": param_tolerance_rel_pct,
        "mod_rate_tolerance_rel_pct": mod_rate_tolerance_rel_pct,
        "sinad_min_db": sinad_min_db,
        "repeat_limit_rel_pct": repeat_limit_rel_pct,
    }
