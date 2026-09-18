import time
from datetime import datetime
from base_test_procedure import BaseTestProcedure, format_frequency


class SmallSignalProcedure(BaseTestProcedure):
    """基于信号源功率步进和频谱仪 marker 追踪的小信号测量流程"""

    TEST_TYPE = "small_signal"

    FIELDNAMES = [
        # A 区：标识与数值
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
        # B 区：频谱仪采集条件
        "sa_ref_level_dbm", "sa_input_att_db", "sa_att_mode",
        "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz", "sa_noise_floor_dbm",
        # C 区：源专有
        "peak_frequency_hz", "sa_preamp_on",
        # 判定与时间
        "status", "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self._output_enabled = False
        self.run_id = ""

    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.run_id = self.derive_run_id(csv_path)
        self.csv_streamer = CsvStreamer(csv_path, self.FIELDNAMES)

    def _configure_spectrum_analyzer(self, spectrum_analyzer, center_frequency, span, rbw, vbw, reference_level, attenuation, preamp_on=False, preamp_band="FULL"):
        spectrum_analyzer.set_center_frequency(center_frequency)
        spectrum_analyzer.set_span(span)
        spectrum_analyzer.set_rbw(rbw)
        spectrum_analyzer.set_vbw(vbw)
        spectrum_analyzer.set_reference_level(reference_level)
        if attenuation is None:
            # None = 自动衰减（手册: POW:ATT:AUTO ON）
            if hasattr(spectrum_analyzer, "set_attenuation_auto"):
                spectrum_analyzer.set_attenuation_auto(True)
        else:
            spectrum_analyzer.set_attenuation(attenuation)
        if hasattr(spectrum_analyzer, "set_preamp"):
            spectrum_analyzer.set_preamp(preamp_on, preamp_band)
        # 设置后立刻核对错误队列（被固件拒绝的命令只能从这里看出来）
        if hasattr(spectrum_analyzer, "report_error_queue"):
            spectrum_analyzer.report_error_queue(tag="设置后")

    def _within_tolerance(self, peak_frequency, expected_frequency, tolerance):
        if peak_frequency is None:
            return False
        return abs(peak_frequency - expected_frequency) <= tolerance

    @staticmethod
    def _effective_tolerance(span, rbw, config):
        """有效频率容差：配置值被 ±1/4 SPAN 上限截断。

        容差若 ≥ 半 SPAN，窗口内任意噪声峰/杂散都会被判成"找到真峰"，
        于是 marker 被拖到非信号处，读数必然低于真实峰值。
        """
        tol_configured = config.get("freq_tolerance_hz", 10e3)
        tol_cap = max(span * 0.25, rbw * 2.0)
        return min(tol_configured, tol_cap)

    def _refresh_sweep(self, spectrum_analyzer):
        """按当前设置确定性采集一次 trace，保证后续 marker 读的是本次数据。

        仪器若停在单次态（上游流程用 `INIT:CONT OFF` 收尾），**改设置不会自动重扫**，
        trace 仍是旧数据：此时搜峰取到的是过期峰值，marker 甚至可能落在屏外
        → `CALC:MARK:Y?` 返回 9.91e+37 哨兵（被 `_sanitize_raw` 归为 None）。
        `acquire_once()`（`INIT:IMM` + `*OPC?`）保证这次采集确实已完成。
        """
        return self._acquire(spectrum_analyzer)

    @staticmethod
    def _estimate_noise_floor(trace):
        """用轨迹采样的中位数近似本地噪声底（dBm）。

        单音只占少量 bin，中位数几乎不受峰值影响。trace 为空返回 None。
        """
        if not trace:
            return None
        sorted_trace = sorted(trace)
        return sorted_trace[len(sorted_trace) // 2]

    def _read_noise_floor(self, spectrum_analyzer, trace_num=1):
        """读取当前 trace 并估计本地噪声底；读不到返回 None。

        调用前必须保证 trace 是**按当前设置刚采集的**（否则读到旧数据）。
        """
        if not hasattr(spectrum_analyzer, 'get_trace'):
            return None
        try:
            trace = spectrum_analyzer.get_trace(trace_num)
        except Exception as e:
            print(f"    读取噪声底失败: {e}")
            return None
        return self._estimate_noise_floor(trace)

    def _suggest_preamp(self, set_power, config):
        """低功率档开预放压低底噪；高功率档关闭防止前端过载"""
        if not config.get("preamp_enabled", False):
            return False
        return set_power <= config.get("preamp_threshold_dbm", -50)

    def _measure_peak(self, spectrum_analyzer, expected_frequency, span, rbw, vbw, reference_level, attenuation, config, average_count, preamp_on=False):
        self._configure_spectrum_analyzer(
            spectrum_analyzer,
            expected_frequency,
            span,
            rbw,
            vbw,
            reference_level,
            attenuation,
            preamp_on,
            config.get("preamp_band", "FULL")
        )
        time.sleep(config.get("sa_settling_time", 0.5))

        # 改完中心/SPAN/RBW/参考电平/衰减/预放后必须重新采集一次：
        # 否则搜峰在过期 trace 上取最大值，峰位与电平都不是当前设置下的真实值。
        self._refresh_sweep(spectrum_analyzer)

        # 清空历史错误，便于判断本次搜峰是否真的成功
        if hasattr(spectrum_analyzer, 'get_error_queue'):
            spectrum_analyzer.get_error_queue()

        spectrum_analyzer.peak_search()
        time.sleep(0.05)

        if hasattr(spectrum_analyzer, 'get_error_queue'):
            errs = spectrum_analyzer.get_error_queue()
            if errs:
                # 全部打印：被固件拒绝的命令（undefined header 等）只能从这里看出来
                print(f"    搜峰后仪器错误队列: {'；'.join(str(e) for e in errs)}")

        peak_frequency = None
        if hasattr(spectrum_analyzer, 'get_marker_frequency'):
            peak_frequency = spectrum_analyzer.get_marker_frequency(1)

        tolerance = self._effective_tolerance(span, rbw, config)
        found = self._within_tolerance(peak_frequency, expected_frequency, tolerance)

        if peak_frequency is None:
            print("    峰值搜索后 marker 频率无效（trace 无效/峰在屏外），回退到名义频率")
        elif not found:
            print(f"    峰位 {format_frequency(peak_frequency)} 偏离名义频率超过 "
                  f"{format_frequency(tolerance)}，按名义频率读数")

        # 始终把 marker 放到测量点：找到真峰用峰位，否则用名义频率
        # （外参锁定下以信号源名义频率为准，避免把杂散/噪声峰当成信号）
        measure_frequency = peak_frequency if found else expected_frequency
        spectrum_analyzer.set_marker_frequency(1, measure_frequency)
        time.sleep(0.05)

        measurements = []
        for _ in range(max(1, average_count)):
            # 每次读数前重新采集：单次态下 trace 是冻结的，不重扫等于 5 次读同一条
            self._refresh_sweep(spectrum_analyzer)
            power = self._read_marker(spectrum_analyzer, 1)
            if power is not None:
                measurements.append(power)
            time.sleep(0.1)

        if measurements:
            measured_power = sum(measurements) / len(measurements)
        else:
            measured_power = None

        # 本地噪声底（trace 中位数）：trace 刚采集完，此处有效
        noise_floor = self._read_noise_floor(spectrum_analyzer)
        return measured_power, measure_frequency, found, noise_floor

    def _suggest_span(self, set_power, config):
        tolerance = config.get("freq_tolerance_hz", 10e3)
        span = config.get("initial_span", 1e6)
        if set_power <= -80:
            span = max(tolerance, config.get("min_span", 5e3))
        elif set_power <= -60:
            span = max(tolerance * 2.0, config.get("min_span", 5e3))
        elif set_power <= -30:
            span = max(tolerance * 4.0, config.get("min_span", 5e3))
        return span

    def _suggest_rbw(self, set_power, config):
        rbw = config.get("initial_rbw", 1e3)
        if set_power <= -80:
            rbw = min(rbw, 30)
        elif set_power <= -60:
            rbw = min(rbw, 100)
        elif set_power <= -30:
            rbw = min(rbw, 300)
        return max(rbw, config.get("min_rbw", 10))

    def _suggest_vbw(self, set_power, config):
        rbw = self._suggest_rbw(set_power, config)
        return max(min(config.get("initial_vbw", 1e3), rbw * 3.0), config.get("min_vbw", 10))

    def _suggest_reference_level(self, set_power, config):
        margin = config.get("reference_level_margin_db", 10)
        return min(
            config.get("max_reference_level", 20),
            max(set_power + margin, config.get("min_reference_level", -80))
        )

    def _suggest_attenuation(self, set_power, config):
        """返回衰减值；自动衰减模式返回 None（仪器按参考电平自动耦合）"""
        if config.get("attenuation_auto", False):
            return None
        if set_power >= config.get("high_power_threshold_dbm", -20):
            return config.get("attenuation_for_high_power", 10)
        return config.get("attenuation_for_low_power", 0)

    def run_small_signal_test(self, signal_generator, spectrum_analyzer, frequency, power_list, config, keep_output=False):
        if not power_list:
            print("未配置功率列表，跳过该频率")
            return

        sorted_power_list = sorted(power_list, reverse=True)
        if not self._output_enabled:
            signal_generator.set_frequency(frequency)
            time.sleep(config.get("frequency_settling_time", 1.0))
            signal_generator.set_power(sorted_power_list[0])
            signal_generator.enable_output(True)
            self._output_enabled = True
        else:
            signal_generator.set_frequency(frequency)
            time.sleep(config.get("frequency_settling_time", 1.0))
            signal_generator.set_power(sorted_power_list[0])

        # 输入耦合只随频率变化，每个频点设一次，不在功率循环内重复下发
        # 低于阈值的频点用 DC（AC 耦合低频截止会压低读数），其余用配置值；
        # 仪器只支持 DC 时按能力折算（见 _resolve_input_coupling）
        coupling, folded_from_ac = self._resolve_input_coupling(config, frequency)
        if hasattr(spectrum_analyzer, "set_input_coupling"):
            spectrum_analyzer.set_input_coupling(coupling)
            extra = "（配置要 AC，但仪器只支持 DC，已用 DC）" if folded_from_ac else ""
            print(f"输入耦合: {coupling} (频率 {format_frequency(frequency)}){extra}")

        for power in sorted_power_list:
            signal_generator.set_power(power)
            time.sleep(config.get("power_settling_time", 1.0))

            # 外参锁定：频谱仪中心始终对准信号源名义频率，不做峰值偏移跟踪
            center_frequency = frequency
            span = self._suggest_span(power, config)
            rbw = self._suggest_rbw(power, config)
            vbw = self._suggest_vbw(power, config)
            reference_level = self._suggest_reference_level(power, config)
            attenuation = self._suggest_attenuation(power, config)
            preamp_on = self._suggest_preamp(power, config)

            measured_power, peak_frequency, found, noise_floor = self._measure_peak(
                spectrum_analyzer,
                center_frequency,
                span,
                rbw,
                vbw,
                reference_level,
                attenuation,
                config,
                config.get("average_count", 5),
                preamp_on
            )

            if measured_power is not None:
                # 未找到真峰时仍保留名义频率读到的数值（作为噪声底判据），仅标记状态
                status = "OK" if found else "SUSPECT"
                note = "" if found else "未找到真峰，读数为窗口内噪声/杂散"
            else:
                status = "SKIP"
                note = "测量失败"
                peak_frequency = None

            delta_db = None
            if measured_power is not None:
                delta_db = round(measured_power - power, 3)

            self.add_result({
                # A 区：标识与数值
                "run_id": self.run_id,
                "test_type": self.TEST_TYPE,
                "carrier_hz": frequency,
                "set_power_dbm": power,
                "measured_power_dbm": measured_power,
                "delta_db": delta_db,
                "delta_ref": "set",
                # B 区：频谱仪采集条件（衰减为 AUTO 时 sa_input_att_db 留空，由 sa_att_mode 说明）
                "sa_ref_level_dbm": reference_level,
                "sa_input_att_db": attenuation,
                "sa_att_mode": "auto" if attenuation is None else "manual",
                "sa_span_hz": span,
                "sa_rbw_hz": rbw,
                "sa_vbw_hz": vbw,
                "sa_noise_floor_dbm": noise_floor,
                # C 区：源专有
                "peak_frequency_hz": peak_frequency,
                "sa_preamp_on": self.bool_str(preamp_on),
                # 判定与时间
                "status": status,
                "note": note,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            atten_str = "AUTO" if attenuation is None else f"{attenuation} dB"
            print(
                f"频率: {format_frequency(frequency)}, "
                f"设定功率: {power} dBm, 测量功率: "
                f"{measured_power if measured_power is None else f'{measured_power:.2f}'} dBm, "
                f"衰减: {atten_str}, 预放: {'开' if preamp_on else '关'}, 状态: {status}"
            )

            if measured_power is None:
                break

        if not keep_output:
            signal_generator.enable_output(False)
            self._output_enabled = False

    def add_result(self, result):
        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)
