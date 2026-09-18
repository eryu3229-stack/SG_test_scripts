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
    'end_frequency': 40e9,          # 结束频率: 1GHz
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
    # 输入耦合能力：本机 N9030B 只支持 DC 耦合，下发 AC 会被固件拒绝（错误队列 -113）。
    # 置 False 后程序直接把 AC 折算成 DC（不影响读数），不再产生该错误。
    # 换用支持 AC 耦合的机器时改回 True。
    'input_coupling_ac_supported': False,
}

# ==================== 分谐波测量配置 ====================

# 分谐波测量配置
SUBHARMONIC_MEASUREMENT_CONFIG = {
    # 分谐波阶数（分母）：2 → 测 f/2，[2,3,5] → 分别测 f/2、f/3、f/5。
    # 注意：当前实现只支持 **1/n** 形式。实际分谐波常见多种分数（1/3、3/5 等），
    # 分母为 n 的用整数即可；像 3/5 这种分子不为 1 的分数当前无法表达
    #（写 order=5/3 会让列值与 note 出现 "1/1.666…" 这种字样），如需支持另议。
    # 另外：分谐波幅度通常很低，大概率落在底噪里 —— **测不到是常态**，
    # 此时读数为分谐波频率处的底噪，dBc 应按"抑制上限"理解。
    'subharmonic_orders': [2],
    'measurement_average': 3,      # 平均次数 = 独立单次采集次数（固定值，不做自适应）
    'measurement_attempts': 3,     # 最多尝试次数（1 次原始 + 2 次重试）；用尽即判 FAIL 并中止
    'retry_delay_s': 0.3,          # 两次尝试之间的等待秒数
    # 检出判据（只用于"是否标注为底噪读数"，**不影响 status**）：
    # 读数为底噪时 note 写明"未检出"，并在 sa_noise_floor_dbm 列记录本地底噪
    'subharmonic_detection_margin_db': 10,    # 读数高于本地底噪多少 dB 才算检出
    'subharmonic_freq_tolerance_ratio': 0.25, # 峰位容差相对 span 的比例（另受 rbw×5、500 Hz 下限约束）
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
