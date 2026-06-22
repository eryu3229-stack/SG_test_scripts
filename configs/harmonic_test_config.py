#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试配置
用于测试信号源的二次谐波性能
"""

# ==================== 基础配置 ====================

# 项目名称
PROJECT_NAME = "谐波测试"

# 测试描述
TEST_DESCRIPTION = "测试信号源的二次谐波性能，记录基波和二次谐波功率"

# ==================== 频率扫描配置 ====================

# 频率扫描配置
FREQUENCY_SWEEP_CONFIG = {
    'start_frequency': 1e9,      # 起始频率: 1 GHz
    'end_frequency': 20e9,         # 结束频率: 20 GHz
    'step_frequency': 100e6,       # 频率步进: 100 MHz
    'fixed_power': 10,              # 固定输出功率: 10 dBm
    'settling_time': 2.0,          # 仪器稳定时间: 2秒
}

# ==================== 频谱仪配置 ====================

# 频谱仪测量配置
SPECTRUM_ANALYZER_CONFIG = {
    'span': 5e3,                  # 频率跨度: 5 kHz
    'rbw': 200,                   # 分辨率带宽: 200 Hz
    'vbw': 200,                   # 视频带宽: 200 Hz
    'reference_level': 20,        # 参考电平: 20 dBm
    'attenuation': 40,             # 衰减: 40dB
    'sweep_time': 0.5,             # 扫描时间: 0.5秒
}

# ==================== 谐波测量配置 ====================

# 谐波测量配置
HARMONIC_MEASUREMENT_CONFIG = {
    'fundamental_marker': 1,       # 基波标记器编号
    'harmonic_order': 2,           # 谐波阶数: 2 (二次谐波)
    'measurement_average': 3,      # 测量平均次数
}

# ==================== 输出配置 ====================

# 结果输出配置
OUTPUT_CONFIG = {
    'output_format': 'excel',      # 输出格式: excel
    'include_timestamp': True,     # 包含时间戳
    'save_raw_data': True,         # 保存原始数据
    'calculate_dbc': True,         # 计算dBc值
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
    harmonic_config = HARMONIC_MEASUREMENT_CONFIG
    
    summary = f"""
谐波测试配置摘要:
===================

1. 频率扫描配置:
   - 起始频率: {freq_config['start_frequency']/1e6:.0f} MHz
   - 结束频率: {freq_config['end_frequency']/1e6:.0f} MHz
   - 频率步进: {freq_config['step_frequency']/1e6:.0f} MHz
   - 固定功率: {freq_config['fixed_power']} dBm
   - 稳定时间: {freq_config['settling_time']} 秒

2. 频谱仪配置:
   - 频率跨度: {sa_config['span']/1e6:.1f} MHz
   - 分辨率带宽: {sa_config['rbw']/1e3:.0f} kHz
   - 参考电平: {sa_config['reference_level']} dBm
   - 扫描时间: {sa_config['sweep_time']} 秒

3. 谐波测量配置:
   - 谐波阶数: {harmonic_config['harmonic_order']}
   - 测量平均次数: {harmonic_config['measurement_average']}

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
        print(f"  {i+1}. {point['frequency']/1e6:.0f}MHz, {point['set_power']}dBm, {point['duration']}秒")
    if len(test_points) > 5:
        print(f"  ... 还有 {len(test_points) - 5} 个测试点")
    
    print(get_test_config_summary())

