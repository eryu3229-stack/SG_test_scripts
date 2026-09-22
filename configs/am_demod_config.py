# -*- coding: utf-8 -*-
"""AM 解调测量配置。

与项目其它 config 模块一致：顶部声明参数，底部通过 get_config() /
get_carrier_frequency_list() 暴露给 run_script。

AM 解调的关键物理约束：
- 占用带宽 ≈ 2 * fm（双边带），故通道带宽 / 跨度必须留够，否则测到的深度会偏低、
  THD 会偏高，与"信号源调制不准"难以区分。
- 解调记录时间必须覆盖足够多调制周期，否则 :FETC:AM? 里的调制速率估计会有偏差。
"""

# ============================================================
# 载波定义
# ============================================================
# "step" = 用起止/步进生成；"list" = 用 carrier_frequency_list 显式列表
carrier_frequency_mode = "list"

# 显式列表，仅 carrier_frequency_mode = "list" 时使用
carrier_frequency_list = [1e9,2e9]

# 步进式参数，单位 Hz
carrier_start_frequency_hz = 1e9
carrier_end_frequency_hz = 1e9
carrier_step_frequency_hz = 1e9

# 载波功率，单位 dBm
carrier_power_dbm = 0

# ============================================================
# AM 调制参数
# ============================================================
# 调幅深度列表，单位 %（线性深度）
am_depth_list_pct = [10, 30, 50]

# 调制速率列表，单位 Hz
am_mod_rate_list_hz = [1e3, 10e3, 100e3]

# AM 类型：LIN / EXP；参考流程固定 LIN
am_type = "LIN"

# AM 调制源：参考流程固定 LF1
am_source = "LF1"

# 内部 LF 源波形：参考流程固定 SINE
lf_shape = "SINE"

# ============================================================
# 频谱仪 ADEMOD 条件
# ============================================================
# AM 解调类型：DSB / SSB；主指标 half_pkpk 只在 DSB 下有意义
am_genre = "DSB"

# 每次切换 AM 测量是否走 Meas Preset（建议 True，给一个已知起点）
demod_preset = True

# 通道带宽：None 则按 2*fm * 余量自动算
channel_bw_hz = None
channel_bw_margin_factor = 1.5
min_channel_bw_hz = 8e3

# RF 跨度：None 则按通道带宽 * 余量自动算（仪器要求 通道带宽 ≤ 跨度）
demod_span_hz = None
span_margin_factor = 1.5
min_demod_span_hz = 20e3

# 解调 RBW：None 且 demod_rbw_auto=True 时由仪器自动选
demod_rbw_hz = None
demod_rbw_auto = True

# AF 频谱范围：start 固定 0，stop 按 fm * 余量自动算
af_start_hz = 0.0
af_stop_hz = None
af_span_margin = 20.0
min_af_stop_hz = 20e3

# 解调记录时间：None 则按至少 20 个调制周期自动算
demod_time_s = None
demod_time_cycles = 20.0
min_demod_time_s = 0.01

# 仪器平均：必须 False，否则重复性标准差恒为 0
sa_average_on = False
sa_average_count = 3

# ============================================================
# 沉降与采样
# ============================================================
sa_settling_time_s = 0.5
source_settling_time_s = 0.5
frequency_settling_time_s = 0.5
power_settling_time_s = 0.5

# 每个调制组合的独立采集次数
repeat_count = 3

# ============================================================
# 判定容差
# ============================================================
# 主指标（AM 深度）相对偏差容差，%
param_tolerance_rel_pct = 5.0

# 调制速率相对偏差容差，%
mod_rate_tolerance_rel_pct = 1.0

# SINAD 最小门限（dB），None 表示不判
sinad_min_db = None

# 重复性（样本标准差）相对上限，%
repeat_limit_rel_pct = 2.0

# ============================================================
# 结束阶段：恢复未调制信号并复测
# ============================================================
# 是否在最后关掉 AM 后用 SA 重新测一次载波功率/频率
# False：跳过该步。该步会读 marker（CALC:MARK:X?/Y?），SA 切回频谱模式后
# marker 常定位不到而回 9.91e+37 哨兵值，刷屏但与你需要的 half-pk（FETC:AM?）无关。
verify_unmodulated_carrier = False

# 关 AM 后等 ALC 稳定的时间
verify_settling_time_s = 1.0

# 复测时 SA 使用普通频谱模式参数
verify_sa_config = {
    "span": 1e6,
    "rbw": 1e3,
    "vbw": 3e3,
    "reference_level": 10,
    "attenuation": 10,
}

# ============================================================
# 输出
# ============================================================
output_tag = "am_demod"


def get_config():
    """返回完整配置字典。"""
    return {
        "carrier_power_dbm": carrier_power_dbm,
        "am_depth_list_pct": am_depth_list_pct,
        "am_mod_rate_list_hz": am_mod_rate_list_hz,
        "am_type": am_type,
        "am_source": am_source,
        "lf_shape": lf_shape,
        "am_genre": am_genre,
        "demod_preset": demod_preset,
        "channel_bw_hz": channel_bw_hz,
        "channel_bw_margin_factor": channel_bw_margin_factor,
        "min_channel_bw_hz": min_channel_bw_hz,
        "demod_span_hz": demod_span_hz,
        "span_margin_factor": span_margin_factor,
        "min_demod_span_hz": min_demod_span_hz,
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
        "source_settling_time_s": source_settling_time_s,
        "frequency_settling_time_s": frequency_settling_time_s,
        "power_settling_time_s": power_settling_time_s,
        "repeat_count": repeat_count,
        "param_tolerance_rel_pct": param_tolerance_rel_pct,
        "mod_rate_tolerance_rel_pct": mod_rate_tolerance_rel_pct,
        "sinad_min_db": sinad_min_db,
        "repeat_limit_rel_pct": repeat_limit_rel_pct,
        "verify_unmodulated_carrier": verify_unmodulated_carrier,
        "verify_settling_time_s": verify_settling_time_s,
        "verify_sa_config": verify_sa_config,
    }


def get_carrier_frequency_list():
    """生成载波频率列表，单位 Hz。"""
    if carrier_frequency_mode == "list" and carrier_frequency_list:
        return list(carrier_frequency_list)

    frequencies = []
    current = carrier_start_frequency_hz
    while current <= carrier_end_frequency_hz:
        frequencies.append(current)
        current += carrier_step_frequency_hz

    if frequencies and frequencies[-1] != carrier_end_frequency_hz:
        frequencies.append(carrier_end_frequency_hz)

    return frequencies
