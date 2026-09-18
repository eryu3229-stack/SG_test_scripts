# -*- coding: utf-8 -*-

project_name = "小信号测量"

# ==================== 频率设置 ====================
# 频率生成方式：
#   "step" = 用下面的起止步进自动生成（默认）
#   "list" = 用 frequency_list 显式列表（旧用法，保留兼容；点位可非均匀）
frequency_mode = "step"

# 步进式频率参数，单位 Hz
frequency_config = {
    'start_frequency': 1e9,      # 起始频率（含）
    'end_frequency': 40e9,       # 终止频率（含）
    'step_frequency': 1e9,       # 频率步进
    'include_end': True,         # 末点不落在步进网格上时，是否补一个终止点
}

# 显式频率列表，仅 frequency_mode = "list" 时使用
frequency_list = [
    1e9,
    2e9,
    5e9,
    6e9,
    10e9,
    20e9,
]

# 从高到低排列的功率扫描列表，单位 dBm
power_list_dbm = [
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

# 内置预放（按品牌自动映射）
#   罗德 FSWP: INPut:GAIN:STATe + INPut:GAIN:VALue（增益值 15/30 dB）
#   是德 X 系列: POWer:RF:GAIN:STATe + :GAIN:BAND（波段 LOW/FULL）
# 低功率测量时打开预放压低底噪；高功率时关闭防止过载
preamp_enabled = True            # 总开关：False 则全程不开预放
preamp_threshold_dbm = -50       # 设定功率 <= 该值时开预放
preamp_band = "FULL"             # 兼容写法：LOW→罗德15dB/是德低波段，FULL→罗德30dB/是德全波段

# 频谱仪输入耦合
# 低于 dc_coupling_below_hz 的频点用 DC（AC 耦合有低频截止，会压低低频读数）
# 其余频点用 input_coupling 指定的值；每个频点只下发一次，不随功率点重复
input_coupling = "AC"
dc_coupling_below_hz = 10e6
# 输入耦合能力：本机 N9030B 只支持 DC 耦合，下发 AC 会被固件拒绝（错误队列 -113）。
# 置 False 后程序直接把 AC 折算成 DC（不影响读数），不再产生该错误。
# 换用支持 AC 耦合的机器时改回 True。
input_coupling_ac_supported = False


def generate_frequency_list():
    """按 `frequency_mode` 生成被测频率列表（单位 Hz，升序）

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
    # 浮点误差可能让最后一个点越过终止频率，丢掉它
    while len(frequencies) > 1 and frequencies[-1] > end + tol:
        frequencies.pop()
    if frequency_config.get('include_end', True) and abs(frequencies[-1] - end) > tol:
        frequencies.append(end)
    return frequencies


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
        "input_coupling_ac_supported": input_coupling_ac_supported,
    }
