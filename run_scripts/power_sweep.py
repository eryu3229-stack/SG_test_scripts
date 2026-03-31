import sys
import os
import time

# 添加项目目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)  # 项目根目录
sys.path.append(os.path.join(parent_dir, 'instruments'))
sys.path.append(os.path.join(parent_dir, 'procedures'))
sys.path.append(os.path.join(parent_dir, 'configs'))

from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from power_meter import PowerMeter
from power_sweep_procedure import TestProcedure
from datetime import datetime
from power_sweep_config import project_name, test_configs


# 主函数
def main():
    """主函数"""
    # 初始化仪器管理器
    manager = InstrumentManager()

    # 列出可用仪器
    print("可用仪器:")
    instruments = manager.list_instruments()
    for i, instrument in enumerate(instruments):
        print(f"{i + 1}. {instrument}")

    # 连接仪器
    signal_gen = None
    power_meter = None

    # 连接信号源
    sg_resource = input("请输入信号源的资源名称 (例如 TCPIP::192.168.1.100::INSTR): ")
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, 'signal_generator')
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"信号源ID: {signal_gen.get_idn()}")

    # 连接功率计
    pm_resource = input("请输入功率计的资源名称 (例如 USB::0x0AAD::0x015F::101930::INSTR): ")
    if pm_resource:
        pm_instrument = manager.connect_instrument(pm_resource, 'power_meter')
        if pm_instrument:
            power_meter = PowerMeter(pm_instrument)
            print(f"功率计ID: {power_meter.get_idn()}")

    # 确保仪器连接成功
    if not signal_gen or not power_meter:
        print("仪器连接失败，无法继续")
        return

    # 执行功率计归零
    try:
        print("正在执行功率计归零...")
        power_meter.zero()  # 归零会等待完成
        print("功率计归零完成")
    except Exception:
        print("归零失败，终止测试")
        manager.disconnect_all()
        return

    # 使用配置文件中的设置
    selected_project_name = project_name
    selected_configs = test_configs

    # 运行测试
    test_procedure = TestProcedure(manager)

    # 使用TestProcedure的prepare_test方法进行测试前准备
    test_procedure.prepare_test(signal_gen, power_meter)

    print(f"\n开始测试项目: {selected_project_name}")
    print(f"测试点数: {len(selected_configs)}")
    print("测试模式: RF开关在测试阶段保持开启，测试结束后关闭")

    # 显示时间参数配置
    if selected_configs and len(selected_configs) > 0:
        # 使用第一个测试点的配置作为参考
        sample_config = selected_configs[0]
        settling_time = sample_config.get('settling_time', 0.5)
        pm_settling_time = sample_config.get('pm_settling_time', 0.5)
        post_close_wait = sample_config.get('post_close_wait', 0.1)
        measurement_times = sample_config.get('measurement_times', 5)
        attenuator_enabled = sample_config.get('attenuator_enabled', False)
        attenuator_value = sample_config.get('attenuator_value', 0)
        attenuator_freq_dependent = sample_config.get('attenuator_freq_dependent', False)

        print(f"时间参数配置:")
        print(f"  - 信号源稳定时间: {settling_time}秒")
        print(f"  - 功率计频率切换稳定时间: {pm_settling_time}秒")
        print(f"  - 信号源关闭后等待时间: {post_close_wait}秒")
        print(f"  - 功率计测量次数: {measurement_times}次")
        
        print(f"\n衰减器配置:")
        if attenuator_enabled:
            if attenuator_freq_dependent:
                print(f"  - 使用频率相关衰减器")
                print(f"  - 衰减值根据频率自动调整")
            else:
                print(f"  - 使用固定衰减器，衰减值: {attenuator_value}dB")
        else:
            print(f"  - 未使用衰减器")
        
        # 显示功率设置
        power_settings = sorted(list(set(config['power'] for config in selected_configs)))
        print(f"\n功率设置: {power_settings} dBm")
        print(f"测试顺序: 先完成一个功率级别的所有频率点，再进行下一个功率级别")
    else:
        print("时间参数: 使用默认值（信号源稳定时间2.0秒，功率计频率切换稳定时间0.5秒）")

    print("\n开始测试...")

    try:
        current_power = None
        for i, test_config in enumerate(selected_configs):
            is_last_point = (i == len(selected_configs) - 1)

            # 检查是否进入新的功率级别
            if test_config['power'] != current_power:
                current_power = test_config['power']
                print(f"\n{'=' * 60}")
                print(f"开始功率级别: {current_power} dBm")
                print(f"{'=' * 60}")

            # 最后一个点测量后关闭输出，其他点保持输出
            keep_output = not is_last_point

            print(f"\n--- 测试点 {i+1}/{len(selected_configs)}: {test_config['test_name']} ---")

            # 显示当前点的频率和功率
            freq_mhz = test_config['frequency'] / 1e6
            print(f"频率: {freq_mhz:.0f}MHz, 功率: {test_config['power']}dBm")

            # 运行测试
            test_procedure.run_test(signal_gen, power_meter, test_config, keep_output=keep_output)

            # 如果不是最后一个点，输出保持开启，准备切换到下一个频点
            if not is_last_point:
                print(f"保持输出状态，准备切换到下一个频点...")
                # 这里可以添加一个短暂的延时，确保仪器准备好
                time.sleep(0.1)

        # 所有测试点完成后，确保信号源输出关闭
        print("\n所有测试点完成，关闭信号源输出...")
        signal_gen.enable_output(False)

    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        # 确保出错时也关闭信号源输出
        try:
            signal_gen.enable_output(False)
        except:
            pass
        raise  # 重新抛出异常

    # 保存测试结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    filename = f"功率扫描_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    test_procedure.save_results(filepath, test_configs=selected_configs)
    print(f"测试结果已保存到: {filepath}")

    # 断开所有仪器连接USB0::0x0AAD::0x015F::101930::0::INSTR
    manager.disconnect_all()


if __name__ == "__main__":
    main()