import sys
import os
import time

# 娣诲姞椤圭洰鐩綍鍒癙ython璺緞
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)  # 椤圭洰鏍圭洰褰?
sys.path.append(os.path.join(parent_dir, 'instruments'))
sys.path.append(os.path.join(parent_dir, 'procedures'))
sys.path.append(os.path.join(parent_dir, 'configs'))

from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from power_meter import PowerMeter
from max_power_procedure import MaxPowerProcedure
from datetime import datetime
from max_power_config import project_name, test_configs


# 涓诲嚱鏁?
def main():
    """涓诲嚱鏁?""
    # 鍒濆鍖栦华鍣ㄧ鐞嗗櫒
    manager = InstrumentManager()

    # 鍒楀嚭鍙敤浠櫒
    print("鍙敤浠櫒:")
    instruments = manager.list_instruments()
    for i, instrument in enumerate(instruments):
        print(f"{i + 1}. {instrument}")

    # 杩炴帴浠櫒
    signal_gen = None
    power_meter = None

    # 杩炴帴淇″彿婧?
    sg_resource = input("璇疯緭鍏ヤ俊鍙锋簮鐨勮祫婧愬悕绉?(渚嬪 TCPIP::192.168.1.100::INSTR): ")
    if sg_resource:
        sg_instrument = manager.connect_instrument(sg_resource, 'signal_generator')
        if sg_instrument:
            signal_gen = SignalGenerator(sg_instrument)
            print(f"淇″彿婧怚D: {signal_gen.get_idn()}")

    # 杩炴帴鍔熺巼璁?
    pm_resource = input("璇疯緭鍏ュ姛鐜囪鐨勮祫婧愬悕绉?(渚嬪 USB::0x0AAD::0x015F::101930::INSTR): ")
    if pm_resource:
        pm_instrument = manager.connect_instrument(pm_resource, 'power_meter')
        if pm_instrument:
            power_meter = PowerMeter(pm_instrument)
            print(f"鍔熺巼璁D: {power_meter.get_idn()}")

    # 纭繚浠櫒杩炴帴鎴愬姛
    if not signal_gen or not power_meter:
        print("浠櫒杩炴帴澶辫触锛屾棤娉曠户缁?)
        return

    # 鎵ц鍔熺巼璁″綊闆?
    try:
        power_meter.zero()  # 褰掗浂浼氱瓑寰呭畬鎴?
    except Exception:
        print("褰掗浂澶辫触锛岀粓姝㈡祴璇?)
        manager.disconnect_all()
        return

    # 绛夊緟鐢ㄦ埛纭閲嶆柊杩炴帴鍔熺巼璁?
    input("\n璇烽噸鏂拌繛鎺ュ姛鐜囪杈撳叆淇″彿锛岀劧鍚庢寜 Enter 閿户缁?..")

    # 浣跨敤榛樿娴嬭瘯閰嶇疆
    selected_configs = test_configs
    selected_project_name = project_name

    # 杩愯娴嬭瘯
    test_procedure = MaxPowerProcedure(manager)
    output_dir = os.path.join(parent_dir, "output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"{project_name}_{timestamp}.csv")
    test_procedure.start_csv_stream(csv_path)

    print(f"\n寮€濮嬫祴璇曢」鐩? {selected_project_name}")
    print(f"娴嬭瘯鐐规暟: {len(selected_configs)}")
    print("娴嬭瘯妯″紡: 鍦ㄦ瘡涓鐐硅繘琛屽姛鐜囨壂鎻忥紝瀵绘壘鏈€澶ц緭鍑哄姛鐜?)

    # 鏄剧ず娴嬭瘯閰嶇疆
    if selected_configs and len(selected_configs) > 0:
        # 浣跨敤绗竴涓祴璇曠偣鐨勯厤缃綔涓哄弬鑰?
        sample_config = selected_configs[0]
        start_power = sample_config.get('start_power', -20)
        power_step = sample_config.get('power_step', 1.0)
        max_set_power = sample_config.get('max_set_power', 20)
        max_measured_power = sample_config.get('max_measured_power', 20)
        attenuator_value = sample_config.get('attenuator_value', 0.0)
        use_attenuator = sample_config.get('use_attenuator', False)
        measurement_times = sample_config.get('measurement_times', 5)

        print(f"鍔熺巼鎵弿鍙傛暟:")
        print(f"  - 璧峰鍔熺巼: {start_power} dBm")
        print(f"  - 鍔熺巼姝ヨ繘: {power_step} dB")
        print(f"  - 鏈€澶ц瀹氬姛鐜囬檺鍒? {max_set_power} dBm")
        print(f"  - 鏈€澶ф祴閲忓姛鐜囬檺鍒? {max_measured_power} dBm")
        if use_attenuator:
            print(f"  - 琛板噺鍣ㄥ€? {attenuator_value} dB")
        print(f"  - 鍔熺巼璁℃祴閲忔鏁? {measurement_times}娆?)

    print("\n寮€濮嬫祴璇?..")

    try:
        for i, test_config in enumerate(selected_configs):
            is_last_point = (i == len(selected_configs) - 1)

            # 鏈€鍚庝竴涓偣娴嬮噺鍚庡叧闂緭鍑猴紝鍏朵粬鐐逛繚鎸佽緭鍑?
            keep_output = not is_last_point

            print(f"\n{'=' * 60}")
            print(f"娴嬭瘯鐐?{i+1}/{len(selected_configs)}: {test_config['test_name']}")
            print(f"{'=' * 60}")

            # 杩愯娴嬭瘯
            test_procedure.run_test(signal_gen, power_meter, test_config, keep_output=keep_output)

            # 濡傛灉涓嶆槸鏈€鍚庝竴涓偣锛岃緭鍑轰繚鎸佸紑鍚紝鍑嗗鍒囨崲鍒颁笅涓€涓鐐?
            if not is_last_point:
                print(f"淇濇寔杈撳嚭鐘舵€侊紝鍑嗗鍒囨崲鍒颁笅涓€涓鐐?..")
                # 杩欓噷鍙互娣诲姞涓€涓煭鏆傜殑寤舵椂锛岀‘淇濅华鍣ㄥ噯澶囧ソ
                time.sleep(0.1)

        # 鎵€鏈夋祴璇曠偣瀹屾垚鍚庯紝纭繚淇″彿婧愯緭鍑哄叧闂?
        print("\n鎵€鏈夋祴璇曠偣瀹屾垚锛屽叧闂俊鍙锋簮杈撳嚭...")
        signal_gen.enable_output(False)

    except Exception as e:
        print(f"娴嬭瘯杩囩▼涓彂鐢熼敊璇? {e}")
        # 纭繚鍑洪敊鏃朵篃鍏抽棴淇″彿婧愯緭鍑?
        try:
            signal_gen.enable_output(False)
        except:
            pass
        raise  # 閲嶆柊鎶涘嚭寮傚父

    # 淇濆瓨娴嬭瘯缁撴灉
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(parent_dir, 'output')
    filename = f"鏈€澶у姛鐜囨祴璇昣{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    test_procedure.finish_xlsx(filepath)

    # 鏂紑鎵€鏈変华鍣ㄨ繛鎺?
    manager.disconnect_all()


if __name__ == "__main__":
    main()
