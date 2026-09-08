import time
import os
from datetime import datetime
import numpy as np
from base_test_procedure import BaseTestProcedure, format_frequency


class SpuriousProcedure(BaseTestProcedure):
    """粗扫找峰 + 二次精测的杂散定量测量流程"""

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self._output_enabled = False

    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.csv_streamer = CsvStreamer(csv_path, [
            "carrier_frequency_hz",
            "carrier_power_dbm",
            "frequency_hz",
            "amplitude_dbm",
            "offset_hz",
            "relative_dbc",
            "rbw_hz",
            "vbw_hz",
            "span_hz",
            "noise_floor_dbm",
            "status",
            "average_count",
            "std_db",
            "timestamp",
        ])

    def finish_xlsx(self, xlsx_path):
        if not self.csv_streamer:
            return self.save_results(xlsx_path)
        self.csv_streamer.to_xlsx(xlsx_path, sheet_name="杂散测量数据")
        self._remove_intermediate_csv()

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
            print("没有杂散测量结果可保存")
            return False
        if filename.lower().endswith(".xlsx"):
            import pandas as pd
            pd.DataFrame(self.test_results).to_excel(filename, index=False)
            print(f"Excel 已保存: {filename}")
            return True
        return self.save_results_to_csv(filename)

    def sort_results(self):
        self.test_results.sort(
            key=lambda row: (row["carrier_frequency_hz"], row["frequency_hz"])
        )

    def add_result(self, result):
        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

    def _configure_spectrum_analyzer(
        self,
        spectrum_analyzer,
        center_frequency,
        span,
        rbw,
        vbw,
        reference_level,
        attenuation,
        trace_mode,
        detector,
        coupling,
    ):
        spectrum_analyzer.set_center_frequency(center_frequency)
        spectrum_analyzer.set_span(span)
        spectrum_analyzer.set_rbw(rbw)
        spectrum_analyzer.set_vbw(vbw)
        spectrum_analyzer.set_reference_level(reference_level)
        spectrum_analyzer.set_attenuation(attenuation)
        if hasattr(spectrum_analyzer, "set_trace_mode"):
            spectrum_analyzer.set_trace_mode(trace_mode)
        if hasattr(spectrum_analyzer, "set_detector"):
            spectrum_analyzer.set_detector(detector)
        if hasattr(spectrum_analyzer, "set_input_coupling"):
            spectrum_analyzer.set_input_coupling(coupling)

    def _estimate_noise_floor(self, trace):
        if not trace:
            return None
        return float(np.median(trace))

    def _trace_frequencies(self, center_frequency, span, trace_length):
        if trace_length <= 0:
            return []
        step = span / trace_length
        return [
            center_frequency - span / 2.0 + (index + 0.5) * step
            for index in range(trace_length)
        ]

    def _find_candidate_peaks(self, frequencies, powers, noise_floor, config):
        if noise_floor is None:
            return []
        height = noise_floor + config.get("noise_margin_db", 6.0)
        min_distance = max(
            1,
            int(len(powers) * config.get("min_peak_distance_ratio", 0.005))
        )
        peak_indices = self._find_local_peaks(
            powers,
            height,
            min_distance,
            config.get("peak_prominence_db", 10.0)
        )

        candidates = [
            {
                "frequency": frequencies[int(index)],
                "power": float(powers[int(index)]),
                "index": int(index),
            }
            for index in peak_indices
        ]
        candidates.sort(key=lambda item: item["power"], reverse=True)
        max_count = config.get("max_peak_count_per_segment", 200)
        return candidates[:max_count]

    def _find_local_peaks(self, powers, height, min_distance, min_prominence):
        powers = np.asarray(powers, dtype=float)
        if len(powers) < 3:
            return []
        peak_indices = []
        last_peak_index = -min_distance
        window = max(10, min_distance * 2)

        for index in range(len(powers)):
            # 局部极大(含平顶峰右边缘)。首尾边界点也参与判断。
            if index > 0 and powers[index] < powers[index - 1]:
                continue
            if index < len(powers) - 1 and powers[index] <= powers[index + 1]:
                continue

            if powers[index] < height:
                continue

            left = powers[max(0, index - window):index]
            right = powers[index + 1:min(len(powers), index + 1 + window)]
            left_base = float(np.median(left)) if len(left) else -np.inf
            right_base = float(np.median(right)) if len(right) else -np.inf
            baseline = max(left_base, right_base)
            if not np.isfinite(baseline):
                baseline = float(powers[index])
            prominence = float(powers[index] - baseline)

            if prominence < min_prominence:
                continue

            if index - last_peak_index < min_distance:
                if peak_indices and powers[peak_indices[-1]] < powers[index]:
                    peak_indices[-1] = index
                continue

            peak_indices.append(index)
            last_peak_index = index

        return peak_indices

    def _is_harmonic(self, frequency, carrier_frequency, config):
        """判断某个峰是否落在 n×CF（n=2..spur_upper_harmonic_order）上"""
        if not frequency or carrier_frequency <= 0:
            return False
        tolerance = config.get("harmonic_tolerance_hz", 1e3)
        max_order = int(config.get("spur_upper_harmonic_order", 2))
        for order in range(2, max_order + 1):
            harmonic_frequency = order * carrier_frequency
            if abs(frequency - harmonic_frequency) <= tolerance:
                return True
        return False

    def _deduplicate_candidates(self, candidates, tolerance_hz):
        unique = []
        for candidate in candidates:
            if not any(
                abs(candidate["frequency"] - existing["frequency"]) <= tolerance_hz
                for existing in unique
            ):
                unique.append(candidate)
        return unique

    def _measure_marker_average(self, spectrum_analyzer, average_count):
        measurements = []
        for _ in range(max(1, average_count)):
            power = spectrum_analyzer.measure_marker_power(1)
            if power is not None:
                measurements.append(power)
            time.sleep(0.1)

        if not measurements:
            return None, None

        values = np.array(measurements)
        return float(values.mean()), float(values.std())

    def _measure_carrier(self, spectrum_analyzer, carrier_frequency, config):
        span = max(config.get("refine_span_hz", 100e3) * 2.0, 1e5)
        rbw = config.get("refine_rbw_hz", 1e3)
        vbw = max(config.get("refine_vbw_hz", 1e3), rbw)
        self._configure_spectrum_analyzer(
            spectrum_analyzer,
            carrier_frequency,
            span,
            rbw,
            vbw,
            config.get("reference_level_dbm", 20),
            config.get("attenuation_db", 20),
            config.get("refine_trace_mode", "WRITE"),
            config.get("refine_detector", "POS"),
            config.get("input_coupling", "AC"),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        spectrum_analyzer.wait_for_sweep(
            config.get("refine_sweep_count", 1)
        )
        spectrum_analyzer.peak_search()

        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - carrier_frequency) > span / 2.0:
            spectrum_analyzer.set_marker_frequency(1, carrier_frequency)
            peak_frequency = carrier_frequency

        power, _ = self._measure_marker_average(
            spectrum_analyzer,
            config.get("average_count", 5)
        )
        return power, peak_frequency

    def _refine_peak(self, spectrum_analyzer, candidate, carrier_frequency, config):
        span = config.get("refine_span_hz", 100e3)
        rbw = config.get("refine_rbw_hz", 1e3)
        vbw = max(config.get("refine_vbw_hz", 1e3), rbw)

        self._configure_spectrum_analyzer(
            spectrum_analyzer,
            candidate["frequency"],
            span,
            rbw,
            vbw,
            config.get("reference_level_dbm", 20),
            config.get("attenuation_db", 20),
            config.get("refine_trace_mode", "WRITE"),
            config.get("refine_detector", "POS"),
            config.get("input_coupling", "AC"),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        spectrum_analyzer.wait_for_sweep(
            config.get("refine_sweep_count", 1)
        )

        spectrum_analyzer.peak_search()
        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - candidate["frequency"]) > config.get("candidate_tolerance_hz", 10e3):
            spectrum_analyzer.set_marker_frequency(1, candidate["frequency"])
            peak_frequency = candidate["frequency"]

        measured_power, std_db = self._measure_marker_average(
            spectrum_analyzer,
            config.get("average_count", 5)
        )

        trace = spectrum_analyzer.get_trace(1)
        noise_floor = self._estimate_noise_floor(trace)
        if noise_floor is None:
            noise_floor = candidate.get("noise_floor_dbm")

        status = "已确认"
        if measured_power is None:
            status = "测量失败"
        elif noise_floor is not None and measured_power < noise_floor + config.get("noise_floor_reliable_margin_db", 10.0):
            status = "接近噪声底"
            measured_power = None
        elif std_db is not None and std_db > config.get("stability_limit_db", 1.0):
            status = "不稳定"

        return {
            "frequency_hz": peak_frequency,
            "amplitude_dbm": measured_power,
            "offset_hz": peak_frequency - carrier_frequency,
            "rbw_hz": rbw,
            "vbw_hz": vbw,
            "span_hz": span,
            "noise_floor_dbm": noise_floor,
            "status": status,
            "average_count": config.get("average_count", 5),
            "std_db": std_db,
        }

    def run_spurious_test(
        self,
        signal_generator,
        spectrum_analyzer,
        carrier_frequency,
        carrier_power,
        config,
        keep_output=False,
    ):
        if not self._output_enabled:
            signal_generator.set_frequency(carrier_frequency)
            time.sleep(config.get("sa_settling_time_s", 0.5))
            signal_generator.set_power(carrier_power)
            signal_generator.enable_output(True)
            self._output_enabled = True
        else:
            signal_generator.set_frequency(carrier_frequency)
            time.sleep(config.get("sa_settling_time_s", 0.5))
            signal_generator.set_power(carrier_power)

        # 搜索带：载波近端保护带之外，向上扫到 N×CF，封顶到仪器可用上限
        guard_width = max(
            config.get("carrier_guard_fixed_hz", 10e3),
            config.get("carrier_guard_ratio", 0.10) * carrier_frequency
        )
        start_frequency = carrier_frequency + guard_width
        end_frequency = min(
            config.get("spur_upper_harmonic_order", 2) * carrier_frequency,
            config.get("max_frequency_hz", 20e9)
        )
        if end_frequency <= start_frequency:
            print(
                f"载波 {carrier_frequency / 1e6:.3f} MHz 无有效搜索区间 "
                f"(保护带 {guard_width / 1e3:.1f} kHz, 上界 {end_frequency / 1e6:.3f} MHz)"
            )
            if not keep_output:
                signal_generator.enable_output(False)
                self._output_enabled = False
            return

        center_frequency = (start_frequency + end_frequency) / 2.0
        actual_span = end_frequency - start_frequency

        coarse_rbw = config.get("scan_rbw_hz", 100.0)
        print(
            f"搜索带 {start_frequency / 1e6:.3f} ~ {end_frequency / 1e6:.3f} MHz, "
            f"粗扫 RBW {coarse_rbw / 1e3:.2f} kHz"
        )

        self._configure_spectrum_analyzer(
            spectrum_analyzer,
            center_frequency,
            actual_span,
            coarse_rbw,
            max(config.get("scan_vbw_hz", 30e3), coarse_rbw),
            config.get("reference_level_dbm", 20),
            config.get("attenuation_db", 20),
            config.get("scan_trace_mode", "MAXH"),
            config.get("scan_detector", "POS"),
            config.get("input_coupling", "AC"),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        spectrum_analyzer.wait_for_sweep(
            config.get("scan_sweep_count", 1)
        )

        trace = spectrum_analyzer.get_trace(1)
        if trace:
            frequencies = self._trace_frequencies(center_frequency, actual_span, len(trace))
            noise_floor = self._estimate_noise_floor(trace)
            candidates = self._find_candidate_peaks(
                frequencies,
                trace,
                noise_floor,
                config
            )
            for candidate in candidates:
                candidate["noise_floor_dbm"] = noise_floor
            candidates = self._deduplicate_candidates(
                candidates,
                config.get("candidate_tolerance_hz", 10e3)
            )
        else:
            candidates = []

        if not candidates:
            print(
                f"载波 {carrier_frequency / 1e6:.3f} MHz: "
                "搜索带内未发现杂散候选，不输出结果"
            )
            if not keep_output:
                signal_generator.enable_output(False)
                self._output_enabled = False
            return

        # 有候选峰才测载波电平，作为 dBc 参考
        carrier_power_measured, _ = self._measure_carrier(
            spectrum_analyzer,
            carrier_frequency,
            config
        )
        carrier_reference = (
            carrier_power_measured
            if carrier_power_measured is not None
            else carrier_power
        )

        # 只精测粗扫中幅度最大的前 K 个候选，节约时间
        candidates.sort(key=lambda item: item["power"], reverse=True)
        candidates = candidates[:config.get("refine_candidate_limit", 15)]

        refined_rows = []
        for candidate in candidates:
            refined = self._refine_peak(
                spectrum_analyzer,
                candidate,
                carrier_frequency,
                config
            )
            result = {
                "carrier_frequency_hz": carrier_frequency,
                "carrier_power_dbm": carrier_reference,
            }
            result.update(refined)
            result["relative_dbc"] = (
                refined["amplitude_dbm"] - carrier_reference
                if refined["amplitude_dbm"] is not None
                else None
            )
            result["is_harmonic"] = self._is_harmonic(
                refined["frequency_hz"],
                carrier_frequency,
                config
            )
            result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            refined_rows.append(result)

        # 按幅度排序：剔除谐波后取最大的前 N 条，谐波不进入最终结果
        valid_rows = [r for r in refined_rows if r["amplitude_dbm"] is not None]
        valid_rows.sort(key=lambda r: r["amplitude_dbm"], reverse=True)
        non_harmonic = [r for r in valid_rows if not r["is_harmonic"]]

        top_spurs = non_harmonic[:config.get("max_spur_report_count", 5)]
        for row in top_spurs:
            row.pop("is_harmonic", None)
            self.add_result(row)

        if top_spurs:
            print(
                f"载波 {carrier_frequency / 1e6:.3f} MHz: "
                f"输出 {len(top_spurs)} 条非谐波杂散"
            )
        else:
            print(
                f"载波 {carrier_frequency / 1e6:.3f} MHz: "
                "未发现非谐波杂散(候选均为谐波或未通过精测)，不输出结果"
            )

        if not keep_output:
            signal_generator.enable_output(False)
            self._output_enabled = False
