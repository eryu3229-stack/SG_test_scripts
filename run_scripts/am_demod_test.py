# -*- coding: utf-8 -*-
"""AM（幅度调制）测量入口脚本。

输出：`output/am_demod_<时间戳>.csv`（流式逐行落盘，中断也保留已测数据）
展开顺序：频率（外）→ 调制深度（中）→ 调制速率（内）
"""

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
from am_demod_procedure import AmDemodProcedure
from utils.formatting import format_frequency
from am_demod_config import (
    am_depth_list_pct,
    carrier_power_dbm,
    generate_frequency_list,
    get_config,
    mod_rate_list_hz,
)

# 输出文件统一命名（只出 CSV）：<OUTPUT_TAG>_<时间戳>.csv
OUTPUT_TAG = "am_demod"


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

    frequencies = generate_frequency_list()
    if not frequencies or not am_depth_list_pct or not mod_rate_list_hz:
        print("频率列表、调制深度列表或速率列表为空，请检查 am_demod_config.py")
        manager.disconnect_all()
        return

    procedure = AmDemodProcedure(manager)
    output_dir = os.path.join(parent_dir, "output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{OUTPUT_TAG}_{timestamp}.csv")
    procedure.start_csv_stream(csv_path)

    total_rows = len(frequencies) * len(am_depth_list_pct) * len(mod_rate_list_hz)
    plan = f"{format_frequency(frequencies[0])} ~ {format_frequency(frequencies[-1])}"
    print(f"\n开始 AM（幅度调制）测量")
    print(f"载波: {len(frequencies)} 点（{plan}），载波功率 {carrier_power_dbm} dBm")
    print(f"调制深度: {am_depth_list_pct} %")
    print(f"调制速率: {mod_rate_list_hz} Hz")
    print(f"预计输出行数: {total_rows}")
    print("注意: AM 与 FM/PM 无硬件互斥，流程不下发任何 FM/PM 指令"
          "（残留调制只作回读告警，不主动关闭）")

    for i, carrier_frequency in enumerate(frequencies):
        keep_output = i < len(frequencies) - 1
        procedure.run_demod_test(
            signal_gen,
            spectrum_analyzer,
            carrier_frequency,
            carrier_power_dbm,
            am_depth_list_pct,
            mod_rate_list_hz,
            get_config(),
            keep_output=keep_output,
        )

    procedure.sort_results()
    procedure.finish_csv()
    manager.disconnect_all()


if __name__ == "__main__":
    main()
