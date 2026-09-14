# -*- coding: utf-8 -*-

project_name = "小信号测量"

# 被测频率列表，单位 Hz
frequency_list = [
    1e7,
    10e7,
    1e9,
    6e9,
    10e9
]

# 从高到低排列的功率扫描列表，单位 dBm
power_list_dbm = [
    -70,
    -80,
    -90,
    -100,
    -110,
    -120
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
# 衰减模式：True=自动衰减（POW:ATT:AUTO ON，仪器按参考电平自动耦合）
#          False=手动，用下面两个固定值
attenuation_auto = True
attenuation_for_high_power = 10
attenuation_for_low_power = 0

# 内置预放（N9030B，手册: [:SENSe]:POWer[:RF]:GAIN[:STATe] / :GAIN:BAND）
# 低功率测量时打开预放压低底噪；高功率时关闭防止过载
preamp_enabled = True            # 总开关：False 则全程不开预放
preamp_threshold_dbm = -50       # 设定功率 <= 该值时开预放
preamp_band = "FULL"             # LOW=仅低波段, FULL=全频段

# 频谱仪输入耦合
# 低于 dc_coupling_below_hz 的频点用 DC（AC 耦合有低频截止，会压低低频读数）
# 其余频点用 input_coupling 指定的值；每个频点只下发一次，不随功率点重复
input_coupling = "AC"
dc_coupling_below_hz = 10e6


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
        "attenuation_auto": attenuation_auto,
        "attenuation_for_high_power": attenuation_for_high_power,
        "attenuation_for_low_power": attenuation_for_low_power,
        "preamp_enabled": preamp_enabled,
        "preamp_threshold_dbm": preamp_threshold_dbm,
        "preamp_band": preamp_band,
        "input_coupling": input_coupling,
        "dc_coupling_below_hz": dc_coupling_below_hz,
    }
