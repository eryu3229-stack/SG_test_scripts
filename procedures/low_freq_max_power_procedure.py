import time
from datetime import datetime
from base_test_procedure import format_frequency
from power_sweep_base import PowerSweepBaseProcedure


class LowFreqMaxPowerProcedure(PowerSweepBaseProcedure):
    """低频段最大功率测试流程类（用频谱仪读数，带 sa_* 采集条件列）

    字段说明：summary 的 `actual_power_dbm` = `measured_power_dbm` + `ext_att_db`
    （折算到 DUT 端）。**detail 表不插该列**（2026-09-20 用户明确要求）。
    """

    TEST_TYPE = "low_freq_max_power"

    SA_COLUMNS = [
        "sa_ref_level_dbm", "sa_input_att_db", "sa_att_mode",
        "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz",
    ]

    SUMMARY_FIELDNAMES = (
        ["run_id", "test_type", "carrier_hz", "set_power_dbm",
         "actual_power_dbm", "measured_power_dbm", "delta_db", "delta_ref"]
        + SA_COLUMNS
        + ["ext_att_db", "saturated", "steps", "status", "note", "timestamp"]
    )

    DETAIL_FIELDNAMES = (
        ["run_id", "test_type", "carrier_hz", "set_power_dbm",
         "measured_power_dbm", "delta_db", "delta_ref"]
        + SA_COLUMNS
        + ["ext_att_db", "step_index", "status", "note", "timestamp"]
    )

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)

    def run_test(self, signal_generator, spectrum_analyzer, test_config, keep_output=False):
        """运行低频段最大功率测试"""
        frequency = test_config['frequency']
        start_power = test_config['start_power']
        stop_power = test_config.get('stop_power', test_config.get('max_set_power', start_power))
        power_step = test_config['power_step']
        max_set_power = test_config['max_set_power']
        max_measured_power = test_config['max_measured_power']

        if stop_power > max_set_power:
            print(f"警告: stop_power ({stop_power} dBm) > max_set_power ({max_set_power} dBm)，"
                  f"将 stop_power 限制为 {max_set_power} dBm")
            stop_power = max_set_power
        power_tolerance = test_config['power_tolerance']
        max_power_drop = test_config['max_power_drop']
        attenuator_value = test_config['attenuator_value']
        use_attenuator = test_config['use_attenuator']
        settling_time = test_config['settling_time']
        sa_settling_time = test_config['sa_settling_time']
        measurement_times = test_config['measurement_times']
        sa_config = test_config['spectrum_analyzer_config']

        print(f"\n{'=' * 60}")
        print(f"开始低频段最大功率测试: {test_config['test_name']}")
        print(f"频率: {format_frequency(frequency)}")
        print(f"起始功率: {start_power} dBm, 终止功率: {stop_power} dBm, 步进: {power_step} dB")
        print(f"信号源硬限制: {max_set_power} dBm")
        print(f"频谱仪最大读数限制: {max_measured_power} dBm")
        if use_attenuator:
            print(f"衰减器值: {attenuator_value} dB")
        print(f"频谱仪输入耦合: {sa_config['input_coupling']}")
        print(f"{'=' * 60}")

        signal_generator.set_frequency(frequency)
        
        spectrum_analyzer.set_center_frequency(frequency)
        spectrum_analyzer.set_span(sa_config['span'])
        spectrum_analyzer.set_rbw(sa_config['rbw'])
        spectrum_analyzer.set_vbw(sa_config['vbw'])
        spectrum_analyzer.set_reference_level(sa_config['reference_level'])
        spectrum_analyzer.set_attenuation(sa_config['attenuation'])
        spectrum_analyzer.set_input_coupling(sa_config['input_coupling'])
        print(f"设置频谱仪输入耦合为: {sa_config['input_coupling']}")

        # 频谱仪采集条件：写入每行的 sa_* 列
        self.sa_context = {
            "sa_ref_level_dbm": sa_config['reference_level'],
            "sa_input_att_db": sa_config['attenuation'],
            "sa_att_mode": "manual",
            "sa_span_hz": sa_config['span'],
            "sa_rbw_hz": sa_config['rbw'],
            "sa_vbw_hz": sa_config['vbw'],
        }

        # 外接衰减器：人为告知的物理事实，从不下发仪器，仅用于折算读数
        ext_att_db = attenuator_value if use_attenuator else 0.0
        
        current_power = start_power
        signal_generator.set_power(current_power)
        signal_generator.enable_output(True)
        print(f"启用信号源输出，起始功率: {current_power} dBm")
        
        print(f"等待信号源稳定 {settling_time}秒...")
        time.sleep(settling_time)
        print(f"等待频谱仪稳定 {sa_settling_time}秒...")
        time.sleep(sa_settling_time)
        
        max_achieved_power = None
        max_achieved_measured = None
        max_set_power_at_peak = None
        prev_measured_power = None
        prev_actual_power = None
        saturation_detected = False
        overload_detected = False
        step_count = 0
        stop_reason = "正常完成"
        
        while True:
            step_count += 1
            print(f"\n--- 功率步进 {step_count}: 设定功率 = {current_power:.1f} dBm ---")
            
            signal_generator.set_power(current_power)
            time.sleep(settling_time)
            
            measured_power = None
            measurements = []
            for i in range(measurement_times):
                power = spectrum_analyzer.measure_power()
                if power is not None:
                    measurements.append(power)
                time.sleep(0.1)
            
            if measurements:
                measured_power = sum(measurements) / len(measurements)
                print(f"测量功率 (平均{len(measurements)}次): {measured_power:.2f} dBm")
            else:
                print("警告: 频谱仪测量失败，跳过此点")
                self.add_power_sweep_point(
                    frequency, current_power, None, None, step_count,
                    'MEAS_FAIL', ext_att_db=ext_att_db,
                )
                measured_power = prev_measured_power if prev_measured_power is not None else -float('inf')
            
            if use_attenuator:
                actual_power = measured_power + attenuator_value
            else:
                actual_power = measured_power
            
            print(f"测量功率: {measured_power:.2f} dBm, 实际功率: {actual_power:.2f} dBm")
            
            stop_scan = False
            
            if current_power >= stop_power:
                stop_reason = f"达到扫描终止功率 ({stop_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            if current_power >= max_set_power:
                stop_reason = f"达到信号源硬限制 ({max_set_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            if measured_power >= max_measured_power:
                stop_reason = f"达到频谱仪最大读数 ({max_measured_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            if prev_actual_power is not None:
                power_increase = actual_power - prev_actual_power
                if power_increase < power_tolerance:
                    saturation_detected = True
                    stop_reason = f"检测到饱和 (实际功率增加仅{power_increase:.2f} dB < 容差 {power_tolerance} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            if prev_actual_power is not None:
                power_drop = prev_actual_power - actual_power
                if power_drop > max_power_drop:
                    overload_detected = True
                    stop_reason = f"检测到过载 (实际功率下降 {power_drop:.2f} dB > 最大允许 {max_power_drop} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            status = 'OK'
            if saturation_detected:
                status = 'SATURATED'
            elif overload_detected:
                status = 'OVERLOAD'
            elif stop_scan:
                status = 'LIMIT'

            self.add_power_sweep_point(
                frequency, current_power, measured_power, actual_power,
                step_count, status, ext_att_db=ext_att_db,
            )

            if max_achieved_power is None or actual_power > max_achieved_power:
                max_achieved_power = actual_power
                max_achieved_measured = measured_power
                max_set_power_at_peak = current_power
            
            prev_measured_power = measured_power
            prev_actual_power = actual_power
            
            if stop_scan:
                break
            
            current_power += power_step
        
        notes = stop_reason
        if saturation_detected:
            notes += " (饱和点)"
        if overload_detected:
            notes += " (过载点)"
        
        self.add_test_result(
            frequency=frequency,
            set_power_at_max=max_set_power_at_peak,
            max_measured_power=max_achieved_measured,
            max_actual_power=max_achieved_power,
            attenuation=attenuator_value if use_attenuator else 0.0,
            saturation_point=saturation_detected,
            steps=step_count,
            notes=notes
        )
        
        print(f"\n{'=' * 60}")
        print(f"测试完成: {test_config['test_name']}")
        print(f"最大实际功率: {max_achieved_power:.2f} dBm")
        print(f"最大测量功率: {max_achieved_measured:.2f} dBm")
        print(f"功率步进数: {step_count}")
        print(f"停止原因: {stop_reason}")
        print(f"{'=' * 60}")
        
        if not keep_output:
            signal_generator.enable_output(False)
            print("信号源输出已禁用")
            time.sleep(test_config['post_close_wait'])
        else:
            print("保持信号源输出状态")