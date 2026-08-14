# -*- coding: utf-8 -*-
"""单频点功率扫描配置

在固定频点上按 start_power -> end_power 扫描信号源设定功率，
使用功率计逐点测量实际输出功率。
"""

# 测试项目名称
project_name = "单频点功率扫描"

# 固定测量频点（Hz）
frequency = 1e9

# 功率扫描范围（dBm）
start_power = -40.0
end_power = 10.0
power_step = 1.0

# 信号源切换功率后的稳定时间（秒）
settling_time = 1.0
# 功率计频率切换后的稳定时间（秒）
pm_settling_time = 0.5
# 信号源关闭后的等待时间（秒）
post_close_wait = 0.1
# 每个功率点的测量次数
measurement_times = 5

# 保护参数（dBm）
max_set_power = 20.0         # 信号源设定功率上限
max_measured_power = 23.0    # 功率计最大输入功率保护

# 衰减器补偿（dB）
attenuator_enabled = False
attenuator_value = 10.0

# 生成扫描功率点（包含结束点）
power_points = []
current_power = start_power
while current_power <= end_power + 1e-9:
    power_points.append(round(current_power, 6))
    current_power += power_step

# 单次测试配置
test_config = {
    "test_name": (
        f"{frequency / 1e9:.3f}GHz功率扫描"
        if frequency >= 1e9
        else f"{frequency / 1e6:.3f}MHz功率扫描"
    ),
    "frequency": frequency,
    "start_power": start_power,
    "end_power": end_power,
    "power_step": power_step,
    "power_points": power_points,
    "settling_time": settling_time,
    "pm_settling_time": pm_settling_time,
    "post_close_wait": post_close_wait,
    "measurement_times": measurement_times,
    "max_set_power": max_set_power,
    "max_measured_power": max_measured_power,
    "attenuator_enabled": attenuator_enabled,
    "attenuator_value": attenuator_value,
}
