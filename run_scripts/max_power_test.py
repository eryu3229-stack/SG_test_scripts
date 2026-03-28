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
sys.path.append(os.path.join(parent_dir, 'utils'))

from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from power_meter import PowerMeter
from max_power_procedure import MaxPowerProcedure
from project_manager import ProjectManager
from datetime import datetime
from max_power_config import project_name, test_configs


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
        power_meter.zero()  # 归零会等待完成
    except Exception:
        print("归零失败，终止测试")
        manager.disconnect_all()
        return

    # 初始化项目管理器
    project_manager = ProjectManager()

    # 显示已有项目
    project_manager.list_projects()

    # 选择使用已有项目还是创建新项目
    print("\n请选择:")
    print("1. 使用已有项目")
    print("2. 创建新项目")

    choice = input("请输入选择 (1或2): ")

    selected_configs = None
    selected_project_name = None

    if choice == "1" and project_manager.projects:
        # 使用已有项目
        project_index = input(f"请输入项目编号 (1-{len(project_manager.projects)}): ")
        try:
            project_index = int(project_index)
            project = project_manager.get_project(project_index)
            if project:
                selected_configs = project['test_configs']
                selected_project_name = project['project_name']
                print(f"已选择项目: {selected_project_name}")
            else:
                print("无效的项目编号，将创建新项目")
                choice = "2"  # 回退到创建新项目
        except ValueError:
            print("无效的输入，将创建新项目")
            choice = "2"

    if choice == "2" or not selected_configs:
        # 创建新项目
        user_project_name = input("请输入测试项目名称 (按Enter使用默认名称): ")
        if user_project_name:
            selected_project_name = user_project_name
        else:
            selected_project_name = project_name

        selected_configs = test_configs

        # 保存新项目
        project_manager.add_project(selected_project_name, selected_configs)

    # 运行测试
    test_procedure = MaxPowerProcedure(manager)

    print(f"\n开始测试项目: {selected_project_name}")
    print(f"测试点数: {len(selected_configs)}")
    print("测试模式: 在每个频点进行功率扫描，寻找最大输出功率")

    # 显示测试配置
    if selected_configs and len(selected_configs) > 0:
        # 使用第一个测试点的配置作为参考
        sample_config = selected_configs[0]
        start_power = sample_config.get('start_power', -20)
        power_step = sample_config.get('power_step', 1.0)
        max_set_power = sample_config.get('max_set_power', 20)
        max_measured_power = sample_config.get('max_measured_power', 20)
        attenuator_value = sample_config.get('attenuator_value', 0.0)
        use_attenuator = sample_config.get('use_attenuator', False)
        measurement_times = sample_config.get('measurement_times', 5)

        print(f"功率扫描参数:")
        print(f"  - 起始功率: {start_power} dBm")
        print(f"  - 功率步进: {power_step} dB")
        print(f"  - 最大设定功率限制: {max_set_power} dBm")
        print(f"  - 最大测量功率限制: {max_measured_power} dBm")
        if use_attenuator:
            print(f"  - 衰减器值: {attenuator_value} dB")
        print(f"  - 功率计测量次数: {measurement_times}次")

    print("\n开始测试...")

    try:
        for i, test_config in enumerate(selected_configs):
            is_last_point = (i == len(selected_configs) - 1)

            # 最后一个点测量后关闭输出，其他点保持输出
            keep_output = not is_last_point

            print(f"\n{'=' * 60}")
            print(f"测试点 {i+1}/{len(selected_configs)}: {test_config['test_name']}")
            print(f"{'=' * 60}")

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
    filename = f"最大功率测试_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    test_procedure.save_results(filepath)
    print(f"测试结果已保存到: {filepath}")

    # 断开所有仪器连接
    manager.disconnect_all()


if __name__ == "__main__":
    main()