# -*- coding: utf-8 -*-
"""AM 解调测试执行脚本。

连接信号源 + 频谱仪，按配置遍历载波频率、AM 深度、调制速率，
流式输出 CSV；测试结束后恢复未调制信号并复测载波，再按指定顺序关闭。
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
from am_demod_config import (
    carrier_power_dbm,
    get_config,
    get_carrier_frequency_list,
    output_tag,
)


def connect_instruments():
    """连接信号源与频谱仪，均必须成功。"""
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
        print("载波频率列表为空，请检查 am_demod_config.py")
        manager.disconnect_all()
        return

    config = get_config()
    am_depth_list_pct = config["am_depth_list_pct"]
    am_mod_rate_list_hz = config["am_mod_rate_list_hz"]

    output_dir = os.path.join(parent_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{output_tag}_{timestamp}.csv")

    procedure = AmDemodProcedure(manager)
    procedure.start_csv_stream(csv_path)

    print(f"\n开始 AM 解调测量")
    print(f"载波频率点数: {len(carrier_frequency_list)}")
    print(f"AM 深度点数: {len(am_depth_list_pct)}")
    print(f"调制速率点数: {len(am_mod_rate_list_hz)}")

    for carrier_frequency in carrier_frequency_list:
        print(f"\n--- 载波 {carrier_frequency / 1e6:.3f} MHz, {carrier_power_dbm} dBm ---")
        # 统一 keep_output=True，把最终清理留给本脚本，保证能先做未调制复测
        procedure.run_demod_test(
            signal_gen,
            spectrum_analyzer,
            carrier_frequency,
            carrier_power_dbm,
            am_depth_list_pct,
            am_mod_rate_list_hz,
            config,
            keep_output=True,
        )

    procedure.sort_results()

    # 在最后载波上恢复未调制信号并复测
    last_carrier = carrier_frequency_list[-1]
    procedure.verify_unmodulated_carrier(
        signal_gen, spectrum_analyzer, last_carrier, config)

    # 按指定顺序关闭：OUTP → AM1 → MOD:ALL
    procedure.cleanup_am(signal_gen)

    procedure.finish_csv()
    manager.disconnect_all()


if __name__ == "__main__":
    main()
