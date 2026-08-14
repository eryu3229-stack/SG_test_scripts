#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单频点功率扫描入口脚本（功率计版本）"""

import os
import sys
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, 'instruments'))
sys.path.append(os.path.join(parent_dir, 'procedures'))
sys.path.append(os.path.join(parent_dir, 'configs'))

from instrument_manager import InstrumentManager
from power_meter import PowerMeter
from signal_generator import SignalGenerator
from single_frequency_power_sweep_config import project_name, test_config
from single_frequency_power_sweep_procedure import SingleFrequencyPowerSweepProcedure


def main():
    """主函数。"""
    manager = InstrumentManager()

    print("可用仪器:")
    instruments = manager.list_instruments()
    for i, instrument in enumerate(instruments):
        print(f"{i + 1}. {instrument}")

    signal_gen = None
    power_meter = None

    sg_resource = input(
        "请输入信号源的资源名称(例如 TCPIP::192.168.1.100::INSTR): "
    )
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, 'signal_generator')
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"信号源ID: {signal_gen.get_idn()}")

    pm_resource = input(
        "请输入功率计的资源名称(例如 USB::0x0AAD::0x015F::101930::INSTR): "
    )
    if pm_resource:
        pm_instrument = manager.connect_instrument(pm_resource, 'power_meter')
        if pm_instrument:
            power_meter = PowerMeter(pm_instrument)
            print(f"功率计ID: {power_meter.get_idn()}")

    if not signal_gen or not power_meter:
        print("仪器连接失败，无法继续。")
        manager.disconnect_all()
        return

    print("\n" + "=" * 60)
    print("请确认功率计已断开连接，处于开路状态！")
    print("=" * 60)
    while True:
        confirm = input("确认功率计已断开连接并处于开路状态? (y/n): ").strip().lower()
        if confirm == 'y':
            break
        if confirm == 'n':
            print("请断开功率计连接后再继续。")
        else:
            print("请输入 y 或 n")

    try:
        print("正在执行功率计归零...")
        power_meter.zero()
        print("功率计归零完成。")
    except Exception:
        print("归零失败，终止测试。")
        manager.disconnect_all()
        return

    print("\n" + "=" * 60)
    print("请重新连接功率计输入信号")
    print("=" * 60)
    input("连接完成后按 Enter 键继续...")

    procedure = SingleFrequencyPowerSweepProcedure(manager)

    power_points = test_config['power_points']
    print(f"\n开始测试项目: {project_name}")
    print(f"测量频率: {test_config['frequency']} Hz")
    if power_points:
        print(f"功率范围: {power_points[0]} ~ {power_points[-1]} dBm, "
              f"共 {len(power_points)} 个点")
    else:
        print("功率范围为空，请检查配置文件。")
    print(f"信号源稳定时间: {test_config['settling_time']} 秒")
    print(f"功率计测量次数: {test_config['measurement_times']} 次")
    if test_config['attenuator_enabled']:
        print(f"衰减器补偿: {test_config['attenuator_value']} dB")
    else:
        print("衰减器补偿: 未启用")

    try:
        procedure.run_test(signal_gen, power_meter, test_config)
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        try:
            signal_gen.enable_output(False)
        except Exception:
            pass
        manager.disconnect_all()
        raise

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{project_name}_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    procedure.save_results(filepath)
    print(f"测试结果已保存到: {filepath}")

    manager.disconnect_all()


if __name__ == "__main__":
    main()
