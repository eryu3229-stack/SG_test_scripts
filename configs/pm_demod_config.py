# -*- coding: utf-8 -*-
"""PM（相位调制）测量配置。

口径（用户 2026-09-18 定案）：
    要读 **相位偏移 + 调制速率 + 正负峰值不平衡**；
    寄生交叉调制不做；Bessel 零点法暂缓；
    最大相偏上限属"设置问题"，**不在读数侧测**。

测量链路：
    信号源（内部 LF1 正弦）→ 设 PM 相偏（rad）→ 射频输出
    频谱仪 ADEMOD 模式 → 解调 → `:FETC:PM?` 16 项 → 相偏 / 速率 / 不平衡

相偏取哪一个量：
    手册 PM 结果表 `#8~#11` = **Deviation (Peak+) / (Peak-) / (Pk-Pk)/2 / RMS**。
    本配置把 **(Pk-Pk)/2** 作为"相位偏移"主指标，**单位 rad**；
    Peak+/Peak- 另列，两者之差即正负峰值不平衡。

⚠ 单位是本测量最大的坑（真机证实，2026-09-16，N9030B / A.36.22）：
    `:UNIT:PM:DEMod` **会连带改 `:FETC:PM?` 的数值**，不是只改标注 ——
      RAD  → 第 8 项 0.167111437
      DEGR → 第 8 项 9.582051469      比值 57.339291918 = 180/π
    且该节点的复位默认值是 **DEGR 而非 RAD**。
    驱动 `read_demod_metrics()` 已按"先读单位再换算回 rad"处理（读不到单位就
    剔除 `_rad` 字段并报错），所以本配置**不依赖单位设置正确**；
    这里仍显式锁定 RAD，是为了让面板/其它读数窗口与本流程口径一致、便于现场核对。
"""

project_name = "PM 相位调制测量"

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
# 相位偏移列表，单位 **rad**（信号源 `SOUR:PM1:DEV ... RAD`，上限随 RF 频率变化）
# ⚠ 信号源侧也有同源的坑：`UNIT:ANGLe`（SMB100B 手册 p596）能把角度默认单位改成
#   度，届时裸数值 `PM:DEV 1` 会被当成 1°（=0.0175 rad）。驱动
#   `set_pm_deviation()` 已显式带 `RAD` 后缀，不依赖默认单位。
pm_deviation_list_rad = [
    0.2,
    0.5,
    1.0,
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
# `:DISP:PM:VIEW:METR:MMAG`（调制量度显示）复位到预设 ALL，避免
# "其余量度被装入 not a number" 导致 `:FETC:PM?` 静默回 NaN。
demod_preset = True

# 解调 Y 轴 / 读数单位，锁定 RAD（见文件头说明）。
# 取值：RADian | DEGRee；驱动会转成手册写法 `RADian` 下发。
pm_demod_unit = "RAD"

# RF 跨度（`SENS:PM:FREQ:SPAN`）。None = 自动推导
demod_span_hz = None
span_margin_factor = 1.5
min_demod_span_hz = 20e3

# 解调通道带宽（`SENS:PM:BAND:CHAN`）。None = 自动推导
channel_bw_hz = None
# PM 按 Carson 带宽推导：调制指数 β = Δφ(rad)，BW ≈ 2 × (β + 1) × fm。
# β=1、fm=1 kHz 时 BW ≈ 4 kHz；β 较大时带宽需求随 β 线性增长。
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

# ============================================================
# 重复采样
# ============================================================
repeat_count = 3

# ============================================================
# 判定容差
# ============================================================
# 相偏相对误差上限（%）：|实测 − 设定| / 设定 × 100
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
        "pm_demod_unit": pm_demod_unit,
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
        "repeat_count": repeat_count,
        "param_tolerance_rel_pct": param_tolerance_rel_pct,
        "mod_rate_tolerance_rel_pct": mod_rate_tolerance_rel_pct,
        "sinad_min_db": sinad_min_db,
        "repeat_limit_rel_pct": repeat_limit_rel_pct,
    }
