# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, "instruments"))
sys.path.append(os.path.join(parent_dir, "procedures"))
sys.path.append(os.path.join(parent_dir, "configs"))
sys.path.append(os.path.join(parent_dir, "utils"))

from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from spectrum_analyzer import SpectrumAnalyzer
from small_signal_procedure import SmallSignalProcedure
from utils.formatting import format_frequency
from small_signal_config import (
    generate_frequency_list,
    power_list_dbm,
    get_config,
)

# 输出文件统一命名（只出 CSV）：<OUTPUT_TAG>_<时间戳>.csv
OUTPUT_TAG = "small_signal"


def connect_instruments():
    manager = InstrumentManager()
    print("可用仪器:")
    for i, instrument in enumerate(manager.list_instruments()):
        print(f"{i + 1}. {instrument}")

    signal_gen = None
    spectrum_analyzer = None

    sg_resource = input("\n请输入信号源的资源名称(按Enter跳过): ").strip()
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, "signal_generator")
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"信号源ID: {signal_gen.get_idn()}")

    sa_resource = input("\n请输入频谱仪的资源名称(按Enter跳过): ").strip()
    if sa_resource:
        sa_instrument = manager.connect_instrument(sa_resource, "spectrum_analyzer")
        if sa_instrument:
            spectrum_analyzer = SpectrumAnalyzer(sa_instrument)
            print(f"频谱仪ID: {spectrum_analyzer.get_idn()}")

    return manager, signal_gen, spectrum_analyzer


def main():
    manager, signal_gen, spectrum_analyzer = connect_instruments()

    if not signal_gen or not spectrum_analyzer:
        print("\n错误: 信号源和频谱仪都必须连接")
        manager.disconnect_all()
        return

    procedure = SmallSignalProcedure(manager)
    output_dir = os.path.join(parent_dir, "output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{OUTPUT_TAG}_{timestamp}.csv")
    procedure.start_csv_stream(csv_path)

    frequencies = generate_frequency_list()

    print(f"\n开始小信号测量")
    print(f"频率点数: {len(frequencies)}")
    print(f"功率点数: {len(power_list_dbm)}")

    if not frequencies or not power_list_dbm:
        print("频率列表或功率列表为空，请检查 small_signal_config.py "
              "（频率为 step 模式时看 frequency_config，list 模式看 frequency_list）")
        manager.disconnect_all()
        return

    plan = f"{format_frequency(frequencies[0])} ~ {format_frequency(frequencies[-1])}"
    if len(frequencies) > 1:
        plan += f"，首段间隔 {format_frequency(frequencies[1] - frequencies[0])}"
    print(f"频率范围: {plan}")
    if len(frequencies) > 1000:
        print(f"警告: 频率点数 {len(frequencies)} 过多，请确认步进设置是否过小")

    for i, frequency in enumerate(frequencies):
        keep_output = i < len(frequencies) - 1
        print(f"\n--- 频率 {format_frequency(frequency)} ---")
        procedure.run_small_signal_test(
            signal_gen,
            spectrum_analyzer,
            frequency,
            power_list_dbm,
            get_config(),
            keep_output=keep_output
        )

    # CSV 流已在测试过程中逐点落盘，此处仅关闭文件
    procedure.finish_csv()

    manager.disconnect_all()


if __name__ == "__main__":
    main()
