#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试流程类
用于执行信号源的二次谐波测试
"""

import time
from datetime import datetime
import pandas as pd
from base_test_procedure import BaseTestProcedure


class HarmonicTestProcedure(BaseTestProcedure):
    """谐波测试流程类"""

    def __init__(self, instrument_manager):
        """初始化谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)
        self._output_enabled = False

    def measure_harmonic_power(self, spectrum_analyzer, fundamental_freq, harmonic_order, sa_config, average_count=3, harmonic_config=None, sync_kwargs=None):
        """测量谐波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            fundamental_freq: 基波频率 (Hz)
            harmonic_order: 谐波阶数
            sa_config: 频谱仪配置
            average_count: 测量平均次数
            harmonic_config: 谐波测量配置（含检出门限等）
            sync_kwargs: 透传给 _sweep_sync / wait_for_sweep 的参数

        Returns:
            dict: {"power": 谐波功率/底噪(dBm), "detected": 是否检出谐波,
                   "noise_floor": 本地噪声底(dBm)或None}
        """
        harmonic_config = harmonic_config or {}
        sync_kwargs = sync_kwargs or {}
        harmonic_freq = fundamental_freq * harmonic_order
        print(f"测量{harmonic_order}次谐波功率 @ {self.format_frequency(harmonic_freq)}")

        self.setup_spectrum_analyzer(spectrum_analyzer, harmonic_freq, sa_config)

        marker_num = 1

        # 先等待一次完整扫描，避免读到过期 trace
        self._sweep_sync(spectrum_analyzer, **sync_kwargs)

        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()
            time.sleep(0.05)
        else:
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                time.sleep(0.05)

        # 读取峰值频率与电平（用于后续"是否检出"判定）
        peak_frequency = None
        if hasattr(spectrum_analyzer, 'get_marker_frequency'):
            peak_frequency = spectrum_analyzer.get_marker_frequency(marker_num)
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            peak_level = spectrum_analyzer.measure_marker_power(marker_num)
        else:
            peak_level = spectrum_analyzer.measure_power()

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

        # 多次测量取平均：每次读数前都触发并等待一次完整扫描，确保数值准确
        measurements = []

        for i in range(average_count):
            if not self._sweep_sync(spectrum_analyzer, **sync_kwargs):
                time.sleep(0.3)  # 无扫描同步支持时退化为固定等待
            if hasattr(spectrum_analyzer, 'measure_marker_power'):
                measurement = spectrum_analyzer.measure_marker_power(marker_num)
            else:
                measurement = spectrum_analyzer.measure_power()

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

        # 谐波测试使用小 SPAN，无需杂散测试那么大的安全余量
        sync_kwargs = sa_config.get('sweep_sync_kwargs', {'factor': 1.0, 'margin': 0.2})

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
        dc_below = sa_config.get('dc_coupling_below_hz', 10e6)
        coupling = 'DC' if frequency < dc_below else sa_config.get('input_coupling', 'AC')
        if hasattr(spectrum_analyzer, 'set_input_coupling'):
            spectrum_analyzer.set_input_coupling(coupling)
            print(f"频谱仪输入耦合: {coupling} (基波 {self.format_frequency(frequency)})")

        # 2. 测量基波功率（使用基类方法）
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config,
            average_count=harmonic_config.get('measurement_average', 3),
            sync_kwargs=sync_kwargs
        )

        # 3. 测量谐波功率（返回 dict，含检出状态与噪声底）
        harmonic_order = harmonic_config.get('harmonic_order', 2)
        harmonic_result = self.measure_harmonic_power(
            spectrum_analyzer, frequency, harmonic_order, sa_config,
            average_count=harmonic_config.get('measurement_average', 3),
            harmonic_config=harmonic_config,
            sync_kwargs=sync_kwargs
        )
        harmonic_power = harmonic_result['power']
        harmonic_detected = harmonic_result['detected']
        harmonic_floor = harmonic_result['noise_floor']

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
        if harmonic_detected:
            harmonic_note = f"检出{harmonic_order}次谐波"
        elif harmonic_power is not None:
            if harmonic_floor is not None:
                harmonic_note = f"未检出{harmonic_order}次谐波（读数为谐波频率处底噪，约{harmonic_floor:.1f}dBm）"
            else:
                harmonic_note = f"未检出{harmonic_order}次谐波（读数为谐波频率处底噪）"
        else:
            harmonic_note = f"{harmonic_order}次谐波测量失败"

        # 创建测试结果
        result = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'frequency_hz': frequency,
            'frequency_mhz': frequency / 1e6,
            'set_power_dbm': set_power,
            'fundamental_power_dbm': fundamental_power,
            'harmonic_power_dbm': harmonic_power,
            'harmonic_suppression_dbc': harmonic_suppression,
            'harmonic_detected': harmonic_detected,
            'harmonic_floor_dbm': harmonic_floor,
            'harmonic_note': harmonic_note,
            'harmonic_order': harmonic_order,
            'sa_attenuation_db': sa_config.get('attenuation', 10),
            'sa_reference_level_db': sa_config.get('reference_level', 10),
            'sa_span_hz': sa_config.get('span', 10e6),
            'sa_rbw_hz': sa_config.get('rbw', 100e3),
            'sa_vbw_hz': sa_config.get('vbw', 100e3),
        }

        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

        print(f"测试完成: {self.format_frequency(frequency)}")
        print(f"基波功率: {fundamental_power:.2f} dBm")
        print(f"二次谐波功率: {harmonic_power:.2f} dBm" if harmonic_power is not None else "二次谐波功率: 测量失败")
        print(f"谐波检出: {'是' if harmonic_detected else '否'}")
        if harmonic_suppression is not None:
            print(f"谐波抑制: {harmonic_suppression:.2f} dBc")

        return result

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        fieldnames = [
            "timestamp", "frequency_hz", "frequency_mhz", "set_power_dbm",
            "fundamental_power_dbm", "harmonic_power_dbm",
            "harmonic_suppression_dbc", "harmonic_detected",
            "harmonic_floor_dbm", "harmonic_note", "harmonic_order",
            "sa_attenuation_db", "sa_reference_level_db",
            "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz",
        ]
        super().start_csv_stream(csv_path, fieldnames)

    def finish_xlsx(self, xlsx_path):
        """关闭 CSV 流并转为 XLSX"""
        super().finish_xlsx(xlsx_path, sheet_name="详细数据")

    def print_summary(self):
        """打印测试摘要（谐波专项）"""
        if not self.test_results:
            print("没有测试结果")
            return

        print(f"\n{'=' * 60}")
        print("测试摘要")
        print(f"{'=' * 60}")

        df = pd.DataFrame(self.test_results) if self.test_results else None

        print(f"总测试点数: {len(self.test_results)}")

        if df is not None and not df.empty:
            freq_min = self.format_frequency(df['frequency_hz'].min())
            freq_max = self.format_frequency(df['frequency_hz'].max())
            print(f"频率范围: {freq_min} - {freq_max}")
            print(f"设置功率: {df['set_power_dbm'].iloc[0]} dBm")

            if 'harmonic_detected' in df.columns:
                detected_count = int(df['harmonic_detected'].sum())
                print(f"检出谐波点数: {detected_count}/{len(df)}")

            if not df['harmonic_suppression_dbc'].isnull().all():
                best_idx = df['harmonic_suppression_dbc'].idxmin()
                worst_idx = df['harmonic_suppression_dbc'].idxmax()
                best_freq = self.format_frequency(df.loc[best_idx, 'frequency_hz'])
                worst_freq = self.format_frequency(df.loc[worst_idx, 'frequency_hz'])
                print(f"平均谐波抑制: {df['harmonic_suppression_dbc'].mean():.2f} dBc")
                print(f"最佳谐波抑制: {df['harmonic_suppression_dbc'].min():.2f} dBc @ {best_freq}")
                print(f"最差谐波抑制: {df['harmonic_suppression_dbc'].max():.2f} dBc @ {worst_freq}")

        print(f"{'=' * 60}")
