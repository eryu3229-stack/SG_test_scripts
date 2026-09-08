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
from small_signal_config import (
    frequency_list,
    power_list_dbm,
    get_config,
)

# 输出文件统一命名：结果 <OUTPUT_TAG>_results_<时间戳>.xlsx，中间流式 CSV <OUTPUT_TAG>_stream_<时间戳>.csv
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
    csv_path = os.path.join(output_dir, f"{OUTPUT_TAG}_stream_{timestamp}.csv")
    procedure.start_csv_stream(csv_path)

    print(f"\n开始小信号测量")
    print(f"频率点数: {len(frequency_list)}")
    print(f"功率点数: {len(power_list_dbm)}")

    if not frequency_list or not power_list_dbm:
        print("频率列表或功率列表为空，请检查 small_signal_config.py")
        manager.disconnect_all()
        return

    for i, frequency in enumerate(frequency_list):
        keep_output = i < len(frequency_list) - 1
        print(f"\n--- 频率 {frequency / 1e6:.3f} MHz ---")
        procedure.run_small_signal_test(
            signal_gen,
            spectrum_analyzer,
            frequency,
            power_list_dbm,
            get_config(),
            keep_output=keep_output
        )

    # 流式写 CSV -> 最后转 Excel 并删除中间 CSV；若缺少 pandas/openpyxl 则保留 CSV
    xlsx_path = os.path.join(output_dir, f"{OUTPUT_TAG}_results_{timestamp}.xlsx")
    if procedure.finish_xlsx(xlsx_path):
        print(f"Excel 已保存: {xlsx_path}")
    else:
        print(f"已保留 CSV 结果: {csv_path}")

    manager.disconnect_all()


if __name__ == "__main__":
    main()
