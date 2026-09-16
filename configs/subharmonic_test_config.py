# -*- coding: utf-8 -*-
"""
分谐波测试配置
用于测试信号源的分谐波性能
"""

import os
import sys

# 保证可导入 utils（项目根目录加入路径），供 format_frequency 使用
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.formatting import format_frequency


# ==================== 基础配置 ====================

# 项目名称
PROJECT_NAME = "分谐波测试"

# 测试描述
TEST_DESCRIPTION = "测试信号源的分谐波性能，记录基波和分谐波功率"

# ==================== 频率扫描配置 ====================

# 频率扫描配置
FREQUENCY_SWEEP_CONFIG = {
    'start_frequency': 100e6,      # 起始频率: 200MHz (确保分谐波在可测量范围内)
    'end_frequency': 1e9,          # 结束频率: 1GHz
    'step_frequency': 100e6,       # 频率步进: 200MHz
    'fixed_power': 10,              # 固定输出功率: 10 dBm
    'settling_time': 1.0,          # 仪器稳定时间: 1秒
}

# ==================== 频谱仪配置 ====================

# 频谱仪测量配置
SPECTRUM_ANALYZER_CONFIG = {
    'span': 10e3,                  # 频率跨度: 10 kHz
    'rbw': 100,                    # 分辨率带宽: 100 Hz
    'vbw': 100,                    # 视频带宽: 100 Hz
    'reference_level': 10,         # 参考电平: 10dBm
    'attenuation': 40,             # 衰减: 40dB
    'input_coupling': 'AC',        # 频率 >= dc_coupling_below_hz 时使用的耦合方式
    'dc_coupling_below_hz': 10e6,  # 低于该频率自动用 DC 耦合（AC 耦合有低频截止，会压低低频读数）
}

# ==================== 分谐波测量配置 ====================

# 分谐波测量配置
SUBHARMONIC_MEASUREMENT_CONFIG = {
    'subharmonic_orders': [2],     # 分谐波阶数: 2 (1/2)
    'measurement_average': 3,      # 测量平均次数
    'subharmonic_search_offset': 2e3, # 分谐波搜索偏移: 1MHz
}

# ==================== 测试点生成函数 ====================

def generate_frequency_points():
    """生成频率测试点"""
    config = FREQUENCY_SWEEP_CONFIG
    points = []
    
    current_freq = config['start_frequency']
    while current_freq <= config['end_frequency']:
        points.append({
            'frequency': current_freq,
            'set_power': config['fixed_power'],
            'settling_time': config['settling_time'],
        })
        current_freq += config['step_frequency']
    
    # 确保包含结束点
    if points and points[-1]['frequency'] != config['end_frequency']:
        points.append({
            'frequency': config['end_frequency'],
            'set_power': config['fixed_power'],
            'settling_time': config['settling_time'],
        })
    
    return points


def get_test_config_summary():
    """获取测试配置摘要"""
    freq_config = FREQUENCY_SWEEP_CONFIG
    sa_config = SPECTRUM_ANALYZER_CONFIG
    subharmonic_config = SUBHARMONIC_MEASUREMENT_CONFIG
    
    summary = f"""
分谐波测试配置摘要:
===================

1. 频率扫描配置:
   - 起始频率: {format_frequency(freq_config['start_frequency'])}
   - 结束频率: {format_frequency(freq_config['end_frequency'])}
   - 频率步进: {format_frequency(freq_config['step_frequency'])}
   - 固定功率: {freq_config['fixed_power']} dBm
   - 稳定时间: {freq_config['settling_time']} 秒

2. 频谱仪配置:
   - 频率跨度: {format_frequency(sa_config['span'])}
   - 分辨率带宽: {format_frequency(sa_config['rbw'])}
   - 参考电平: {sa_config['reference_level']} dBm
   - 输入耦合: 低于 {format_frequency(sa_config['dc_coupling_below_hz'])} 用 DC，以上用 {sa_config['input_coupling']}

3. 分谐波测量配置:
   - 分谐波阶数: {', '.join([f'1/{order}' for order in subharmonic_config['subharmonic_orders']])}
   - 测量平均次数: {subharmonic_config['measurement_average']}
   - 分谐波搜索偏移: {format_frequency(subharmonic_config['subharmonic_search_offset'])}

预计测试点数: {len(generate_frequency_points())}
"""
    return summary


# ==================== 主函数 ====================

if __name__ == "__main__":
    # 测试代码
    print(f"项目名称: {PROJECT_NAME}")
    print(f"测试描述: {TEST_DESCRIPTION}")
    
    test_points = generate_frequency_points()
    print(f"\n生成的测试点 ({len(test_points)}个):")
    for i, point in enumerate(test_points[:5]):  # 只显示前5个
        print(f"  {i+1}. {format_frequency(point['frequency'])}, {point['set_power']}dBm")
    if len(test_points) > 5:
        print(f"  ... 还有 {len(test_points) - 5} 个测试点")
    
    print(get_test_config_summary())
