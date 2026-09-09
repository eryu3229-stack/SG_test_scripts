import time
import os
import json
import numpy as np
from datetime import datetime
from base_test_procedure import BaseTestProcedure, format_frequency


class SpuriousProcedure(BaseTestProcedure):
    """分段扫描 + Trace 全量峰值检测 + 候选验证的杂散测量流程

    设计目标：速度不是核心，全面掌握频谱杂散情况。
    - 近载波：10 MHz / 100 MHz SPAN，RBW 从 100 Hz 起
    - 远载波：1 GHz 分段覆盖全频段
    - 谐波：单独逐阶测量
    - 候选：全部列出，不做 next-peak 依赖
    - 验证：衰减器阶跃、RBW 缩放、重复性、源开关环境扫描
    """

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self._output_enabled = False
        self._ambient_spurs = []  # 源 OFF 时测到的固定频点

    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.csv_streamer = CsvStreamer(csv_path, [
            "carrier_frequency_hz",
            "carrier_power_dbm",
            "segment_name",
            "frequency_hz",
            "amplitude_dbm",
            "offset_hz",
            "relative_dbc",
            "rbw_hz",
            "span_hz",
            "noise_floor_dbm",
            "is_harmonic",
            "harmonic_order",
            "status",
            "validation_notes",
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
            key=lambda row: (row["carrier_frequency_hz"], row["segment_name"], row["frequency_hz"])
        )

    def add_result(self, result):
        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

    # ------------------------------------------------------------------
    # 频谱仪基础控制
    # ------------------------------------------------------------------
    def _configure_sa(
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
        scale_div_db=15,
    ):
        spectrum_analyzer.set_center_frequency(center_frequency)
        spectrum_analyzer.set_span(span)
        spectrum_analyzer.set_rbw(rbw)
        spectrum_analyzer.set_vbw(vbw)
        spectrum_analyzer.set_reference_level(reference_level)
        spectrum_analyzer.set_scale_div(scale_div_db)
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

    # ------------------------------------------------------------------
    # 峰值检测（基于 trace，不依赖 next-peak）
    # ------------------------------------------------------------------
    def _find_local_peaks(self, powers, height, min_distance, min_prominence):
        powers = np.asarray(powers, dtype=float)
        if len(powers) < 3:
            return []

        peak_indices = []
        last_peak_index = -min_distance
        window = max(10, min_distance * 2)

        for index in range(len(powers)):
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

    def _find_candidates(self, frequencies, powers, noise_floor, peak_config):
        if noise_floor is None:
            return []

        height = noise_floor + peak_config.get("noise_margin_db", 6.0)
        min_prominence = peak_config.get("peak_prominence_db", 3.0)
        min_distance_hz = peak_config.get("min_peak_distance_hz", 1e3)
        max_count = peak_config.get("max_peak_count_per_segment", 200)

        if len(frequencies) < 2:
            return []
        freq_step = abs(frequencies[1] - frequencies[0])
        min_distance = max(1, int(round(min_distance_hz / freq_step)))

        peak_indices = self._find_local_peaks(
            powers,
            height,
            min_distance,
            min_prominence,
        )

        candidates = [
            {
                "frequency_hz": float(frequencies[int(index)]),
                "amplitude_dbm": float(powers[int(index)]),
                "index": int(index),
                "noise_floor_dbm": noise_floor,
            }
            for index in peak_indices
        ]
        candidates.sort(key=lambda item: item["amplitude_dbm"], reverse=True)
        return candidates[:max_count]

    def _deduplicate_candidates(self, candidates, tolerance_hz):
        unique = []

        def _power(c):
            return c.get("amplitude_dbm", c.get("power", -999.0))

        def _freq(c):
            return c.get("frequency_hz", c.get("frequency", 0.0))

        for candidate in sorted(candidates, key=_power, reverse=True):
            freq = _freq(candidate)
            if not any(
                abs(freq - _freq(existing)) <= tolerance_hz
                for existing in unique
            ):
                unique.append(candidate)
        return unique

    # ------------------------------------------------------------------
    # 载波测量
    # ------------------------------------------------------------------
    def _measure_carrier(self, spectrum_analyzer, carrier_frequency, config):
        span = max(200e3, carrier_frequency * 0.002)
        rbw = 1e3
        vbw = 3e3
        self._configure_sa(
            spectrum_analyzer,
            carrier_frequency,
            span,
            rbw,
            vbw,
            config.get("reference_level_dbm", 10),
            config.get("attenuation_db", 20),
            "WRITE",
            "POS",
            config.get("input_coupling", "DC"),
            config.get("scale_div_db", 15),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        if not spectrum_analyzer.wait_for_sweep(1, span_hz=span):
            print("载波扫描同步失败，跳过该载波")
            return None, carrier_frequency
        spectrum_analyzer.peak_search()

        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - carrier_frequency) > span / 2.0:
            spectrum_analyzer.set_marker_frequency(1, carrier_frequency)
            peak_frequency = carrier_frequency

        measurements = []
        for _ in range(5):
            power = spectrum_analyzer.measure_marker_power(1)
            if power is not None:
                measurements.append(power)
            time.sleep(0.1)

        if measurements:
            return float(np.mean(measurements)), peak_frequency
        return None, peak_frequency

    # ------------------------------------------------------------------
    # 候选精测
    # ------------------------------------------------------------------
    def _refine_candidate(self, spectrum_analyzer, candidate, carrier_frequency, config):
        refine = config.get("refine_config", {})
        span = refine.get("span_hz", 1e6)
        rbw = refine.get("rbw_hz", 100)
        vbw = refine.get("vbw_hz", 300)
        sweep_count = refine.get("sweep_count", 3)
        trace_mode = refine.get("trace_mode", "WRITE")
        detector = refine.get("detector", "POS")
        average_count = refine.get("average_count", 5)

        self._configure_sa(
            spectrum_analyzer,
            candidate["frequency_hz"],
            span,
            rbw,
            vbw,
            config.get("reference_level_dbm", 10),
            config.get("attenuation_db", 20),
            trace_mode,
            detector,
            config.get("input_coupling", "DC"),
            config.get("scale_div_db", 15),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        if not spectrum_analyzer.wait_for_sweep(sweep_count, span_hz=span):
            print(f"候选 {candidate['frequency_hz']/1e6:.3f} MHz 精测扫描同步失败")
            return None
        spectrum_analyzer.peak_search()
        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - candidate["frequency_hz"]) > span / 2.0:
            spectrum_analyzer.set_marker_frequency(1, candidate["frequency_hz"])
            peak_frequency = candidate["frequency_hz"]

        measurements = []
        for _ in range(max(1, average_count)):
            power = spectrum_analyzer.measure_marker_power(1)
            if power is not None:
                measurements.append(power)
            time.sleep(0.05)

        if not measurements:
            return None

        trace = spectrum_analyzer.get_trace(1)
        noise_floor = self._estimate_noise_floor(trace)
        if noise_floor is None:
            noise_floor = candidate.get("noise_floor_dbm")

        return {
            "frequency_hz": peak_frequency,
            "amplitude_dbm": float(np.mean(measurements)),
            "std_db": float(np.std(measurements)),
            "rbw_hz": rbw,
            "span_hz": span,
            "noise_floor_dbm": noise_floor,
        }

    # ------------------------------------------------------------------
    # 谐波判定
    # ------------------------------------------------------------------
    def _classify_harmonic(self, frequency, carrier_frequency, harmonic_config):
        if not frequency or carrier_frequency <= 0:
            return False, None
        tolerance = harmonic_config.get("tolerance_hz", 1e6)
        for order in harmonic_config.get("orders", [2, 3, 4, 5, 6]):
            harmonic_frequency = order * carrier_frequency
            if abs(frequency - harmonic_frequency) <= tolerance:
                return True, order
        return False, None

    # ------------------------------------------------------------------
    # 候选验证
    # ------------------------------------------------------------------
    def _validate_candidate(
        self,
        spectrum_analyzer,
        signal_generator,
        refined,
        carrier_frequency,
        carrier_power,
        config,
    ):
        validation = config.get("validation", {})
        if not validation.get("enable", True):
            return "未验证", {}

        notes = {}
        status_flags = []

        # 1. 重复性
        stability_count = validation.get("stability_count", 5)
        stability_limit = validation.get("stability_limit_db", 1.0)
        if refined.get("std_db") is not None and refined["std_db"] > stability_limit:
            status_flags.append("不稳定")
            notes["stability_std_db"] = refined["std_db"]

        # 2. 衰减器阶跃测试：dBc 应基本不变
        if validation.get("attenuator_step_check", True):
            att_base = config.get("attenuation_db", 20)
            att_steps = validation.get("attenuator_steps", [-2, 0, 2])
            dbc_tolerance = validation.get("attenuator_dbc_tolerance_db", 2.0)
            dbc_values = []
            for step in att_steps:
                spectrum_analyzer.set_attenuation(att_base + step)
                time.sleep(0.2)
                power = spectrum_analyzer.measure_marker_power(1)
                if power is not None and carrier_power is not None:
                    dbc_values.append(power - carrier_power)
            spectrum_analyzer.set_attenuation(att_base)
            if dbc_values:
                dbc_range = max(dbc_values) - min(dbc_values)
                notes["attenuator_dbc_values"] = [round(v, 2) for v in dbc_values]
                notes["attenuator_dbc_range_db"] = round(dbc_range, 2)
                if dbc_range > dbc_tolerance:
                    status_flags.append("衰减器响应异常")

        # 3. RBW 缩放测试：真 CW 杂散幅度基本不变
        if validation.get("rbw_scaling_check", True):
            base_rbw = refined.get("rbw_hz", 100)
            ratios = validation.get("rbw_scaling_ratios", [1, 2])
            amp_tolerance = validation.get("rbw_scaling_amplitude_tolerance_db", 2.0)
            amps = []
            for ratio in ratios:
                spectrum_analyzer.set_rbw(base_rbw * ratio)
                spectrum_analyzer.set_vbw(base_rbw * ratio * 3)
                time.sleep(0.2)
                if not spectrum_analyzer.wait_for_sweep(1, span_hz=refined.get("span_hz", 1e6)):
                    print(f"RBW缩放测试扫描同步失败，ratio={ratio}")
                    continue
                power = spectrum_analyzer.measure_marker_power(1)
                if power is not None:
                    amps.append(power)
            spectrum_analyzer.set_rbw(base_rbw)
            spectrum_analyzer.set_vbw(base_rbw * 3)
            if amps:
                amp_range = max(amps) - min(amps)
                notes["rbw_scaling_amplitudes_dbm"] = [round(v, 2) for v in amps]
                notes["rbw_scaling_range_db"] = round(amp_range, 2)
                if amp_range > amp_tolerance:
                    status_flags.append("RBW缩放响应异常")

        # 4. 环境杂散比对：候选频率是否在源 OFF 时也存在
        if self._ambient_spurs:
            freq_match = any(
                abs(refined["frequency_hz"] - amb["frequency"]) <= validation.get("cf_step_freq_tolerance_hz", 100e3)
                for amb in self._ambient_spurs
            )
            if freq_match:
                status_flags.append("源OFF仍存在")

        if not status_flags:
            return "已确认", notes
        if any(s in ("源OFF仍存在", "衰减器响应异常", "RBW缩放响应异常") for s in status_flags):
            return "疑似仪器产物", notes
        return "疑似", notes

    # ------------------------------------------------------------------
    # 源 OFF 环境扫描（每个载波一次）
    # ------------------------------------------------------------------
    def _scan_ambient(self, spectrum_analyzer, signal_generator, carrier_frequency, config):
        validation = config.get("validation", {})
        if not validation.get("source_off_check", True):
            return

        print(f"载波 {carrier_frequency / 1e6:.3f} MHz: 关闭信号源进行环境扫描")
        signal_generator.enable_output(False)
        time.sleep(0.5)

        self._ambient_spurs = []
        segments = config.get("near_carrier_segments", []) + [config.get("far_carrier_segment", {})]
        for segment in segments:
            if not segment:
                continue
            span = segment.get("span_hz", 10e6)
            center = carrier_frequency
            if span > 200e6:
                # 远载波只扫包含 CF 附近可能环境的 1G 段
                continue

            self._configure_sa(
                spectrum_analyzer,
                center,
                span,
                segment.get("rbw_hz", 1e3),
                segment.get("vbw_hz", 3e3),
                config.get("reference_level_dbm", 10),
                config.get("attenuation_db", 20),
                segment.get("trace_mode", "MAXH"),
                segment.get("detector", "POS"),
                config.get("input_coupling", "DC"),
                config.get("scale_div_db", 15),
            )
            time.sleep(config.get("sa_settling_time_s", 0.5))
            if not spectrum_analyzer.wait_for_sweep(segment.get("sweep_count", 5), span_hz=span):
                print(f"环境扫描 segment {segment_name} 同步失败，跳过")
                continue

            trace = spectrum_analyzer.get_trace(1)
            if not trace:
                continue
            frequencies = self._trace_frequencies(center, span, len(trace))
            noise_floor = self._estimate_noise_floor(trace)
            candidates = self._find_candidates(
                frequencies,
                trace,
                noise_floor,
                config.get("peak_detection", {}),
            )
            self._ambient_spurs.extend(candidates)

        signal_generator.enable_output(True)
        time.sleep(0.5)
        print(f"环境扫描完成，记录 {len(self._ambient_spurs)} 条环境/仪器杂散")

    # ------------------------------------------------------------------
    # 分段扫描
    # ------------------------------------------------------------------
    def _scan_segment(
        self,
        spectrum_analyzer,
        segment_config,
        center_frequency,
        carrier_frequency,
        carrier_power,
        config,
    ):
        span = segment_config.get("span_hz", 10e6)
        rbw = segment_config.get("rbw_hz", 100)
        vbw = segment_config.get("vbw_hz", 300)
        sweep_count = segment_config.get("sweep_count", 10)
        trace_mode = segment_config.get("trace_mode", "MAXH")
        detector = segment_config.get("detector", "POS")
        segment_name = segment_config.get("name", "unknown")

        print(
            f"    {segment_name}: {center_frequency / 1e6:.0f} MHz / "
            f"{span / 1e6:.0f} MHz / RBW {rbw:.0f} Hz / sweep {sweep_count}"
        )

        self._configure_sa(
            spectrum_analyzer,
            center_frequency,
            span,
            rbw,
            vbw,
            config.get("reference_level_dbm", 10),
            config.get("attenuation_db", 20),
            trace_mode,
            detector,
            config.get("input_coupling", "DC"),
            config.get("scale_div_db", 15),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        if not spectrum_analyzer.wait_for_sweep(sweep_count, span_hz=span):
            print(f"  {segment_name}: 扫描同步失败，跳过该段")
            return []

        trace = spectrum_analyzer.get_trace(1)
        if not trace:
            print(f"  {segment_name}: 未读取到 trace")
            return []

        frequencies = self._trace_frequencies(center_frequency, span, len(trace))
        noise_floor = self._estimate_noise_floor(trace)
        candidates = self._find_candidates(
            frequencies,
            trace,
            noise_floor,
            config.get("peak_detection", {}),
        )
        print(f"  {segment_name}: 噪声底 {noise_floor:.1f} dBm, 候选 {len(candidates)} 个")

        refined_list = []
        min_offset = config.get("min_spur_offset_hz", 5e3)
        for candidate in candidates:
            # 跳过载波保护带内
            if abs(candidate["frequency_hz"] - carrier_frequency) <= config.get("carrier_guard_hz", 100e3):
                continue
            # 跳过偏移过小的测量伪影
            if abs(candidate["frequency_hz"] - carrier_frequency) < min_offset:
                continue

            refined = self._refine_candidate(
                spectrum_analyzer,
                candidate,
                carrier_frequency,
                config,
            )
            if refined is None:
                continue

            # 精测后仍高于噪声底才保留
            noise_margin = config.get("validation", {}).get("noise_floor_reliable_margin_db", 10.0)
            if refined["noise_floor_dbm"] is not None and refined["amplitude_dbm"] < refined["noise_floor_dbm"] + noise_margin:
                continue

            refined_list.append(refined)

        return refined_list

    # ------------------------------------------------------------------
    # 远载波 1 GHz 分段生成
    # ------------------------------------------------------------------
    def _build_far_segment_centers(self, carrier_frequency, coverage, span):
        """以载波为中心，向两侧各扩展 coverage/2 的范围，按 span 分段。

        Args:
            carrier_frequency: 载波频率 (Hz)
            coverage: 远载波总覆盖宽度 (Hz)，以 CF 为中心
            span: 每段 SPAN (Hz)

        Returns:
            list of segment center frequencies (Hz)
        """
        half_cov = coverage / 2.0
        half_span = span / 2.0
        start = carrier_frequency - half_cov + half_span
        stop = carrier_frequency + half_cov
        centers = []
        center = start
        while center <= stop:
            centers.append(center)
            center += span
        return centers

    # ------------------------------------------------------------------
    # 谐波测量
    # ------------------------------------------------------------------
    def _measure_harmonics(self, spectrum_analyzer, carrier_frequency, carrier_power, config):
        harmonic_config = config.get("harmonic_config", {})
        results = []
        orders = harmonic_config.get("orders", [2, 3, 4, 5, 6])
        for idx, order in enumerate(orders, 1):
            harmonic_freq = carrier_frequency * order
            if harmonic_freq > config.get("max_frequency_hz", 20e9):
                print(f"    [{idx}/{len(orders)}] H{order} = {harmonic_freq / 1e9:.3f} GHz 超量程，跳过")
                continue

            span = harmonic_config.get("span_hz", 10e6)
            rbw = harmonic_config.get("rbw_hz", 1e3)
            vbw = harmonic_config.get("vbw_hz", 3e3)
            sweep_count = harmonic_config.get("sweep_count", 5)
            print(f"    [{idx}/{len(orders)}] H{order} = {harmonic_freq / 1e9:.3f} GHz")

            self._configure_sa(
                spectrum_analyzer,
                harmonic_freq,
                span,
                rbw,
                vbw,
                config.get("reference_level_dbm", 10),
                config.get("attenuation_db", 20),
                harmonic_config.get("trace_mode", "MAXH"),
                harmonic_config.get("detector", "POS"),
                config.get("input_coupling", "DC"),
                config.get("scale_div_db", 15),
            )
            time.sleep(config.get("sa_settling_time_s", 0.5))
            if not spectrum_analyzer.wait_for_sweep(sweep_count, span_hz=span):
                print(f"  谐波 {order} 次扫描同步失败，跳过")
                continue
            spectrum_analyzer.peak_search()

            peak_frequency = spectrum_analyzer.get_marker_frequency(1)
            peak_power = spectrum_analyzer.measure_marker_power(1)

            if peak_power is None:
                continue

            trace = spectrum_analyzer.get_trace(1)
            noise_floor = self._estimate_noise_floor(trace)

            results.append({
                "frequency_hz": peak_frequency,
                "amplitude_dbm": peak_power,
                "offset_hz": peak_frequency - carrier_frequency,
                "rbw_hz": rbw,
                "span_hz": span,
                "noise_floor_dbm": noise_floor,
                "is_harmonic": True,
                "harmonic_order": order,
            })
        return results

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
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

        print(f"\n[主频 {carrier_frequency / 1e6:.3f} MHz, {carrier_power} dBm] 开始杂散扫描")

        # 1. 测载波
        carrier_power_measured, carrier_freq_actual = self._measure_carrier(
            spectrum_analyzer,
            carrier_frequency,
            config,
        )
        carrier_reference = (
            carrier_power_measured if carrier_power_measured is not None else carrier_power
        )
        carrier_freq_reference = (
            carrier_freq_actual if carrier_freq_actual is not None else carrier_frequency
        )
        print(f"  实测载波: {carrier_freq_reference / 1e6:.6f} MHz, {carrier_reference:.2f} dBm")

        all_candidates = []

        # 2. 近载波分段扫描（以载波为中心）
        near_segments = config.get("near_carrier_segments", [])
        print(f"  近载波扫描: {len(near_segments)} 段")
        for idx, segment in enumerate(near_segments, 1):
            print(f"  [{idx}/{len(near_segments)}] {segment.get('name', 'near_unknown')}")
            refined = self._scan_segment(
                spectrum_analyzer,
                segment,
                carrier_freq_reference,
                carrier_freq_reference,
                carrier_reference,
                config,
            )
            for r in refined:
                r["segment_name"] = segment.get("name", "near_unknown")
            all_candidates.extend(refined)

        # 3. 远载波 1 GHz 分段扫描（以 CF 为中心，受 coverage 限制）
        far_segment = config.get("far_carrier_segment", {})
        if far_segment:
            coverage = far_segment.get("coverage_hz", 2e9)
            span = far_segment.get("span_hz", 1e9)
            centers = self._build_far_segment_centers(
                carrier_freq_reference,
                coverage,
                span,
            )
            print(f"  远载波扫描: CF ± {coverage / 2e9:.1f} GHz, 共 {len(centers)} 段")
            for idx, center in enumerate(centers, 1):
                print(f"  [{idx}/{len(centers)}] far_{center / 1e9:.1f}GHz")
                refined = self._scan_segment(
                    spectrum_analyzer,
                    far_segment,
                    center,
                    carrier_freq_reference,
                    carrier_reference,
                    config,
                )
                for r in refined:
                    r["segment_name"] = f"far_{center / 1e9:.1f}GHz"
                all_candidates.extend(refined)

        # 4. 源 OFF 环境扫描（仅在启用时显示）
        if config.get("validation", {}).get("source_off_check", False):
            print("  源 OFF 环境扫描")
            self._scan_ambient(spectrum_analyzer, signal_generator, carrier_freq_reference, config)

        # 5. 谐波测量（仅在输出包含谐波时实测；否则仅用数学关系判断）
        output_config = config.get("output", {})
        include_harmonics = output_config.get("include_harmonics", False)
        if include_harmonics:
            harmonic_orders = config.get("harmonic_config", {}).get("orders", [2, 3, 4, 5, 6])
            print(f"  谐波扫描: {len(harmonic_orders)} 阶")
            harmonic_results = self._measure_harmonics(
                spectrum_analyzer,
                carrier_freq_reference,
                carrier_reference,
                config,
            )
            for hr in harmonic_results:
                hr["segment_name"] = f"harmonic_{hr['harmonic_order']}"
            all_candidates.extend(harmonic_results)
            print(f"  谐波扫描完成: {len(harmonic_results)} 个")

        # 6. 去重、验证、输出
        dedup_tolerance = config.get("peak_detection", {}).get("min_peak_distance_hz", 1e3)
        all_candidates = self._deduplicate_candidates(all_candidates, dedup_tolerance)

        output_config = config.get("output", {})
        include_unconfirmed = output_config.get("include_unconfirmed", True)
        max_candidates = output_config.get("max_candidates_per_segment")

        if max_candidates is not None:
            all_candidates.sort(key=lambda c: c["amplitude_dbm"], reverse=True)
            all_candidates = all_candidates[:max_candidates]

        print(f"  待验证候选: {len(all_candidates)} 个")
        confirmed_count = 0
        min_offset = config.get("min_spur_offset_hz", 5e3)
        for idx, candidate in enumerate(all_candidates, 1):
            offset = abs(candidate["frequency_hz"] - carrier_freq_reference)
            if offset < min_offset and not candidate.get("is_harmonic", False):
                print(f"  验证 [{idx}/{len(all_candidates)}] {candidate['frequency_hz'] / 1e6:.3f} MHz - 偏移 {offset:.0f} Hz 过小，跳过")
                continue
            print(f"  验证 [{idx}/{len(all_candidates)}] {candidate['frequency_hz'] / 1e6:.3f} MHz")
            is_harmonic = candidate.get("is_harmonic", False)
            harmonic_order = candidate.get("harmonic_order", None)

            if not is_harmonic:
                is_harmonic, harmonic_order = self._classify_harmonic(
                    candidate["frequency_hz"],
                    carrier_freq_reference,
                    config.get("harmonic_config", {}),
                )

            status, validation_notes = "已确认", {}
            if not candidate.get("is_harmonic", False) or not config.get("output", {}).get("include_harmonics", True):
                # 谐波条目跳过验证，直接标记
                status, validation_notes = self._validate_candidate(
                    spectrum_analyzer,
                    signal_generator,
                    candidate,
                    carrier_freq_reference,
                    carrier_reference,
                    config,
                )

            if status == "已确认":
                confirmed_count += 1
            elif not include_unconfirmed:
                continue

            result = {
                "carrier_frequency_hz": carrier_freq_reference,
                "carrier_power_dbm": carrier_reference,
                "segment_name": candidate.get("segment_name", "unknown"),
                "frequency_hz": candidate["frequency_hz"],
                "amplitude_dbm": candidate["amplitude_dbm"],
                "offset_hz": candidate["frequency_hz"] - carrier_freq_reference,
                "relative_dbc": candidate["amplitude_dbm"] - carrier_reference,
                "rbw_hz": candidate["rbw_hz"],
                "span_hz": candidate["span_hz"],
                "noise_floor_dbm": candidate.get("noise_floor_dbm"),
                "is_harmonic": is_harmonic,
                "harmonic_order": harmonic_order,
                "status": status,
                "validation_notes": json.dumps(validation_notes, ensure_ascii=False),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.add_result(result)

        print(
            f"载波 {carrier_frequency / 1e6:.3f} MHz: "
            f"输出 {confirmed_count} 条已确认杂散，"
            f"共 {len(self.test_results)} 条记录"
        )

        if not keep_output:
            signal_generator.enable_output(False)
            self._output_enabled = False
            self._ambient_spurs = []
