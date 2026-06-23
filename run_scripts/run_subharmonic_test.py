#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
鍒嗚皭娉㈡祴璇曚富绋嬪簭
杩愯淇″彿婧愮殑鍒嗚皭娉㈡祴璇?
"""

import sys
import os
from datetime import datetime

# 娣诲姞椤圭洰鐩綍鍒癙ython璺緞
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)  # 椤圭洰鏍圭洰褰?
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
    """杩炴帴浠櫒"""
    manager = InstrumentManager()

    print("鍙敤浠櫒:")
    instruments = manager.list_instruments()
    for i, instrument in enumerate(instruments):
        print(f"{i + 1}. {instrument}")

    signal_gen = None
    spectrum_analyzer = None

    # 杩炴帴淇″彿婧?
    sg_resource = input("\n璇疯緭鍏ヤ俊鍙锋簮鐨勮祫婧愬悕绉?(鎸塃nter璺宠繃): ").strip()
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, 'signal_generator')
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"淇″彿婧怚D: {signal_gen.get_idn()}")
        else:
            print("淇″彿婧愯繛鎺ュけ璐?)
    else:
        print("鏈繛鎺ヤ俊鍙锋簮")

    # 杩炴帴棰戣氨浠?
    sa_resource = input("\n璇疯緭鍏ラ璋变华鐨勮祫婧愬悕绉?(鎸塃nter璺宠繃): ").strip()
    if sa_resource:
        sa_instrument = manager.connect_instrument(sa_resource, 'spectrum_analyzer')
        if sa_instrument:
            spectrum_analyzer = SpectrumAnalyzer(sa_instrument)
            print(f"棰戣氨浠狪D: {spectrum_analyzer.get_idn()}")
        else:
            print("棰戣氨浠繛鎺ュけ璐?)
    else:
        print("鏈繛鎺ラ璋变华")

    return manager, signal_gen, spectrum_analyzer


def configure_test():
    """閰嶇疆娴嬭瘯鍙傛暟"""
    print("\n" + "=" * 60)
    print("鍒嗚皭娉㈡祴璇曢厤缃?)
    print("=" * 60)

    # 鏄剧ず榛樿閰嶇疆
    print(get_test_config_summary())

    # 璇㈤棶鏄惁淇敼閰嶇疆
    modify = input("\n鏄惁淇敼閰嶇疆? (y/N): ").strip().lower()
    
    # 杩欓噷鍙互娣诲姞閰嶇疆淇敼閫昏緫
    # 鏆傛椂浣跨敤榛樿閰嶇疆
    if modify == 'y':
        print("閰嶇疆淇敼鍔熻兘鏆傛湭瀹炵幇锛屼娇鐢ㄩ粯璁ら厤缃?)
    
    return {
        'frequency_sweep_config': FREQUENCY_SWEEP_CONFIG,
        'spectrum_analyzer_config': SPECTRUM_ANALYZER_CONFIG,
        'subharmonic_measurement_config': SUBHARMONIC_MEASUREMENT_CONFIG,
        'output_config': OUTPUT_CONFIG
    }


def run_subharmonic_test():
    """杩愯鍒嗚皭娉㈡祴璇?""
    print("\n" + "=" * 60)
    print("鍒嗚皭娉㈡祴璇?)
    print("=" * 60)

    # 1. 杩炴帴浠櫒
    manager, signal_gen, spectrum_analyzer = connect_instruments()

    if not signal_gen or not spectrum_analyzer:
        print("\n閿欒: 淇″彿婧愬拰棰戣氨浠兘蹇呴』杩炴帴")
        manager.disconnect_all()
        return

    # 2. 閰嶇疆娴嬭瘯
    test_config = configure_test()

    # 3. 鐢熸垚娴嬭瘯鐐?
    test_points = generate_frequency_points()
    print(f"\n鐢熸垚 {len(test_points)} 涓祴璇曠偣")

    # 4. 鍒濆鍖栨祴璇曟祦绋?
    test_procedure = SubharmonicTestProcedure(manager)
    output_dir = os.path.join(parent_dir, "output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{PROJECT_NAME}_{timestamp}.csv")
    test_procedure.start_csv_stream(csv_path)

    # 5. 杩愯娴嬭瘯
    print("\n" + "=" * 60)
    print("寮€濮嬫祴璇?)
    print("=" * 60)

    # 杩愯娴嬭瘯锛屾渶鍚庝竴涓祴璇曠偣涔嬪墠淇濇寔杈撳嚭寮€鍚?
    for i, test_point in enumerate(test_points):
        # 鏈€鍚庝竴涓祴璇曠偣涓嶄繚鎸佽緭鍑猴紝鍏朵粬娴嬭瘯鐐逛繚鎸佽緭鍑?
        keep_output = (i < len(test_points) - 1)
        test_procedure.run_subharmonic_test(
            signal_gen,
            spectrum_analyzer,
            test_point,
            test_config['spectrum_analyzer_config'],
            test_config['subharmonic_measurement_config'],
            keep_output=keep_output
        )

    # 6. 淇濆瓨娴嬭瘯缁撴灉
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    output_format = test_config['output_config'].get('output_format', 'excel')
    
    if output_format == 'excel':
        filename = f"subharmonic_test_results_{timestamp}.xlsx"
    else:
        filename = f"subharmonic_test_results_{timestamp}.csv"
    
    filepath = os.path.join(output_dir, filename)
    test_procedure.finish_xlsx(filepath)

    # 7. 鎵撳嵃娴嬭瘯鎽樿
    test_procedure.print_summary()

    # 8. 鏂紑浠櫒杩炴帴
    print("\n" + "=" * 60)
    print("鏂紑浠櫒杩炴帴")
    print("=" * 60)
    manager.disconnect_all()

    print("\n娴嬭瘯瀹屾垚锛?)


if __name__ == "__main__":
    run_subharmonic_test()
