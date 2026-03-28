#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分谐波测试主程序
运行信号源的分谐波测试
"""

import sys
import os
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
from subharmonic_test_procedure import SubharmonicTestProcedure
from subharmonic_test_config import (
    PROJECT_NAME,
    FREQUENCY_SWEEP_CONFIG,
    SPECTRUM_ANALYZER_CONFIG,
    SUBHARMONIC_MEASUREMENT_CONFIG,
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
    print("分谐波测试配置")
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
        'subharmonic_measurement_config': SUBHARMONIC_MEASUREMENT_CONFIG,
        'output_config': OUTPUT_CONFIG
    }


def run_subharmonic_test():
    """运行分谐波测试"""
    print("\n" + "=" * 60)
    print("分谐波测试")
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
    test_procedure = SubharmonicTestProcedure(manager)

    # 5. 运行测试
    print("\n" + "=" * 60)
    print("开始测试")
    print("=" * 60)

    # 运行测试，最后一个测试点之前保持输出开启
    for i, test_point in enumerate(test_points):
        # 最后一个测试点不保持输出，其他测试点保持输出
        keep_output = (i < len(test_points) - 1)
        test_procedure.run_subharmonic_test(
            signal_gen,
            spectrum_analyzer,
            test_point,
            test_config['spectrum_analyzer_config'],
            test_config['subharmonic_measurement_config'],
            keep_output=keep_output
        )

    # 6. 保存测试结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    output_format = test_config['output_config'].get('output_format', 'excel')
    
    if output_format == 'excel':
        filename = f"subharmonic_test_results_{timestamp}.xlsx"
    else:
        filename = f"subharmonic_test_results_{timestamp}.csv"
    
    filepath = os.path.join(output_dir, filename)
    test_procedure.save_results(filepath)

    # 7. 打印测试摘要
    test_procedure.print_summary()

    # 8. 断开仪器连接
    print("\n" + "=" * 60)
    print("断开仪器连接")
    print("=" * 60)
    manager.disconnect_all()

    print("\n测试完成！")


if __name__ == "__main__":
    run_subharmonic_test()
