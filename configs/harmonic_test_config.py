# -*- coding: utf-8 -*-
"""
谐波测试配置
用于测试信号源的二次谐波性能
"""

import os
import sys

# 保证可导入 utils（项目根目录加入路径），供 format_frequency 使用
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.formatting import format_frequency


# ==================== 基础配置 ====================

# 项目名称
PROJECT_NAME = "谐波测试"

# 测试描述
TEST_DESCRIPTION = "测试信号源的二次谐波性能，记录基波和二次谐波功率"

# ==================== 频率扫描配置 ====================

# 频率扫描配置
FREQUENCY_SWEEP_CONFIG = {
    'start_frequency': 19e9,       # 起始频率: 3 kHz
    'end_frequency': 20e9,          # 结束频率: 100 kHz
    'step_frequency': 10e7,         # 频率步进: 1 kHz
    'fixed_power': 10,              # 固定输出功率: 10 dBm
    'frequency_settling_time': 0.8, # 频率切换稳定时间，单位：秒
    'settling_time': 0.5,           # 仪器稳定时间: 0.5秒
}

# ==================== 频谱仪配置 ====================

# 频谱仪测量配置
SPECTRUM_ANALYZER_CONFIG = {
    'span': 10e3,                  # 频率跨度: 10 kHz
    'rbw': 10,                   # 分辨率带宽: 200 Hz
    'vbw': 10,                   # 视频带宽: 200 Hz
    'reference_level': 15,        # 参考电平: 20 dBm
    'attenuation': 30,            # 衰减: 40dB
    'scale_div_db': 15,           # Y轴刻度: 15 dB/div
    'input_coupling': 'AC',        # 频率 >= dc_coupling_below_hz 时使用的耦合方式
    'dc_coupling_below_hz': 10e6,  # 低于该频率自动用 DC 耦合（AC 耦合有低频截止，会压低低频读数）
    # 输入耦合能力：本机 N9030B 只支持 DC 耦合，下发 `INP:COUP AC` 会被固件拒绝
    #（错误队列留下一条 -113）。置 False 后程序直接把 AC 折算成 DC —— 不影响读数
    #（仪器本来就保持 DC），只是不再反复下发一条注定被拒的命令。
    # 换用支持 AC 耦合的机器时改回 True。
    'input_coupling_ac_supported': False,
    'sa_settling_time': 0.5,      # 频谱仪稳定等待时间: 0.5秒
    # 采集方式：不再使用"等够时间"的同步参数。
    # 每次读数 = acquire_once()（INIT:IMM + *OPC?），即一次完整扫描，
    # 三次平均 = 三次独立完整扫描。原 sweep_sync_kwargs（factor/margin/extra_margin）
    # 属于时间法盲等，已随采集原语拆分删除。
}

# ==================== 谐波测量配置 ====================

# 谐波测量配置
HARMONIC_MEASUREMENT_CONFIG = {
    'fundamental_marker': 1,       # 基波标记器编号
    'harmonic_order': 2,           # 谐波阶数: 2 (二次谐波)
    'measurement_average': 3,      # 平均次数 = 独立单次采集次数（固定值，不做自适应）
    'measurement_attempts': 3,     # 最多尝试次数（1 次原始 + 2 次重试）；用尽即判 FAIL 并中止
    'retry_delay_s': 0.3,          # 两次尝试之间的等待秒数
    'harmonic_detection_margin_db': 10,   # 峰包络高于本地噪声底多少 dB 才判为"检出谐波"
    'harmonic_freq_tolerance_ratio': 0.25, # 频率冗余判据相对 span 的比例
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
            'frequency_settling_time': config['frequency_settling_time'],
            'set_power': config['fixed_power'],
            'settling_time': config['settling_time'],
        })
        current_freq += config['step_frequency']
    
    # 确保包含结束点
    if points and points[-1]['frequency'] != config['end_frequency']:
        points.append({
            'frequency': config['end_frequency'],
            'frequency_settling_time': config['frequency_settling_time'],
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
   - 起始频率: {format_frequency(freq_config['start_frequency'])}
   - 结束频率: {format_frequency(freq_config['end_frequency'])}
   - 频率步进: {format_frequency(freq_config['step_frequency'])}
   - 固定功率: {freq_config['fixed_power']} dBm
   - 频率切换稳定时间: {freq_config['frequency_settling_time']} 秒
   - 稳定时间: {freq_config['settling_time']} 秒

2. 频谱仪配置:
   - 频率跨度: {format_frequency(sa_config['span'])}
   - 分辨率带宽: {format_frequency(sa_config['rbw'])}
   - 参考电平: {sa_config['reference_level']} dBm
   - 输入耦合: 低于 {format_frequency(sa_config['dc_coupling_below_hz'])} 用 DC，以上用 {sa_config['input_coupling']}

3. 谐波测量配置:
   - 谐波阶数: {harmonic_config['harmonic_order']}
   - 测量平均次数: {harmonic_config['measurement_average']}
   - 谐波检出门限: {harmonic_config['harmonic_detection_margin_db']} dB (高于本地噪声底)

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
        print(f"  {i+1}. {format_frequency(point['frequency'])}, {point['set_power']}dBm, {point['settling_time']}秒")
    if len(test_points) > 5:
        print(f"  ... 还有 {len(test_points) - 5} 个测试点")
    
    print(get_test_config_summary())

