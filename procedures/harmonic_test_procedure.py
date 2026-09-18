#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试流程类
用于执行信号源的二次谐波测试
"""

import time
from datetime import datetime
from base_test_procedure import BaseTestProcedure, MeasurementFailed


class HarmonicTestProcedure(BaseTestProcedure):
    """谐波测试流程类（长表：每 (基波频率, 阶数) 一行）"""

    TEST_TYPE = "harmonic"

    FIELDNAMES = [
        # A 区：标识与数值
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
        # B 区：频谱仪采集条件
        "sa_ref_level_dbm", "sa_input_att_db", "sa_att_mode",
        "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz", "sa_noise_floor_dbm",
        # C 区：源专有
        "harmonic_order", "harmonic_freq_hz", "fundamental_power_dbm", "detected",
        # 判定与时间
        "status", "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        """初始化谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)
        self._output_enabled = False
        self.run_id = ""

    def measure_harmonic_power(self, spectrum_analyzer, fundamental_freq, harmonic_order, sa_config,
                               average_count=3, harmonic_config=None, attempts=3, retry_delay=0.3):
        """测量谐波功率（读数失败自动重试）

        Args:
            spectrum_analyzer: 频谱仪对象
            fundamental_freq: 基波频率 (Hz)
            harmonic_order: 谐波阶数
            sa_config: 频谱仪配置
            average_count: 平均次数（= 独立单次采集次数）
            harmonic_config: 谐波测量配置（含检出门限等）
            attempts: 最多尝试次数（1 次原始 + attempts-1 次重试）
            retry_delay: 两次尝试之间的等待秒数

        Returns:
            dict: {"power": 谐波功率/底噪(dBm) 或 None, "detected": 是否检出谐波,
                   "noise_floor": 本地噪声底(dBm)或None, "attempts": 实际尝试次数}
        """
        harmonic_config = harmonic_config or {}
        attempts = max(1, attempts)
        for attempt in range(1, attempts + 1):
            result = self._measure_harmonic_power_once(
                spectrum_analyzer, fundamental_freq, harmonic_order, sa_config,
                average_count, harmonic_config)
            result["attempts"] = attempt
            if result["power"] is not None:
                if attempt > 1:
                    print(f"    {harmonic_order}次谐波测量第 {attempt} 次尝试成功")
                return result
            if attempt < attempts:
                print(f"    {harmonic_order}次谐波测量第 {attempt} 次尝试失败，{retry_delay}s 后重试...")
                time.sleep(retry_delay)
        print(f"{harmonic_order}次谐波功率测量失败（已尝试 {attempts} 次）")
        return result

    def _measure_harmonic_power_once(self, spectrum_analyzer, fundamental_freq, harmonic_order,
                                     sa_config, average_count=3, harmonic_config=None):
        """谐波功率的单次尝试：配置 → 确定性采集（搜峰）→ N 次独立采集取平均。"""
        harmonic_config = harmonic_config or {}
        harmonic_freq = fundamental_freq * harmonic_order
        print(f"测量{harmonic_order}次谐波功率 @ {self.format_frequency(harmonic_freq)}")

        self.setup_spectrum_analyzer(spectrum_analyzer, harmonic_freq, sa_config)

        marker_num = 1

        # 确定性采集一次完整扫描（*OPC? 握手）；搜峰必须在这条 trace 上进行
        if not self._acquire(spectrum_analyzer):
            return {'power': None, 'detected': False, 'noise_floor': None}

        if hasattr(spectrum_analyzer, 'peak_search'):
            # 清空历史错误，便于下面判断本次搜峰是否成功
            if hasattr(spectrum_analyzer, 'get_error_queue'):
                spectrum_analyzer.get_error_queue()
            spectrum_analyzer.peak_search()
            time.sleep(0.05)
            if hasattr(spectrum_analyzer, 'get_error_queue'):
                errs = spectrum_analyzer.get_error_queue()
                if errs:
                    # 全部打印：被固件拒绝的命令（undefined header 等）只能从这里看出来
                    print(f"    搜峰后仪器错误队列: {'；'.join(str(e) for e in errs)}")
            # 搜峰后校验 marker 是否真的定位成功；无效则回退钉到理论谐波频率
            if hasattr(spectrum_analyzer, 'get_marker_frequency'):
                _pf = spectrum_analyzer.get_marker_frequency(marker_num)
                if _pf is None:
                    print("    峰值搜索后 marker 频率无效，回退到理论谐波频率")
                    spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                    time.sleep(0.05)
        else:
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                time.sleep(0.05)

        # 读取峰值频率与电平（用于后续"是否检出"判定）
        peak_frequency = None
        if hasattr(spectrum_analyzer, 'get_marker_frequency'):
            peak_frequency = spectrum_analyzer.get_marker_frequency(marker_num)
        peak_level = self._read_marker(spectrum_analyzer, marker_num)

        # 用扫描轨迹采样的中位数近似本地噪声底（谐波线宽只占少量 bin，不受峰值影响）
        noise_floor = None
        if hasattr(spectrum_analyzer, 'get_trace'):
            trace = spectrum_analyzer.get_trace(1)
            if trace:
                noise_floor = self._estimate_noise_floor(trace)

        # 检出判据：频率需落在理论谐波附近（按 span 而非谐波频率的 0.1%），
        # 且峰包络需明显高于本地噪声底，避免把噪声峰当成谐波。
        span = sa_config.get('span', 10e3)
        rbw = sa_config.get('rbw', 200)
        detection_margin = harmonic_config.get('harmonic_detection_margin_db', 10)
        freq_tol_ratio = harmonic_config.get('harmonic_freq_tolerance_ratio', 0.25)
        freq_tol = max(span * freq_tol_ratio, rbw * 5, 500.0)

        frequency_ok = peak_frequency is not None and abs(peak_frequency - harmonic_freq) <= freq_tol
        if noise_floor is None:
            # 无法获取轨迹时退化为"只要有峰值即可"（兼容无 get_trace 的仪器）
            level_ok = peak_level is not None
        else:
            level_ok = peak_level is not None and (peak_level - noise_floor) >= detection_margin
        harmonic_detected = frequency_ok and level_ok

        if harmonic_detected:
            print(f"检测到{harmonic_order}次谐波，频率: {self.format_frequency(peak_frequency)} (理论: {self.format_frequency(harmonic_freq)})")
        else:
            print(f"未检测到明显的{harmonic_order}次谐波，将使用理论频率点的底噪")
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                time.sleep(0.05)
                print(f"设置标记器到理论{harmonic_order}次谐波频率: {self.format_frequency(harmonic_freq)}")

        # N 次独立单次采集：每次采集完成后读一次 marker
        #（marker 位置固定，不重复搜峰——否则样本会混入峰位抖动）
        measurements = []

        for i in range(max(1, average_count)):
            if not self._acquire(spectrum_analyzer):
                continue
            measurement = self._read_marker(spectrum_analyzer, marker_num)
            if measurement is not None:
                measurements.append(measurement)

        if measurements:
            avg_power = sum(measurements) / len(measurements)
            tag = "谐波功率" if harmonic_detected else "谐波底噪"
            print(f"{harmonic_order}次{tag}: {avg_power:.2f} dBm (平均{len(measurements)}次)")
        else:
            avg_power = None
            print(f"{harmonic_order}次谐波功率测量失败")

        return {'power': avg_power, 'detected': harmonic_detected, 'noise_floor': noise_floor}

    @staticmethod
    def _estimate_noise_floor(trace):
        """用轨迹采样中位数近似本地噪声底（dBm）

        Args:
            trace: 幅度列表，单位 dBm

        Returns:
            float: 噪声底估计值(dBm)；trace 为空返回 None
        """
        if not trace:
            return None
        sorted_trace = sorted(trace)
        return sorted_trace[len(sorted_trace) // 2]

    def run_harmonic_test(self, signal_gen, spectrum_analyzer, test_point, sa_config, harmonic_config, keep_output=False):
        """执行单个频率点的谐波测试

        Args:
            signal_gen: 信号源对象
            spectrum_analyzer: 频谱仪对象
            test_point: 测试点配置
            sa_config: 频谱仪配置
            harmonic_config: 谐波测量配置
            keep_output: 是否保持信号源输出（默认False，测试后关闭输出）

        Returns:
            dict: 测试结果
        """
        frequency = test_point['frequency']
        set_power = test_point['set_power']
        settling_time = test_point.get('settling_time', 1.0)
        frequency_settling_time = test_point.get('frequency_settling_time', 1.0)
        harmonic_order = harmonic_config.get('harmonic_order', 2)
        average_count = harmonic_config.get('measurement_average', 3)
        max_attempts = harmonic_config.get('measurement_attempts', 3)
        retry_delay = harmonic_config.get('retry_delay_s', 0.3)

        print(f"\n{'=' * 60}")
        print(f"开始测试: {self.format_frequency(frequency)}")
        print(f"{'=' * 60}")

        # 1. 设置信号源；输出只在首个测试点打开，后续频点不重复触发输出开关
        if not self._output_enabled:
            self.setup_signal_generator(
                signal_gen,
                frequency,
                set_power,
                enable_output=True,
                settling_time=0,
                frequency_settling_time=frequency_settling_time
            )
            self._output_enabled = True
        else:
            self.setup_signal_generator(
                signal_gen,
                frequency,
                set_power,
                enable_output=False,
                settling_time=0,
                frequency_settling_time=frequency_settling_time
            )
        time.sleep(settling_time)

        # 输入耦合判断：低于阈值用 DC（AC 耦合有低频截止，会严重压低低频读数）。
        # 按基波频率判断、每个测试点只设一次，使基波与谐波测量使用同一耦合，避免 dBc 被耦合切换影响。
        # 仪器只支持 DC 时按能力折算（见 _resolve_input_coupling），不再下发注定被拒的 AC。
        coupling, folded_from_ac = self._resolve_input_coupling(sa_config, frequency)
        if hasattr(spectrum_analyzer, 'set_input_coupling'):
            spectrum_analyzer.set_input_coupling(coupling)
            extra = "（配置要 AC，但仪器只支持 DC，已用 DC）" if folded_from_ac else ""
            print(f"频谱仪输入耦合: {coupling} (基波 {self.format_frequency(frequency)}){extra}")

        # 2. 测量基波功率（内部含重试）
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config,
            average_count=average_count, attempts=max_attempts, retry_delay=retry_delay
        )
        fundamental_attempts = self.last_measure_attempts

        # 3. 测量谐波功率（内部含重试）
        harmonic_power = None
        harmonic_detected = False
        harmonic_floor = None
        harmonic_attempts = 0
        failure_note = ""
        if fundamental_power is None:
            failure_note = f"基波功率测量失败（尝试 {fundamental_attempts} 次）"
        else:
            harmonic_result = self.measure_harmonic_power(
                spectrum_analyzer, frequency, harmonic_order, sa_config,
                average_count=average_count, harmonic_config=harmonic_config,
                attempts=max_attempts, retry_delay=retry_delay
            )
            harmonic_power = harmonic_result['power']
            harmonic_detected = harmonic_result['detected']
            harmonic_floor = harmonic_result['noise_floor']
            harmonic_attempts = harmonic_result.get('attempts', 0)
            if harmonic_power is None:
                failure_note = f"{harmonic_order}次谐波功率测量失败（尝试 {harmonic_attempts} 次）"

        # 4. 计算谐波抑制比 (dBc)
        if fundamental_power is not None and harmonic_power is not None:
            harmonic_suppression = harmonic_power - fundamental_power
            print(f"二次谐波抑制: {harmonic_suppression:.2f} dBc")
        else:
            harmonic_suppression = None
            print("无法计算谐波抑制比")

        # 5. 根据keep_output参数决定是否关闭信号源输出
        if not keep_output:
            signal_gen.enable_output(False)
            self._output_enabled = False

        # 无谐波时的信息标注：区分"检出谐波"与"读数为底噪/噪声"
        if failure_note:
            harmonic_note = failure_note
        elif harmonic_detected:
            harmonic_note = f"检出{harmonic_order}次谐波"
        elif harmonic_floor is not None:
            harmonic_note = f"未检出{harmonic_order}次谐波（读数为谐波频率处底噪，约{harmonic_floor:.1f}dBm）"
        else:
            harmonic_note = f"未检出{harmonic_order}次谐波（读数为谐波频率处底噪）"

        # 重试信息：仅在测量成功时追加（失败行由 failure_note 说明原因，
        # 不能出现"测量失败…重试2次后成功"这种自相矛盾的备注）
        if not failure_note:
            if fundamental_attempts > 1:
                harmonic_note += f"；基波重试{fundamental_attempts - 1}次后成功"
            if harmonic_attempts > 1:
                harmonic_note += f"；谐波重试{harmonic_attempts - 1}次后成功"

        if failure_note:
            status = "FAIL"
        elif harmonic_detected:
            status = "OK"
        else:
            status = "SUSPECT"

        # 创建测试结果（长表：每 (基波频率, 阶数) 一行）
        result = {
            # A 区：标识与数值
            "run_id": getattr(self, "run_id", ""),
            "test_type": self.TEST_TYPE,
            "carrier_hz": frequency,
            "set_power_dbm": set_power,
            "measured_power_dbm": harmonic_power,
            "delta_db": None if harmonic_suppression is None else round(harmonic_suppression, 3),
            "delta_ref": "fundamental",
            # B 区：频谱仪采集条件
            "sa_ref_level_dbm": sa_config.get('reference_level', 10),
            "sa_input_att_db": sa_config.get('attenuation', 10),
            "sa_att_mode": "manual",
            "sa_span_hz": sa_config.get('span', 10e6),
            "sa_rbw_hz": sa_config.get('rbw', 100e3),
            "sa_vbw_hz": sa_config.get('vbw', 100e3),
            "sa_noise_floor_dbm": harmonic_floor,
            # C 区：源专有
            "harmonic_order": harmonic_order,
            "harmonic_freq_hz": frequency * harmonic_order,
            "fundamental_power_dbm": fundamental_power,
            "detected": self.bool_str(harmonic_detected),
            # 判定与时间
            "status": status,
            "note": harmonic_note,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

        print(f"测试完成: {self.format_frequency(frequency)}")
        print(f"基波功率: {fundamental_power:.2f} dBm" if fundamental_power is not None else "基波功率: 测量失败")
        print(f"二次谐波功率: {harmonic_power:.2f} dBm" if harmonic_power is not None else "二次谐波功率: 测量失败")
        print(f"谐波检出: {'是' if harmonic_detected else '否'}")
        if harmonic_suppression is not None:
            print(f"谐波抑制: {harmonic_suppression:.2f} dBc")

        # 失败 → 该行已判 FAIL 并写入 CSV（留证据），此处显式中止整轮测试
        if failure_note:
            signal_gen.enable_output(False)
            self._output_enabled = False
            raise MeasurementFailed(
                f"{self.format_frequency(frequency)}: {failure_note}，测试中止")

        return result

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        self.run_id = self.derive_run_id(csv_path)
        super().start_csv_stream(csv_path, self.FIELDNAMES)

    def print_summary(self):
        """打印测试摘要（谐波专项）"""
        if not self.test_results:
            print("没有测试结果")
            return

        print(f"\n{'=' * 60}")
        print("测试摘要")
        print(f"{'=' * 60}")

        rows = self.test_results
        print(f"总测试点数: {len(rows)}")

        freqs = [r["carrier_hz"] for r in rows if r.get("carrier_hz") is not None]
        if freqs:
            print(f"频率范围: {self.format_frequency(min(freqs))} - {self.format_frequency(max(freqs))}")
        if rows[0].get("set_power_dbm") is not None:
            print(f"设置功率: {rows[0]['set_power_dbm']} dBm")

        detected = [r for r in rows if r.get("detected") == "true"]
        print(f"检出谐波点数: {len(detected)}/{len(rows)}")

        suppressions = [r["delta_db"] for r in rows if r.get("delta_db") is not None]
        if suppressions:
            avg = sum(suppressions) / len(suppressions)
            best = min(suppressions)
            worst = max(suppressions)
            print(f"平均谐波抑制: {avg:.2f} dBc")
            print(f"最佳谐波抑制: {best:.2f} dBc")
            print(f"最差谐波抑制: {worst:.2f} dBc")

        print(f"{'=' * 60}")
