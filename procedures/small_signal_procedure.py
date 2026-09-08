import time
import os
from datetime import datetime
from base_test_procedure import BaseTestProcedure, format_frequency


class SmallSignalProcedure(BaseTestProcedure):
    """基于信号源功率步进和频谱仪 marker 追踪的小信号测量流程"""

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self._output_enabled = False

    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.csv_streamer = CsvStreamer(csv_path, [
            "frequency",
            "set_power_dbm",
            "measured_power_dbm",
            "error_db",
            "peak_frequency_hz",
            "span_hz",
            "rbw_hz",
            "vbw_hz",
            "reference_level_dbm",
            "attenuation_db",
            "average_count",
            "status",
            "timestamp",
        ])

    def finish_xlsx(self, xlsx_path):
        if not self.csv_streamer:
            return self.save_results(xlsx_path)
        try:
            self.csv_streamer.to_xlsx(xlsx_path, sheet_name="小信号测量数据")
            self._remove_intermediate_csv()
            return True
        except Exception as e:
            print(f"Excel 输出失败，保留 CSV 结果: {e}")
            if self.csv_streamer:
                self.csv_streamer.close()
            return False

    def finish_csv(self):
        if self.csv_streamer:
            self.csv_streamer.close()
            print(f"CSV流式存储已关闭: {self.csv_streamer.filepath}")

    def _remove_intermediate_csv(self):
        csv_path = self.csv_streamer.filepath if self.csv_streamer else None
        if csv_path and os.path.exists(csv_path):
            try:
                os.remove(csv_path)
                print(f"已删除中间CSV: {csv_path}")
            except OSError as e:
                print(f"删除中间CSV失败: {e}")

    def save_results(self, filename):
        if not self.test_results:
            print("没有小信号测量结果可保存")
            return False
        if filename.lower().endswith(".xlsx"):
            import pandas as pd
            pd.DataFrame(self.test_results).to_excel(filename, index=False)
            print(f"Excel 已保存: {filename}")
            return True
        return self.save_results_to_csv(filename)

    def _configure_spectrum_analyzer(self, spectrum_analyzer, center_frequency, span, rbw, vbw, reference_level, attenuation, coupling):
        spectrum_analyzer.set_center_frequency(center_frequency)
        spectrum_analyzer.set_span(span)
        spectrum_analyzer.set_rbw(rbw)
        spectrum_analyzer.set_vbw(vbw)
        spectrum_analyzer.set_reference_level(reference_level)
        spectrum_analyzer.set_attenuation(attenuation)
        if hasattr(spectrum_analyzer, "set_input_coupling"):
            spectrum_analyzer.set_input_coupling(coupling)

    def _within_tolerance(self, peak_frequency, expected_frequency, tolerance):
        if peak_frequency is None:
            return False
        return abs(peak_frequency - expected_frequency) <= tolerance

    def _measure_peak(self, spectrum_analyzer, expected_frequency, span, rbw, vbw, reference_level, attenuation, config, average_count):
        self._configure_spectrum_analyzer(
            spectrum_analyzer,
            expected_frequency,
            span,
            rbw,
            vbw,
            reference_level,
            attenuation,
            config.get("input_coupling", "AC")
        )
        time.sleep(config.get("sa_settling_time", 0.5))

        spectrum_analyzer.peak_search()
        peak_frequency = spectrum_analyzer.get_marker_frequency(1)

        found = self._within_tolerance(
            peak_frequency,
            expected_frequency,
            config.get("freq_tolerance_hz", 10e3)
        )

        # 始终把 marker 放到测量点：找到真峰用峰位，否则用名义频率
        # （外参锁定下以信号源名义频率为准，避免把杂散/噪声峰当成信号）
        measure_frequency = peak_frequency if found else expected_frequency
        spectrum_analyzer.set_marker_frequency(1, measure_frequency)

        measurements = []
        for _ in range(max(1, average_count)):
            power = spectrum_analyzer.measure_marker_power(1)
            if power is not None:
                measurements.append(power)
            time.sleep(0.1)

        if measurements:
            measured_power = sum(measurements) / len(measurements)
            return measured_power, measure_frequency, found
        return None, measure_frequency, found

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

            measured_power, peak_frequency, found = self._measure_peak(
                spectrum_analyzer,
                center_frequency,
                span,
                rbw,
                vbw,
                reference_level,
                attenuation,
                config,
                config.get("average_count", 5)
            )

            if measured_power is not None:
                # 未找到真峰时仍保留名义频率读到的数值（作为噪声底判据），仅标记状态
                status = "OK" if found else "未找到"
            else:
                status = "未找到"
                peak_frequency = None

            error_db = None
            if measured_power is not None:
                error_db = measured_power - power

            self.add_result({
                "frequency": frequency,
                "set_power_dbm": power,
                "measured_power_dbm": measured_power,
                "error_db": error_db,
                "peak_frequency_hz": peak_frequency,
                "span_hz": span,
                "rbw_hz": rbw,
                "vbw_hz": vbw,
                "reference_level_dbm": reference_level,
                "attenuation_db": attenuation,
                "average_count": config.get("average_count", 5),
                "status": status,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            print(
                f"频率: {format_frequency(frequency)}, "
                f"设定功率: {power} dBm, 测量功率: "
                f"{measured_power if measured_power is None else f'{measured_power:.2f}'} dBm, "
                f"状态: {status}"
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
