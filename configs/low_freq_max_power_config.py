# -*- coding: utf-8 -*-
# 低频段最大功率测试配置文件

import os
import sys

# 保证可导入 utils（项目根目录加入路径），供 format_frequency 使用
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.formatting import format_frequency


# 测试项目名称
project_name = "低频段最大功率测试"

# 时间参数配置
settling_time = 0.7           # 信号源稳定时间，单位：秒
sa_settling_time = 0.5        # 频谱仪频率切换稳定时间，单位：秒
post_close_wait = 0.1         # 信号源关闭后等待时间，单位：秒
measurement_times = 3         # 频谱仪测量次数

# 功率扫描参数
start_power = 15             # 起始功率，单位dBm
stop_power = 30              # 扫描终止功率，单位dBm（达到此值后正常停止扫描）
power_step = 1.0              # 功率步进，单位dB
max_set_power = 30            # 信号源最大设定功率硬限制，单位dBm（安全冗余，必须 >= stop_power）
max_measured_power = 30       # 频谱仪最大输入功率（测量值，未补偿衰减），单位dBm（保护频谱仪）
power_tolerance = 0.5         # 功率测量容差，单位dB（用于检测饱和）
max_power_drop = 1.0          # 最大功率下降值，单位dB（如果功率下降超过此值，则认为过载）

# 衰减器配置
attenuator_value = 30.0        # 衰减器衰减值，单位dB（正数表示衰减）
use_attenuator = True        # 是否使用衰减器

# 低频段频率步进配置
frequency_ranges = [
     {'start': 9e3, 'end': 100e3, 'step': 1e3},     # 3k-100kHz，步进10kHz
     {'start': 100e3, 'end': 1e6, 'step': 10e3},    # 100kHz-1MHz，步进100kHz
     {'start': 1e6, 'end': 50e6, 'step': 100e3},       # 1MHz-50MHz，步进1MHz
]

# 频谱仪配置
spectrum_analyzer_config = {
    'input_coupling': 'DC',      # 输入耦合方式：DC
    'span': 5e3,                # 频率跨度：100kHz
    'rbw': 50,                   # 分辨率带宽：1kHz
    'vbw': 100,                   # 视频带宽：100Hz
    'reference_level': 30,         # 参考电平：20dBm
    'attenuation': 40,             # 衰减：10dB
    }

# 生成测试配置
test_configs = []

# 处理每个频率范围
for freq_range in frequency_ranges:
    start = freq_range['start']
    end = freq_range['end']
    step = freq_range['step']

    current_freq = start
    while current_freq <= end:
        test_configs.append({
            'test_name': f'{format_frequency(current_freq)}最大功率测试',
            'frequency': current_freq,
            'start_power': start_power,
            'stop_power': stop_power,
            'power_step': power_step,
            'max_set_power': max_set_power,
            'max_measured_power': max_measured_power,
            'power_tolerance': power_tolerance,
            'max_power_drop': max_power_drop,
            'attenuator_value': attenuator_value,
            'use_attenuator': use_attenuator,
            'settling_time': settling_time,
            'sa_settling_time': sa_settling_time,
            'post_close_wait': post_close_wait,
            'measurement_times': measurement_times,
            'spectrum_analyzer_config': spectrum_analyzer_config
        })
        current_freq += step

# 按频率排序（确保配置按频率升序排列）
test_configs.sort(key=lambda x: x['frequency'])
