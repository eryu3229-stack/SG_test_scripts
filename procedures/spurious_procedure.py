import time
import math
import numpy as np
from datetime import datetime
from base_test_procedure import BaseTestProcedure


def _snap_attenuation(value, step_db):
    """把衰减值对齐到仪器的衰减网格（**向上取整**）。

    仪器的输入衰减只能按固定步进设置（本机 N9030B 为 2 dB/步），网格外的值
    （如 25、35）会被固件拒绝或自行取整 → 记录值 ≠ 生效值。
    向上取整是安全方向：多衰减只会抬高底噪，不会减少对混频器的保护。

    Args:
        value: 期望衰减 (dB)
        step_db: 网格步进 (dB)；0/None 表示不约束

    Returns:
        (对齐后的衰减, 是否被调整)
    """
    if not step_db or value is None:
        return value, False
    snapped = math.ceil(float(value) / float(step_db) - 1e-9) * float(step_db)
    return snapped, abs(snapped - float(value)) > 1e-9


class SpuriousProcedure(BaseTestProcedure):
    """分段扫描 + Trace 全量峰值检测 + 候选验证的杂散测量流程

    设计目标：速度不是核心，全面掌握频谱杂散情况。
    - 近载波：10 MHz / 100 MHz SPAN，RBW 从 100 Hz 起
    - 远载波：1 GHz 分段，范围受 frequency bounds 裁剪
    - 谐波：**不测绘、不输出**。落入任一阶谐波频率窗的候选直接剔除
    - 候选：全部列出，不做 next-peak 依赖
    - 验证：衰减器阶跃、RBW 缩放、重复性、源开关环境扫描
    - 灵敏度：显示底噪由**输入衰减**主导（逐 dB 抬高），故衰减按"混频器电平 =
      载波 − 衰减"取最小值；选峰门限仍用 POS/MAXH 迹线中位数（与 POS 选峰自洽），
      另用独立 AVER 迹线测**真实平均底噪**（dBm 与 dBm/Hz）供结论引用。
    - 每段采集前用 WRITE 覆盖旧迹线，避免连续扫描 + MAXHold 把上一段数据带过来。
    - 下发后读回校验 RBW/VBW/点数/参考电平/输入衰减，设置被静默拒绝时告警。
    """

    TEST_TYPE = "spurious"
    # 列顺序原则：**结论优先**——杂散位置(spurious_freq_hz)、抑制度(delta_db, dBc)
    # 与判定(status)紧跟运行标识，打开 CSV 无需横向滚动即可读到结论；
    # 采集条件与验证量属追溯信息，统一后置。
    FIELDNAMES = [
        # A 区：运行标识 + 杂散结论（位置 → 抑制度 → 判定）
        "run_id", "test_type",
        "spurious_freq_hz",          # 杂散位置（绝对频率）
        "delta_db", "delta_ref",     # 抑制度 dBc（相对载波实测功率）
        "status",                    # 判定（OK/SUSPECT/SKIP）
        "measured_power_dbm",        # 杂散绝对电平
        "segment_name",              # 所属扫描段
        # B 区：激励条件（该杂散对应的载波）
        "carrier_hz", "set_power_dbm",
        # C 区：频谱仪采集条件（精测条件）
        "sa_ref_level_dbm", "sa_input_att_db", "sa_att_mode",
        "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz",
        "sa_noise_floor_dbm", "sa_noise_floor_avg_dbm", "sa_noise_floor_dbm_per_hz",
        # D 区：验证量（结论可信度）
        "att_dbc_range_db", "rbw_scaling_range_db", "stability_std_db",
        # 说明与时间
        "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self._output_enabled = False
        self._ambient_spurs = []  # 源 OFF 时测到的固定频点

    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.run_id = self.derive_run_id(csv_path)
        self.csv_streamer = CsvStreamer(csv_path, self.FIELDNAMES)

    def finish_csv(self):
        if self.csv_streamer:
            self.csv_streamer.close()
            print(f"CSV流式存储已关闭: {self.csv_streamer.filepath}")

    def sort_results(self):
        self.test_results.sort(
            key=lambda row: (row["carrier_hz"], row["segment_name"], row["spurious_freq_hz"])
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
        preamp=False,
        preamp_band=None,
        sweep_points=None,
    ):
        spectrum_analyzer.set_center_frequency(center_frequency)
        spectrum_analyzer.set_span(span)
        spectrum_analyzer.set_rbw(rbw)
        spectrum_analyzer.set_vbw(vbw)
        # 预放先于衰减/参考电平：它会把混频器电平抬高预放增益，余量要按含预放的链路定
        if hasattr(spectrum_analyzer, "set_preamp"):
            spectrum_analyzer.set_preamp(bool(preamp), preamp_band)
        spectrum_analyzer.set_attenuation(attenuation)
        # 显式断开衰减自动耦合：否则改参考电平时仪器可能按 Auto 规则回写衰减，
        # 使"我们以为下发的衰减"与实际生效值不一致（读回校验会暴露这种不一致）
        if hasattr(spectrum_analyzer, "set_attenuation_auto"):
            spectrum_analyzer.set_attenuation_auto(False)
        spectrum_analyzer.set_reference_level(reference_level)
        # 不设点数则沿用仪器 Preset 默认（是德 X 系列 = 1001，会造成粗频率量化，
        # 因扫时由 span/RBW 决定，显式拉高点数在扫频模式下几乎不增加耗时）
        if sweep_points is not None:
            spectrum_analyzer.set_sweep_points(sweep_points)
        if hasattr(spectrum_analyzer, "set_trace_mode"):
            spectrum_analyzer.set_trace_mode(trace_mode)
        if hasattr(spectrum_analyzer, "set_detector"):
            spectrum_analyzer.set_detector(detector)
        if hasattr(spectrum_analyzer, "set_input_coupling"):
            spectrum_analyzer.set_input_coupling(coupling)

    @staticmethod
    def _resolve_segment_settings(segment_config, config):
        """合并「段级覆盖」与「全局缺省」，得到实际下发的采集条件。

        段级可选键（值为 None 表示沿用全局）：
            input_att_db / ref_level_dbm / preamp / preamp_band / sweep_points
        """
        def _pick(key, default):
            value = segment_config.get(key)
            return default if value is None else value

        att_raw = _pick("input_att_db", config.get("attenuation_db", 30))
        att, adjusted = _snap_attenuation(att_raw, config.get("attenuation_step_db"))
        if adjusted:
            print(f"    衰减 {att_raw:g} dB 不在 {config.get('attenuation_step_db'):g} dB 网格上"
                  f" → 取 {att:g} dB")
        return {
            "ref_level_dbm": _pick("ref_level_dbm", config.get("reference_level_dbm", 10)),
            "input_att_db": att,
            "preamp": bool(_pick("preamp", config.get("preamp", False))),
            "preamp_band": _pick("preamp_band", config.get("preamp_band")),
            "sweep_points": segment_config.get("sweep_points"),
        }

    def _verify_settings(self, spectrum_analyzer, expected, segment_name):
        """读回关键设置并与下发值比对；不一致只告警、不中断。

        存在的意义：控制台打印的一直是**请求值**。若仪器静默拒绝（耦合冲突、
        取值越界、命令路径不对），此前完全无从发现，结论就成了"看起来对"。

        Returns:
            读回的设置字典（读不到的项为 None）
        """
        handler = getattr(spectrum_analyzer, "read_key_settings", None)
        if handler is None:
            print(f"  {segment_name}: 当前仪器对象不支持读回校验，已跳过")
            return {}
        actual = handler() or {}
        details = []
        problems = []
        for key, want in expected.items():
            got = actual.get(key)
            if got is None:
                details.append(f"{key}=读取失败")
                problems.append(f"{key}(下发 {want:g}) 无法读回")
                continue
            details.append(f"{key}={got:g}")
            if key == "sweep_points":
                if int(round(got)) != int(round(want)):
                    problems.append(f"{key} 读回 {got:g} ≠ 下发 {want:g}")
            elif abs(got - want) > max(1e-9, abs(want) * 1e-3):
                problems.append(f"{key} 读回 {got:g} ≠ 下发 {want:g}")
        # 额外读回项（预放状态 / Y 轴刻度等）不参与判定，但**必须打印**：
        # 它们是解释"实测底噪比模型好 10 dB""读数是否贴显示下限"的唯一证据。
        # 注意：下面以前是按 expected 的键遍历，这些额外项会被静默丢掉。
        extras = {k: v for k, v in actual.items()
                  if k not in expected and isinstance(v, (int, float))}
        extra_text = (" | 状态项 [" + ", ".join(f"{k}={v:g}" for k, v in extras.items()) + "]"
                      if extras else "")
        print(f"  {segment_name}: 读回 [{', '.join(details)}]{extra_text}")
        if problems:
            print(f"  {segment_name}: ⚠ 设置校验不一致 -> " + "；".join(problems))
        return actual

    NOISE_FLOOR_PERCENTILE = 20

    @classmethod
    def _estimate_noise_floor(cls, trace, percentile=None):
        """门限基准：迹线的**低分位**（默认 20 分位）—— 不是可引用的灵敏度结论。

        为什么不用中位数：中位数会被**占比大的宽带分量 / 大量杂散峰**整体抬高，
        门限随之上移 → 弱杂散被自遮蔽（强峰把弱峰藏起来）。
        20 分位在纯噪声下只比中位数低约 1~2 dB（被 6 dB 门限余量覆盖），
        但在被污染时可以穿过污染层、落在真实噪声上。

        它与 POS 选峰自洽（都基于峰值噪声包络），专用于 `_find_candidates`
        的入围高度；可对外引用的真实平均底噪见 `_measure_average_noise_floor`。
        """
        if not trace:
            return None
        pct = cls.NOISE_FLOOR_PERCENTILE if percentile is None else float(percentile)
        return float(np.percentile(np.asarray(trace, dtype=float), pct))

    @staticmethod
    def _detect_floor_clipping(trace, fraction_limit=0.10, band_db=0.5):
        """判断迹线是否在显示下限触底（底噪被显示范围截断）。

        参考电平与纵向刻度决定屏幕下限（如 10 dBm + 10 dB/div × 10 div = −90 dBm），
        迹线数据会被截在屏幕内。触底时"底噪中位数"等于屏幕下限而非真实噪声，
        门限与灵敏度结论都会失真 —— 这是最容易被误当成"仪器灵敏度差"的坑。

        判据：正常噪声迹线是散开的，只有被下限截断才会形成平台 —— 若超过
        `fraction_limit` 比例的采样点挤在"迹线最小值 + band_db"以内即判触底。

        Returns:
            bool
        """
        if not trace:
            return False
        values = np.asarray(trace, dtype=float)
        if values.size < 10:
            return False
        lowest = float(np.min(values))
        pinned = float(np.mean(values <= lowest + band_db))
        return pinned > fraction_limit

    def _measure_average_noise_floor(self, spectrum_analyzer, span, rbw, ref_level, config):
        """用独立 AVER 检波迹线测「真实平均底噪」，并归一化到 1 Hz。

        为什么必须单独测：POS 检波显示的是每个显示点内的噪声**峰值包络**，
        再叠加 MAXHold 跨扫描取最大，中位数会比平均底噪高约 10 dB。拿它当灵敏度
        结论会低估灵敏度，而且随检波器/扫描次数漂移。

        Args:
            span / rbw: 当前精测跨度与分辨率带宽（rbw 用于 dBm/Hz 归一）
            ref_level: 本段正常参考电平，测完恢复

        Returns:
            (avg_floor_dbm, avg_floor_dbm_per_hz)；关闭或失败时返回 (None, None)
        """
        report = config.get("noise_floor_report", {})
        if not report.get("enable", True):
            return None, None

        low_ref = report.get("ref_level_dbm")
        try:
            spectrum_analyzer.set_detector(report.get("detector", "AVER"))
            spectrum_analyzer.set_trace_mode("WRITE")
            # 临时压低参考电平，把显示下限往下推：平均底噪比 POS/MAXH 迹线的中位数
            # 低约 10 dB，沿用段内的参考电平会掉到屏幕外，读到的只是显示下限。
            # 此时跨度仅 1 MHz 且中心在候选杂散上，载波在跨度之外被 RBW 滤掉，
            # 带内只有噪声，不会 IF/ADC 过载；衰减已显式置为手动，不会被改回。
            if low_ref is not None:
                spectrum_analyzer.set_reference_level(low_ref)
            completed = spectrum_analyzer.accumulate_sweeps(
                report.get("sweep_count", 1), span_hz=span
            )
            if not completed:
                print("  平均底噪扫描同步失败，该口径留空")
                return None, None
            trace = spectrum_analyzer.get_trace(1)
        except Exception as e:
            print(f"  平均底噪测量失败: {e}")
            return None, None
        finally:
            if low_ref is not None:
                spectrum_analyzer.set_reference_level(ref_level)

        avg_floor = self._estimate_noise_floor(trace)
        if avg_floor is None:
            return None, None
        if not report.get("normalize_to_hz", True) or not rbw or rbw <= 0:
            return avg_floor, None
        # 噪声底噪随分辨率带宽变化：归一化到 1 Hz 后各段、各 RBW 才可比
        return avg_floor, avg_floor - 10.0 * np.log10(rbw)

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

    def _find_candidates_robust(self, frequencies, powers, peak_config, iterations=3):
        """选峰 + 迭代掩膜，抵抗"强峰污染门限基准"。

        门限基准取迹线中位数，而中位数会被**占比大的信号/宽带分量**整体抬高：
        强峰、相噪裙边、调制裙边一旦占了足够多的 bin，门限随之上移，弱杂散就被
        自遮蔽掉（强峰把弱峰藏起来）。这里在选峰后把已选中的峰（±mask_bins）
        掩掉再重算底噪，迭代到稳定为止 —— 纯软件处理，不额外占用仪器时间。

        Args:
            frequencies / powers / peak_config: 同 `_find_candidates`
            iterations: 迭代上限（2~3 轮即收敛）

        Returns:
            (最终门限基准 dBm, 候选列表)
        """
        if not powers or len(frequencies) < 2:
            return None, []

        freq_step = abs(frequencies[1] - frequencies[0]) or 1.0
        mask_bins = peak_config.get("threshold_mask_bins")
        if mask_bins is None:
            # 未显式配置时：按"候选最小间隔"换算成 bin 数
            mask_bins = max(1, int(round(peak_config.get("min_peak_distance_hz", 1e3) / freq_step)))
        mask_bins = max(1, int(mask_bins))

        percentile = peak_config.get("noise_floor_percentile")
        floor = self._estimate_noise_floor(powers, percentile)
        candidates = []
        for _ in range(max(1, iterations)):
            candidates = self._find_candidates(frequencies, powers, floor, peak_config)
            if not candidates:
                break
            masked = self._masked_noise_floor(
                powers, [c["index"] for c in candidates], mask_bins, percentile)
            if masked is None or abs(masked - floor) < 0.05:
                break
            floor = masked
        return floor, candidates

    @staticmethod
    def _masked_noise_floor(powers, peak_indices, mask_bins, percentile=None):
        """掩掉峰位（±mask_bins）后取剩余点的低分位；剩余点太少则返回 None。"""
        values = np.asarray(powers, dtype=float)
        keep = np.ones(values.size, dtype=bool)
        for index in peak_indices:
            low = max(0, int(index) - mask_bins)
            high = min(values.size, int(index) + mask_bins + 1)
            keep[low:high] = False
        if keep.sum() < max(10, values.size * 0.1):
            return None
        pct = SpuriousProcedure.NOISE_FLOOR_PERCENTILE if percentile is None else float(percentile)
        return float(np.percentile(values[keep], pct))

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
            config.get("attenuation_db", 25),
            "WRITE",
            "POS",
            config.get("input_coupling", "DC"),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        if not spectrum_analyzer.accumulate_sweeps(1, span_hz=span):
            print("载波扫描同步失败，跳过该载波")
            return None, carrier_frequency
        spectrum_analyzer.peak_search()

        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - carrier_frequency) > span / 2.0:
            spectrum_analyzer.set_marker_frequency(1, carrier_frequency)
            peak_frequency = carrier_frequency

        min_frequency_hz = config.get("min_frequency_hz", 0.0)
        measurements = []
        for _ in range(5):
            # 每次读数前重新采集，保证 5 个样本来自 5 次独立扫描
            if not self._acquire(spectrum_analyzer):
                continue
            power = self._read_marker(spectrum_analyzer, 1)
            if self._is_valid_measurement(peak_frequency, power, min_frequency_hz):
                measurements.append(power)

        if measurements:
            return float(np.mean(measurements)), peak_frequency
        print(f"  载波 {carrier_frequency / 1e6:.3f} MHz 功率测量无效")
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

        # 精测必须沿用**本段实际下发**的衰减 / 参考电平：段级可覆盖全局值，若这里
        # 回落到全局值，精测幅度与段扫幅度就不在同一采集条件下，dBc 不可比。
        ref_level = candidate.get("ref_level_dbm", config.get("reference_level_dbm", 10))
        attenuation = candidate.get("input_att_db", config.get("attenuation_db", 25))

        self._configure_sa(
            spectrum_analyzer,
            candidate["frequency_hz"],
            span,
            rbw,
            vbw,
            ref_level,
            attenuation,
            trace_mode,
            detector,
            config.get("input_coupling", "DC"),
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))
        if not spectrum_analyzer.accumulate_sweeps(sweep_count, span_hz=span):
            print(f"候选 {candidate['frequency_hz']/1e6:.3f} MHz 精测扫描同步失败")
            return None
        spectrum_analyzer.peak_search()
        peak_frequency = spectrum_analyzer.get_marker_frequency(1)
        if peak_frequency is None or abs(peak_frequency - candidate["frequency_hz"]) > span / 2.0:
            spectrum_analyzer.set_marker_frequency(1, candidate["frequency_hz"])
            peak_frequency = candidate["frequency_hz"]

        measurements = []
        for _ in range(max(1, average_count)):
            # 每次读数前重新采集：仪器停在单次态时 trace 是冻结的，
            # 不重扫等于 N 次读同一个数（std 恒为 0，重复性判据失效）
            if not self._acquire(spectrum_analyzer):
                continue
            power = self._read_marker(spectrum_analyzer, 1)
            if power is not None:
                measurements.append(power)

        if not measurements:
            return None

        mean_power = float(np.mean(measurements))
        min_frequency_hz = config.get("min_frequency_hz", 0.0)
        if not self._is_valid_measurement(peak_frequency, mean_power, min_frequency_hz):
            print(
                f"  精测结果无效，跳过: "
                f"freq={peak_frequency / 1e6:.3f} MHz, amp={mean_power:.2f} dBm"
            )
            return None

        # 门限基准口径（POS/WRITE 迹线中位数）—— 与 POS 选峰自洽，用于判断该候选
        # 是否仍高于本地噪声；不代表灵敏度。
        trace = spectrum_analyzer.get_trace(1)
        noise_floor = self._estimate_noise_floor(
            trace, config.get("peak_detection", {}).get("noise_floor_percentile"))
        if noise_floor is None:
            noise_floor = candidate.get("noise_floor_dbm")

        # 真实平均底噪口径（独立 AVER 迹线）—— 这才是可以对外引用的灵敏度证据
        avg_floor, avg_floor_per_hz = self._measure_average_noise_floor(
            spectrum_analyzer, span, rbw, ref_level, config
        )

        return {
            "frequency_hz": peak_frequency,
            "amplitude_dbm": mean_power,
            "std_db": float(np.std(measurements)),
            "rbw_hz": rbw,
            "span_hz": span,
            "noise_floor_dbm": noise_floor,
            "avg_noise_floor_dbm": avg_floor,
            "avg_noise_floor_dbm_per_hz": avg_floor_per_hz,
            "input_att_db": attenuation,
            "ref_level_dbm": ref_level,
        }

    # ------------------------------------------------------------------
    # 谐波剔除
    # ------------------------------------------------------------------
    def _is_harmonic_spur(self, frequency, carrier_frequency, exclusion_config):
        """判断该频点是否落在谐波频率窗内（落在窗内 → 剔除，不精测也不输出）。

        杂散测试中不可避免会遇到谐波分量，但谐波不是本测试的关心对象，
        故在候选进入精测前就将其剔除。
        """
        if not frequency or not carrier_frequency or carrier_frequency <= 0:
            return False
        tolerance = exclusion_config.get("tolerance_hz", 5e5)
        for order in exclusion_config.get("orders", [2, 3, 4, 5, 6]):
            if abs(frequency - order * carrier_frequency) <= tolerance:
                return True
        return False

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
        """验证候选真伪。

        Returns:
            (status, flat, note)
            status ∈ {"OK", "SUSPECT", "SKIP"}
            flat: 已拍平的验证指标（直接作为输出列）
            note: 中文说明（多个异常用「；」连接）
        """
        validation = config.get("validation", {})
        if not validation.get("enable", True):
            return "SKIP", {}, "验证已关闭"

        flat = {}
        flags = []

        # 1. 重复性（读取次数由 refine_config.average_count 决定，此处只判标准差）
        stability_limit = validation.get("stability_limit_db", 1.0)
        if refined.get("std_db") is not None and refined["std_db"] > stability_limit:
            flags.append("重复性差")
            flat["stability_std_db"] = round(refined["std_db"], 3)

        # 2. 衰减器阶跃测试：dBc 应基本不变
        if validation.get("attenuator_step_check", True):
            att_base = refined.get("input_att_db", config.get("attenuation_db", 30))
            att_base, _ = _snap_attenuation(att_base, config.get("attenuation_step_db"))
            att_step_db = config.get("attenuation_step_db")
            att_steps = validation.get("attenuator_steps", [0, 6])
            dbc_tolerance = validation.get("attenuator_dbc_tolerance_db", 2.0)
            att_settle_s = validation.get("attenuator_settle_s", 0.2)
            dbc_values = []
            for step in att_steps:
                att_target, adjusted = _snap_attenuation(att_base + step, att_step_db)
                if adjusted:
                    print(f"    衰减阶跃 {att_base + step:g} dB 不在网格上 → 取 {att_target:g} dB")
                spectrum_analyzer.set_attenuation(att_target)
                time.sleep(att_settle_s)
                # 必须重新采集：仪器停在单次态（精测结束时 CONT OFF）时，
                # 改衰减**不会**自动重扫，直接读 marker 得到的是上一条冻结迹线的值
                # → dBc 变化恒为 0，这项验证会永远通过（假验证）。
                if not self._acquire(spectrum_analyzer):
                    print(f"    衰减阶跃 {att_target:g} dB: 采集失败，该点不参与判定")
                    continue
                power = self._read_marker(spectrum_analyzer, 1)
                if power is not None and carrier_power is not None:
                    dbc_values.append(power - carrier_power)
            spectrum_analyzer.set_attenuation(att_base)
            if len(dbc_values) >= 2:
                dbc_range = max(dbc_values) - min(dbc_values)
                flat["att_dbc_range_db"] = round(dbc_range, 2)
                if dbc_range > dbc_tolerance:
                    flags.append("衰减器响应异常")
            elif dbc_values:
                print("    衰减阶跃有效读数不足 2 个，本项不判定")

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
                if not spectrum_analyzer.accumulate_sweeps(1, span_hz=refined.get("span_hz", 1e6)):
                    print(f"RBW缩放测试扫描同步失败，ratio={ratio}")
                    continue
                power = spectrum_analyzer.measure_marker_power(1)
                if power is not None:
                    amps.append(power)
            spectrum_analyzer.set_rbw(base_rbw)
            spectrum_analyzer.set_vbw(base_rbw * 3)
            if amps:
                amp_range = max(amps) - min(amps)
                flat["rbw_scaling_range_db"] = round(amp_range, 2)
                if amp_range > amp_tolerance:
                    flags.append("RBW缩放响应异常")

        # 4. 环境杂散比对：候选频率是否在源 OFF 时也存在
        if self._ambient_spurs:
            freq_match = any(
                abs(refined["frequency_hz"] - amb["frequency"]) <= validation.get("ambient_freq_tolerance_hz", 100e3)
                for amb in self._ambient_spurs
            )
            if freq_match:
                flags.append("源OFF仍存在")

        if not flags:
            return "OK", flat, ""
        return "SUSPECT", flat, "；".join(flags)

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
                config.get("attenuation_db", 25),
                segment.get("trace_mode", "MAXH"),
                segment.get("detector", "POS"),
                config.get("input_coupling", "DC"),
            )
            time.sleep(config.get("sa_settling_time_s", 0.5))
            if not spectrum_analyzer.accumulate_sweeps(segment.get("sweep_count", 5), span_hz=span):
                print(f"环境扫描 segment {segment.get('name', 'ambient')} 同步失败，跳过")
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
        settings = self._resolve_segment_settings(segment_config, config)

        print(
            f"    {segment_name}: {center_frequency / 1e6:.0f} MHz / "
            f"{span / 1e6:.0f} MHz / RBW {rbw:.0f} Hz / "
            f"衰减 {settings['input_att_db']:g} dB / "
            f"参考 {settings['ref_level_dbm']:g} dBm / sweeps {sweep_count}"
            + (" / 预放 ON" if settings["preamp"] else "")
        )

        self._configure_sa(
            spectrum_analyzer,
            center_frequency,
            span,
            rbw,
            vbw,
            settings["ref_level_dbm"],
            settings["input_att_db"],
            trace_mode,
            detector,
            config.get("input_coupling", "DC"),
            preamp=settings["preamp"],
            preamp_band=settings["preamp_band"],
            sweep_points=settings["sweep_points"],
        )
        time.sleep(config.get("sa_settling_time_s", 0.5))

        # 读回校验：控制台此前打的全是"请求值"，仪器静默拒绝时无从发现
        expected = {
            "rbw_hz": rbw,
            "vbw_hz": vbw,
            "ref_level_dbm": settings["ref_level_dbm"],
            "input_att_db": settings["input_att_db"],
        }
        if settings["sweep_points"] is not None:
            expected["sweep_points"] = settings["sweep_points"]
        self._verify_settings(spectrum_analyzer, expected, segment_name)

        # 迹线初始化（防御性）：切段只改 SPAN / 中心频率 / RBW，代码无法确认仪器
        # 是否顺带清掉旧迹线；而 MAXHold 只升不降，一旦旧迹线被保留（例如近段含
        # +10 dBm 载波的那几个点），就会被一路带进本段并保留下来。先用 WRITE 覆盖
        # 一次再切回 MAXHold，把"本段底噪是否受上一段污染"这个不确定性彻底消掉。
        if config.get("trace_init", {}).get("prime_with_write", True):
            spectrum_analyzer.set_trace_mode("WRITE")
            if not spectrum_analyzer.accumulate_sweeps(1, span_hz=span):
                print(f"  {segment_name}: 迹线初始化扫描失败（继续，但可能含旧迹线残留）")
            spectrum_analyzer.set_trace_mode(trace_mode)

        if not spectrum_analyzer.accumulate_sweeps(sweep_count, span_hz=span):
            print(f"  {segment_name}: 扫描同步失败，跳过该段")
            return []

        trace = spectrum_analyzer.get_trace(1)
        if not trace:
            print(f"  {segment_name}: 未读取到 trace")
            return []

        frequencies = self._trace_frequencies(center_frequency, span, len(trace))
        floor_median = float(np.median(np.asarray(trace, dtype=float)))
        noise_percentile = config.get("peak_detection", {}).get(
            "noise_floor_percentile", self.NOISE_FLOOR_PERCENTILE)
        noise_floor, candidates = self._find_candidates_robust(
            frequencies,
            trace,
            config.get("peak_detection", {}),
        )
        # 污染告警门限：纯噪声下"中位数 − 低分位"本来就有天然差值，不能一有差就报污染。
        # 蒙特卡洛（5 分辨率单元/bin + MAXH 3 次）= 1.3 dB；老配置 100 单元/bin = 0.65 dB。
        # 取 3 dB（天然值 + 余量）才说明中位数确实被强峰/宽带分量抬起。
        if (noise_floor is not None
                and (floor_median - noise_floor) >= 3.0):
            print(f"  {segment_name}: 门限基准 {floor_median:.1f}(中位数) → {noise_floor:.1f} dBm"
                  f"（{noise_percentile:g}分位/掩膜后，差 {floor_median - noise_floor:.1f} dB，"
                  f"天然差值约 1.3 dB）：中位数疑似被强峰/宽带分量污染")
        # 这一行是**门限基准**（POS/MAXH 迹线中位数 = 峰值噪声包络），不是灵敏度结论。
        # 可对外引用的真实平均底噪来自精测阶段的 AVER 迹线
        # （每行 sa_noise_floor_avg_dbm / sa_noise_floor_dbm_per_hz）。
        print(
            f"  {segment_name}: 门限基准(POS/MAXH 低分位/掩膜后) {noise_floor:.1f} dBm, "
            f"候选 {len(candidates)} 个"
        )
        if self._detect_floor_clipping(trace):
            print(
                f"  {segment_name}: ⚠ 底噪疑似被显示范围截断（迹线触底）—— "
                f"该段的门限与灵敏度读数不可用，请降低参考电平或加大输入衰减"
            )

        refined_list = []
        # 统一噪声门限：高于本地噪声底该值即视为潜在杂散（与段内选峰同源参数）
        noise_margin = config.get("peak_detection", {}).get("noise_margin_db", 6.0)
        # 事前保护带：按候选频率剪枝，省下精测时间。
        # 事后按实测峰频的终判见主循环中的 min_spur_offset_hz。
        guard = config.get("carrier_guard_hz", 10e3)
        exclusion = config.get("harmonic_exclusion", {})
        for candidate in candidates:
            # 把本段**实际下发**的采集条件带给精测：段级可覆盖全局值，若精测回落到
            # 全局值，段扫幅度与精测幅度就不在同一条件下，dBc 不可比。
            candidate["input_att_db"] = settings["input_att_db"]
            candidate["ref_level_dbm"] = settings["ref_level_dbm"]

            # 跳过载波保护带内
            if abs(candidate["frequency_hz"] - carrier_frequency) < guard:
                continue

            # 谐波分量剔除：谐波不是本测试关心对象，不精测、不输出
            if self._is_harmonic_spur(
                candidate["frequency_hz"], carrier_frequency, exclusion
            ):
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
            if refined["noise_floor_dbm"] is not None and refined["amplitude_dbm"] < refined["noise_floor_dbm"] + noise_margin:
                continue

            # 精测后按**实测峰频**再判一次保护带：
            # 粗扫的频率分辨率 ≈ span/trace_points（1 GHz span / 1001 点 ≈ 1 MHz），
            # 远宽于 carrier_guard_hz(10 kHz)，所以"载波所在 bin"在精测前
            # 根本不可能被上面的 guard 剪掉 —— 它会一路走到这里才被主循环丢弃。
            # 若不在此处剔除，它会占掉一个「每段 top-N」名额，使该段白白少报一个
            # 真实杂散。（按定义，载波 ±carrier_guard_hz 内本就不算杂散。）
            if abs(refined["frequency_hz"] - carrier_frequency) < guard:
                continue

            refined_list.append(refined)

        # 每段只保留幅度最高的 N 个候选 —— **按段**截断。
        # 旧实现把这个参数用在全局排序上（sort 全部候选再取前 N），等价于
        # "所有段合起来只留 N 个"；覆盖范围一旦放宽到全频段，远段的真实杂散
        # 会被近段（绝对幅度天然更高）整体挤掉。
        max_per_segment = config.get("output", {}).get("max_candidates_per_segment")
        if max_per_segment is not None and len(refined_list) > max_per_segment:
            refined_list.sort(key=lambda c: c["amplitude_dbm"], reverse=True)
            dropped = len(refined_list) - max_per_segment
            print(
                f"  {segment_name}: 候选 {len(refined_list)} 个 → "
                f"按段保留 top-{max_per_segment}（丢弃 {dropped} 个）"
            )
            refined_list = refined_list[:max_per_segment]

        return refined_list

    # ------------------------------------------------------------------
    # 远载波 1 GHz 分段生成
    # ------------------------------------------------------------------
    @staticmethod
    def _is_valid_measurement(frequency_hz, power_dbm, min_frequency_hz=0.0):
        """判断频点/功率是否为有效测量值

        R&S 仪器在设置无效中心频率时会返回 9.91e+37 等哨兵值；
        同时频率必须为正，功率必须在合理范围内。
        """
        if frequency_hz is None or power_dbm is None:
            return False
        try:
            freq = float(frequency_hz)
            power = float(power_dbm)
        except (TypeError, ValueError):
            return False
        if not np.isfinite(freq) or freq <= 0:
            return False
        if not np.isfinite(power) or abs(power) > 200.0:
            return False
        if freq < min_frequency_hz:
            return False
        return True

    def _build_far_segment_centers(
        self, carrier_frequency, coverage, span, min_frequency_hz=0.0,
        max_frequency_hz=None,
    ):
        """以载波为中心，向两侧各扩展 coverage/2 的范围，按 span 分段。

        边界处理针对**整段的上下边缘**，而不是只看段中心：
        center > 0 只等价于"下边缘 > -span/2"，中心落在 (0, span/2) 的段
        仍会带着负频率下边缘下扫；同理高端段可能越过 max_frequency_hz。

        越界段采用**向内夹逼**而非整段丢弃：把段中心平移最小距离，
        使其刚好贴住可用范围。这样 1 GHz 载波的下半段仍能覆盖到
        9 kHz~1 GHz，而不是被整个丢掉；只有"可用范围比一段还窄"或
        "夹逼后与上一段重合"时才真正跳过。

        Args:
            carrier_frequency: 载波频率 (Hz)
            coverage: 远载波总覆盖宽度 (Hz)，以 CF 为中心
            span: 每段 SPAN (Hz)
            min_frequency_hz: 仪器允许的最小频率 (Hz)
            max_frequency_hz: 仪器允许的最大频率 (Hz)，None 表示不设上限

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
            adjusted = center
            if adjusted - half_span < min_frequency_hz:
                adjusted = min_frequency_hz + half_span
            if max_frequency_hz is not None and adjusted + half_span > max_frequency_hz:
                adjusted = max_frequency_hz - half_span

            too_narrow = adjusted - half_span < min_frequency_hz
            over_top = (
                max_frequency_hz is not None
                and adjusted + half_span > max_frequency_hz
            )
            duplicate = bool(centers) and abs(adjusted - centers[-1]) < span * 0.5

            if too_narrow or over_top:
                upper = "inf" if max_frequency_hz is None else f"{max_frequency_hz / 1e6:.3f} MHz"
                print(
                    f"  跳过越界远段: 中心 {center / 1e6:.3f} MHz 放不进 "
                    f"[{min_frequency_hz / 1e6:.3f} MHz, {upper}]"
                )
            elif duplicate:
                print(f"  跳过重叠远段: 中心 {adjusted / 1e6:.3f} MHz 与上一段重合")
            else:
                if abs(adjusted - center) > 1.0:
                    print(
                        f"  段中心内移贴边: {center / 1e6:.3f} -> "
                        f"{adjusted / 1e6:.3f} MHz"
                    )
                centers.append(adjusted)
            center += span
        return centers

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
                min_frequency_hz=config.get("min_frequency_hz", 0.0),
                max_frequency_hz=config.get("max_frequency_hz"),
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

        # 5. 去重、验证、输出
        # 谐波分量已在 _scan_segment 选段阶段剔除，此处不再有谐波条目。
        dedup_tolerance = config.get("peak_detection", {}).get("min_peak_distance_hz", 1e3)
        all_candidates = self._deduplicate_candidates(all_candidates, dedup_tolerance)

        output_config = config.get("output", {})
        include_unconfirmed = output_config.get("include_unconfirmed", True)
        # 候选上限已在 _scan_segment 内按**段**截断
        # （见 output.max_candidates_per_segment），此处不再做全局截断 ——
        # 全局 top-N 会让远段候选被近段（绝对幅度更高）整体挤掉。

        # 频谱仪采集条件（B 区）：逐行取候选身上记录的**实际下发值**。
        # 段级可覆盖全局值（见 _resolve_segment_settings），故不能只写全局缺省，
        # 否则一旦某段单独改了衰减，输出列会与真实采集条件不符。
        refine = config.get("refine_config", {})
        sa_ref_level_default = config.get("reference_level_dbm", 10)
        sa_att_default = config.get("attenuation_db", 25)

        print(f"  待验证候选: {len(all_candidates)} 个")
        confirmed_count = 0
        # 事后保护带终判：此处用的是**精测后的实测峰频**（candidate["frequency_hz"]
        # 已被 _refine_candidate 替换为 peak_frequency），用于兜住"候选在精测窗口内
        # 迁移到载波附近"的情况。事前按候选频率的剪枝见 _scan_segment。
        min_offset = config.get("min_spur_offset_hz", 10e3)
        for idx, candidate in enumerate(all_candidates, 1):
            offset = candidate["frequency_hz"] - carrier_freq_reference
            if abs(offset) < min_offset:
                print(
                    f"  验证 [{idx}/{len(all_candidates)}] "
                    f"{candidate['frequency_hz'] / 1e6:.3f} MHz - "
                    f"偏移 {abs(offset):.0f} Hz < min_spur_offset_hz，跳过"
                )
                continue
            print(f"  验证 [{idx}/{len(all_candidates)}] {candidate['frequency_hz'] / 1e6:.3f} MHz")

            # 真伪验证：返回 (status, 拍平指标, 中文说明)
            # status ∈ {"OK", "SUSPECT", "SKIP"}
            status, flat, note = self._validate_candidate(
                spectrum_analyzer,
                signal_generator,
                candidate,
                carrier_freq_reference,
                carrier_reference,
                config,
            )

            if status == "OK":
                confirmed_count += 1
            elif not include_unconfirmed:
                continue

            result = {
                # A 区：运行标识 + 杂散结论（位置 → 抑制度 → 判定）
                "run_id": getattr(self, "run_id", ""),
                "test_type": self.TEST_TYPE,
                "spurious_freq_hz": candidate["frequency_hz"],
                # 杂散的偏差以载波实测功率为基准（dBc）
                "delta_db": round(candidate["amplitude_dbm"] - carrier_reference, 3),
                "delta_ref": "carrier",
                "status": status,
                "measured_power_dbm": candidate["amplitude_dbm"],
                "segment_name": candidate.get("segment_name", "unknown"),
                # B 区：激励条件
                "carrier_hz": carrier_freq_reference,
                "set_power_dbm": carrier_power,
                # C 区：频谱仪采集条件（精测条件）
                "sa_ref_level_dbm": candidate.get("ref_level_dbm", sa_ref_level_default),
                "sa_input_att_db": candidate.get("input_att_db", sa_att_default),
                "sa_att_mode": "manual",
                "sa_span_hz": candidate.get("span_hz"),
                "sa_rbw_hz": candidate.get("rbw_hz"),
                "sa_vbw_hz": refine.get("vbw_hz", 300),
                # 门限基准口径：POS/MAXH 迹线中位数（与 POS 选峰自洽），非灵敏度结论
                "sa_noise_floor_dbm": candidate.get("noise_floor_dbm"),
                # 真实平均底噪口径：独立 AVER 迹线；dBm/Hz 已按 10·log10(RBW) 归一，
                # 跨段、跨 RBW 可比 —— 这两个值才是可对外引用的灵敏度证据
                "sa_noise_floor_avg_dbm": candidate.get("avg_noise_floor_dbm"),
                "sa_noise_floor_dbm_per_hz": candidate.get("avg_noise_floor_dbm_per_hz"),
                # D 区：验证量
                "att_dbc_range_db": flat.get("att_dbc_range_db"),
                "rbw_scaling_range_db": flat.get("rbw_scaling_range_db"),
                "stability_std_db": flat.get("stability_std_db"),
                # 说明与时间
                "note": note,
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
