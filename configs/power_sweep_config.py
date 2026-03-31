# 测试项目配置文件

# 测试项目名称
project_name = "扫频测试"

# 测试配置：从10MHz到10GHz，步进100MHz，支持多个功率设置
test_configs = []
start_freq = 50e6      # 10MHz (科学计数法)
end_freq = 40e9        # 10GHz (科学计数法)
step_freq = 10e6      # 100MHz (科学计数法)

# 多个功率设置（dBm）
power_settings = [-10, -25, 0]  # 可以添加更多功率值

# 测试参数配置
settling_time = 0.8      # 信号源稳定时间（秒）
pm_settling_time = 0.5   # 功率计频率切换稳定时间（秒）
post_close_wait = 0.1     # 信号源关闭后等待时间（秒）
measurement_times = 3     # 功率计测量次数
attenuator_enabled = False  # 是否启用衰减器
attenuator_value = 10        # 固定衰减器值（dB）
attenuator_freq_dependent = False  # 是否使用频率相关衰减器

# 为每个功率设置生成测试点
for power in power_settings:
    current_freq = start_freq
    while current_freq <= end_freq:
        test_configs.append({
            'test_name': f'{current_freq/1e6:.0f}MHz_{power}dBm测试',
            'frequency': current_freq,
            'power': power,  # 使用当前功率设置
            'settling_time': settling_time,
            'pm_settling_time': pm_settling_time,
            'post_close_wait': post_close_wait,
            'measurement_times': measurement_times,
            'attenuator_enabled': attenuator_enabled,
            'attenuator_value': attenuator_value,
            'attenuator_freq_dependent': attenuator_freq_dependent
        })
        current_freq += step_freq
    
    # 确保包含结束点
    if test_configs and test_configs[-1]['frequency'] != end_freq:
        test_configs.append({
            'test_name': f'{end_freq/1e6:.0f}MHz_{power}dBm测试',
            'frequency': end_freq,
            'power': power,
            'settling_time': settling_time,
            'pm_settling_time': pm_settling_time,
            'post_close_wait': post_close_wait,
            'measurement_times': measurement_times,
            'attenuator_enabled': attenuator_enabled,
            'attenuator_value': attenuator_value,
            'attenuator_freq_dependent': attenuator_freq_dependent
        })
