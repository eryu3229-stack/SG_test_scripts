#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试主程序
运行信号源的二次谐波测试
"""

import sys
import os
import time
from datetime import datetime

# 添加项目目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)  # 项目根目录
sys.path.append(os.path.join(parent_dir, 'instruments'))
sys.path.append(os.path.join(parent_dir, 'procedures'))
sys.path.append(os.path.join(parent_dir, 'configs'))
sys.path.append(os.path.join(parent_dir, 'utils'))

from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from spectrum_analyzer import SpectrumAnalyzer
from harmonic_test_procedure import HarmonicTestProcedure
from base_test_procedure import format_frequency
from harmonic_test_config import (
    PROJECT_NAME,
    FREQUENCY_SWEEP_CONFIG,
    SPECTRUM_ANALYZER_CONFIG,
    HARMONIC_MEASUREMENT_CONFIG,
    OUTPUT_CONFIG,
    generate_frequency_points,
    get_test_config_summary
)


def connect_instruments():
    """连接仪器"""
    manager = InstrumentManager()

    print("可用仪器:")
    instruments = manager.list_instruments()
    for i, instrument in enumerate(instruments):
        print(f"{i + 1}. {instrument}")

    signal_gen = None
    spectrum_analyzer = None

    # 连接信号源
    sg_resource = input("\n请输入信号源的资源名称 (按Enter跳过): ").strip()
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, 'signal_generator')
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"信号源ID: {signal_gen.get_idn()}")
        else:
            print("信号源连接失败")
    else:
        print("未连接信号源")

    # 连接频谱仪
    sa_resource = input("\n请输入频谱仪的资源名称 (按Enter跳过): ").strip()
    if sa_resource:
        sa_instrument = manager.connect_instrument(sa_resource, 'spectrum_analyzer')
        if sa_instrument:
            spectrum_analyzer = SpectrumAnalyzer(sa_instrument)
            print(f"频谱仪ID: {spectrum_analyzer.get_idn()}")
        else:
            print("频谱仪连接失败")
    else:
        print("未连接频谱仪")

    return manager, signal_gen, spectrum_analyzer


def configure_test():
    """配置测试参数"""
    print("\n" + "=" * 60)
    print("谐波测试配置")
    print("=" * 60)

    # 显示默认配置
    print(get_test_config_summary())

    # 询问是否修改配置
    modify = input("\n是否修改配置? (y/N): ").strip().lower()
    
    # 这里可以添加配置修改逻辑
    # 暂时使用默认配置
    if modify == 'y':
        print("配置修改功能暂未实现，使用默认配置")
    
    return {
        'frequency_sweep_config': FREQUENCY_SWEEP_CONFIG,
        'spectrum_analyzer_config': SPECTRUM_ANALYZER_CONFIG,
        'harmonic_measurement_config': HARMONIC_MEASUREMENT_CONFIG,
        'output_config': OUTPUT_CONFIG
    }


def run_harmonic_test():
    """运行谐波测试"""
    print("\n" + "=" * 60)
    print("谐波测试")
    print("=" * 60)

    # 1. 连接仪器
    manager, signal_gen, spectrum_analyzer = connect_instruments()

    if not signal_gen or not spectrum_analyzer:
        print("\n错误: 信号源和频谱仪都必须连接")
        manager.disconnect_all()
        return

    # 2. 配置测试
    test_config = configure_test()

    # 3. 生成测试点
    test_points = generate_frequency_points()
    print(f"\n生成 {len(test_points)} 个测试点")

    # 4. 初始化测试流程
    test_procedure = HarmonicTestProcedure(manager)

    # 5. 运行测试
    print("\n" + "=" * 60)
    print("开始测试")
    print("=" * 60)

    # 显示时间参数配置
    if test_points and len(test_points) > 0:
        # 使用第一个测试点的配置作为参考
        sample_config = test_points[0]
        settling_time = sample_config.get('settling_time', 0.5)  # 从测试点获取信号源稳定时间
        post_close_wait = test_config['harmonic_measurement_config'].get('post_close_wait', 0.1)  # 从谐波配置获取关闭后等待时间

        print(f"时间参数配置:")
        print(f"  - 信号源稳定时间: {settling_time}秒")
        print(f"  - 信号源关闭后等待时间: {post_close_wait}秒")
    else:
        print("时间参数: 使用默认值（信号源稳定时间0.5秒）")

    print("测试模式: 信号源在测试过程中保持开启，最后一个频点测试完成后关闭")
    print("频谱仪输入耦合: 10MHz以下自动切换为DC耦合，10MHz以上使用AC耦合")
    print("\n开始测试...")

    for i, test_point in enumerate(test_points):
        is_last_point = (i == len(test_points) - 1)

        # 最后一个点测量后关闭输出，其他点保持输出
        keep_output = not is_last_point

        print(f"\n--- 测试点 {i+1}/{len(test_points)} ---")

        # 显示当前点的频率和功率
        print(f"频率: {format_frequency(test_point['frequency'])}, 功率: {test_point['set_power']}dBm")

        # 运行测试
        test_procedure.run_harmonic_test(
            signal_gen,
            spectrum_analyzer,
            test_point,
            test_config['spectrum_analyzer_config'],
            test_config['harmonic_measurement_config'],
            keep_output
        )

        # 如果不是最后一个点，输出保持开启，准备切换到下一个频点
        if not is_last_point:
            print(f"保持输出状态，准备切换到下一个频点...")
            # 这里可以添加一个短暂的延时，确保仪器准备好
            time.sleep(0.1)

    # 所有测试点完成后，确保信号源输出关闭
    print("\n所有测试点完成，关闭信号源输出...")
    signal_gen.enable_output(False)

    # 6. 保存测试结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    filename = f"harmonic_test_results_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    test_procedure.save_results(filepath)
    print(f"测试结果已保存到: {filepath}")
    # 7. 打印测试摘要
    test_procedure.print_summary()

    # 8. 断开仪器连接
    print("\n" + "=" * 60)
    print("断开仪器连接")
    print("=" * 60)
    manager.disconnect_all()

    print("\n测试完成！")


if __name__ == "__main__":
    run_harmonic_test()
