# -*- coding: utf-8 -*-

project_name = "小信号测量"

# 被测频率列表，单位 Hz
frequency_list = [
    10e6,
    50e6,
    100e6,
    200e6,
    500e6,
    1e9,
]

# 从高到低排列的功率扫描列表，单位 dBm
power_list_dbm = [
    10,
    0,
    -10,
    -20,
    -30,
    -40,
    -50,
    -60,
    -70,
    -80,
    -90,
    -100,
]

# 稳定时间，单位秒
frequency_settling_time = 1.0
power_settling_time = 1.0
sa_settling_time = 0.5

# 测量次数，频谱仪 marker 多次读数取平均
average_count = 5

# 频谱仪搜索参数
initial_span = 1e6
initial_rbw = 1e3
initial_vbw = 1e3
min_span = 5e3
min_rbw = 10
min_vbw = 10

# 允许的目标信号频率偏差，单位 Hz
freq_tolerance_hz = 10e3

# 参考电平和衰减建议值
reference_level_margin_db = 10
max_reference_level = 20
min_reference_level = -80
high_power_threshold_dbm = -20
attenuation_for_high_power = 10
attenuation_for_low_power = 0

# 频谱仪输入耦合，低频可使用 DC
input_coupling = "AC"


def get_config():
    return {
        "frequency_settling_time": frequency_settling_time,
        "power_settling_time": power_settling_time,
        "sa_settling_time": sa_settling_time,
        "average_count": average_count,
        "initial_span": initial_span,
        "initial_rbw": initial_rbw,
        "initial_vbw": initial_vbw,
        "min_span": min_span,
        "min_rbw": min_rbw,
        "min_vbw": min_vbw,
        "freq_tolerance_hz": freq_tolerance_hz,
        "reference_level_margin_db": reference_level_margin_db,
        "max_reference_level": max_reference_level,
        "min_reference_level": min_reference_level,
        "high_power_threshold_dbm": high_power_threshold_dbm,
        "attenuation_for_high_power": attenuation_for_high_power,
        "attenuation_for_low_power": attenuation_for_low_power,
        "input_coupling": input_coupling,
    }
