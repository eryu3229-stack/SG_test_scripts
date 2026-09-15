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
from spurious_procedure import SpuriousProcedure
from spurious_config import (
    carrier_power_dbm,
    get_config,
    get_carrier_frequency_list,
)

# 输出文件统一命名（只出 CSV）：<OUTPUT_TAG>_<时间戳>.csv
OUTPUT_TAG = "spurious"


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

    carrier_frequency_list = get_carrier_frequency_list()

    if not carrier_frequency_list:
        print("载波频率列表为空，请检查 spurious_config.py")
        manager.disconnect_all()
        return

    procedure = SpuriousProcedure(manager)
    output_dir = os.path.join(parent_dir, "output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{OUTPUT_TAG}_{timestamp}.csv")
    procedure.start_csv_stream(csv_path)

    print(f"\n开始杂散测量")
    print(f"载波频率点数: {len(carrier_frequency_list)}")

    config = get_config()

    for i, carrier_frequency in enumerate(carrier_frequency_list):
        keep_output = i < len(carrier_frequency_list) - 1
        print(f"\n--- 载波 {carrier_frequency / 1e6:.3f} MHz, {carrier_power_dbm} dBm ---")
        procedure.run_spurious_test(
            signal_gen,
            spectrum_analyzer,
            carrier_frequency,
            carrier_power_dbm,
            config,
            keep_output=keep_output,
        )

    procedure.sort_results()
    procedure.finish_csv()
    manager.disconnect_all()


if __name__ == "__main__":
    main()
