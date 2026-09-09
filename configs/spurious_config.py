# -*- coding: utf-8 -*-

project_name = "杂散测量"

# 载波频率生成方式:
# "step" = 使用起始/结束/步进自动生成
# "list" = 使用 carrier_frequency_list 显式列表
carrier_frequency_mode = "step"

# 显式载波频率列表，仅 carrier_frequency_mode = "list" 时使用
carrier_frequency_list = []

# 步进式载波频率参数，单位 Hz
carrier_start_frequency_hz = 3.5e9
carrier_end_frequency_hz = 40e9
carrier_step_frequency_hz = 500e6

# 载波功率，单位 dBm
carrier_power_dbm = 10

# 频谱仪通用参数
reference_level_dbm = 10
attenuation_db = 20
input_coupling = "DC"
sa_settling_time_s = 0.5
scale_div_db = 15

# 频率边界，防止设置到仪器不支持范围
min_frequency_hz = 9e3
max_frequency_hz = 20e9

# ============================================================
# 分段扫描定义
# ============================================================
# 思路：速度不是核心，全面覆盖是核心。
# 近载波用窄 RBW 保证灵敏度；远载波用宽 RBW 覆盖范围。
# 每段独立配置 SPAN / RBW / VBW / MAXH 扫描次数。

# 近载波段：以载波为中心，两侧对称搜索
near_carrier_segments = [
    # 10 MHz SPAN：覆盖 ±5 MHz，RBW 100 Hz，用于捕捉近载波窄杂散
    {
        "name": "near_10MHz",
        "span_hz": 10e6,
        "rbw_hz": 100,
        "vbw_hz": 300,
        "sweep_count": 5,
        "trace_mode": "MAXH",
        "detector": "POS",
    },
    # 100 MHz SPAN：覆盖 ±50 MHz，RBW 1 kHz
    {
        "name": "near_100MHz",
        "span_hz": 100e6,
        "rbw_hz": 1e3,
        "vbw_hz": 3e3,
        "sweep_count": 5,
        "trace_mode": "MAXH",
        "detector": "POS",
    },
]

# 远载波段：以载波为中心，向两侧扩展 coverage_hz 范围分段扫描
# 例如 coverage_hz=2e9 时，1.5 GHz 载波只扫 0.5-2.5 GHz，不再扫到 10 GHz
far_carrier_segment = {
    "name": "far_1GHz",
    "span_hz": 1e9,
    "rbw_hz": 10e3,
    "vbw_hz": 30e3,
    "sweep_count": 3,
    "trace_mode": "MAXH",
    "detector": "POS",
    "coverage_hz": 2e9,   # 以 CF 为中心，总覆盖宽度
}

# 谐波：单独逐阶测量，避免和谐波区重复搜索
harmonic_config = {
    "orders": [2, 3, 4, 5, 6],
    "span_hz": 10e6,
    "rbw_hz": 1e3,
    "vbw_hz": 3e3,
    "sweep_count": 5,
    "trace_mode": "MAXH",
    "detector": "POS",
    "tolerance_hz": 1e6,  # |f - n*CF| <= tol 判为谐波
}

# 精测参数：对 candidate 用窄 SPAN + 窄 RBW 复测
refine_config = {
    "span_hz": 1e6,
    "rbw_hz": 100,
    "vbw_hz": 300,
    "sweep_count": 3,
    "trace_mode": "WRITE",
    "detector": "POS",
    "average_count": 3,   # 从 5 减到 3
}

# ============================================================
# 峰值检测参数
# ============================================================
# prominence 放低，尽量把可疑点都抓出来；后续精测和验证再过滤
peak_detection = {
    "noise_margin_db": 6.0,          # 高于噪声底多少 dB 算候选
    "peak_prominence_db": 3.0,       # 局部峰值相对于邻域的突出程度
    "min_peak_distance_hz": 1e3,     # 两个候选峰最小频率间隔
    "max_peak_count_per_segment": 30,  # 每段最多保留候选，减少精测/验证负担
}

# 近载波保护带：载波本身及附近不搜索杂散（避免把主信号当杂散）
carrier_guard_hz = 10e3  

# 最小有效杂散偏移：相对于载波的最小频率偏移
# 小于该值的峰视为载波自身分量/测量伪影，直接丢弃
min_spur_offset_hz = 5e3  # 5 kHz

# ============================================================
# 候选杂散真伪验证
# ============================================================
validation = {
    "enable": True,

    # 源开关测试：关 RF 后若杂散仍在，判为仪器/环境杂散
    # 默认关闭，非常耗时（需要关源、重扫多个 segment）
    "source_off_check": False,

    # 衰减器阶跃测试：改衰减后 dBc 不变才是真杂散
    "attenuator_step_check": True,
    "attenuator_step_db": 2,
    "attenuator_steps": [0, 2],   # 只测当前值和 +2 dB，减少耗时
    "attenuator_dbc_tolerance_db": 2.0,

    # 载波频率步进测试：真杂散应随 CF 同步偏移
    "cf_step_check": False,  # 默认关闭，因会改变整个测试状态；可手动开启
    "cf_step_hz": 10e6,
    "cf_step_freq_tolerance_hz": 100e3,

    # RBW 缩放测试：真 CW 杂散幅度不随 RBW 变化；噪声会涨
    "rbw_scaling_check": True,
    "rbw_scaling_ratios": [1, 2],
    "rbw_scaling_amplitude_tolerance_db": 2.0,

    # 重复性测试
    "stability_count": 3,   # 精测时只读 3 次
    "stability_limit_db": 1.0,

    # 接近噪声底判定
    "noise_floor_reliable_margin_db": 10.0,
}

# 输出控制
output = {
    # 每段保留多少个候选参与最终验证（None 表示保留全部）
    "max_candidates_per_segment": 15,  # 只验证/输出 worst-case 前 15
    # 是否输出谐波条目
    "include_harmonics": False,
    # 是否输出验证失败的 suspected/noise/artifact 条目
    "include_unconfirmed": True,
}


def get_config():
    """返回完整配置字典"""
    return {
        "reference_level_dbm": reference_level_dbm,
        "attenuation_db": attenuation_db,
        "input_coupling": input_coupling,
        "sa_settling_time_s": sa_settling_time_s,
        "min_frequency_hz": min_frequency_hz,
        "max_frequency_hz": max_frequency_hz,
        "near_carrier_segments": near_carrier_segments,
        "far_carrier_segment": far_carrier_segment,
        "harmonic_config": harmonic_config,
        "refine_config": refine_config,
        "peak_detection": peak_detection,
        "carrier_guard_hz": carrier_guard_hz,
        "validation": validation,
        "output": output,
    }


def get_carrier_frequency_list():
    """生成载波频率列表"""
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
