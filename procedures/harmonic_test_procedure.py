#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试流程类
用于执行信号源的二次谐波测试
"""

import time
import os
from datetime import datetime
import pandas as pd
from base_test_procedure import BaseTestProcedure, format_frequency


class HarmonicTestProcedure(BaseTestProcedure):
    """谐波测试流程类"""

    def __init__(self, instrument_manager):
        """初始化谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)

    def measure_harmonic_power(self, spectrum_analyzer, fundamental_freq, harmonic_order, sa_config):
        """测量谐波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            fundamental_freq: 基波频率 (Hz)
            harmonic_order: 谐波阶数
            sa_config: 频谱仪配置

        Returns:
            float: 谐波功率 (dBm)
        """
        harmonic_freq = fundamental_freq * harmonic_order
        print(f"测量{harmonic_order}次谐波功率 @ {harmonic_freq / 1e6:.2f}MHz")

        self.setup_spectrum_analyzer(spectrum_analyzer, harmonic_freq, sa_config)

        marker_num = 1

        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()
            time.sleep(0.5)
        else:
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                time.sleep(0.2)

        # 检查峰值是否在理论谐波频率附近
        harmonic_detected = False
        if hasattr(spectrum_analyzer, 'get_marker_frequency'):
            peak_frequency = spectrum_analyzer.get_marker_frequency(marker_num)
            frequency_tolerance = harmonic_freq * 0.001

            if peak_frequency is not None and abs(peak_frequency - harmonic_freq) <= frequency_tolerance:
                harmonic_detected = True
                print(f"检测到{harmonic_order}次谐波，频率: {peak_frequency / 1e6:.2f}MHz (理论: {harmonic_freq / 1e6:.2f}MHz)")
            else:
                print(f"未检测到明显的{harmonic_order}次谐波，将使用理论频率点的底噪")

        if not harmonic_detected:
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)
                time.sleep(0.2)
                print(f"设置标记器到理论{harmonic_order}次谐波频率: {harmonic_freq / 1e6:.2f}MHz")

        # 测量功率
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            power = spectrum_analyzer.measure_marker_power(marker_num)
        else:
            power = spectrum_analyzer.measure_power()

        # 多次测量取平均
        average_count = sa_config.get('measurement_average', 3)
        measurements = []

        for i in range(average_count):
            if hasattr(spectrum_analyzer, 'measure_marker_power'):
                measurement = spectrum_analyzer.measure_marker_power(marker_num)
            else:
                measurement = spectrum_analyzer.measure_power()

            if measurement is not None:
                measurements.append(measurement)
            time.sleep(0.3)

        if measurements:
            avg_power = sum(measurements) / len(measurements)
            if harmonic_detected:
                print(f"{harmonic_order}次谐波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            else:
                print(f"{harmonic_order}次谐波底噪: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        elif power is not None:
            if harmonic_detected:
                print(f"{harmonic_order}次谐波功率: {power:.2f} dBm")
            else:
                print(f"{harmonic_order}次谐波底噪: {power:.2f} dBm")
            return power
        else:
            print(f"{harmonic_order}次谐波功率测量失败")
            return None

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

        print(f"\n{'=' * 60}")
        print(f"开始测试: {frequency / 1e6:.2f}MHz")
        print(f"{'=' * 60}")

        # 1. 设置信号源（使用基类方法，settling_time 由 run_harmonic_test 自己控制）
        self.setup_signal_generator(signal_gen, frequency, set_power, settling_time=0)
        time.sleep(settling_time)

        # 2. 测量基波功率（使用基类方法）
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config
        )

        # 3. 测量谐波功率
        harmonic_order = harmonic_config.get('harmonic_order', 2)
        harmonic_power = self.measure_harmonic_power(
            spectrum_analyzer, frequency, harmonic_order, sa_config
        )

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

        # 创建测试结果
        result = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'frequency_hz': frequency,
            'frequency_mhz': frequency / 1e6,
            'set_power_dbm': set_power,
            'fundamental_power_dbm': fundamental_power,
            'harmonic_power_dbm': harmonic_power,
            'harmonic_suppression_dbc': harmonic_suppression,
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

        print(f"测试完成: {frequency / 1e6:.2f}MHz")
        print(f"基波功率: {fundamental_power:.2f} dBm")
        print(f"二次谐波功率: {harmonic_power:.2f} dBm")
        if harmonic_suppression is not None:
            print(f"谐波抑制: {harmonic_suppression:.2f} dBc")

        return result

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        fieldnames = [
            "timestamp", "frequency_hz", "frequency_mhz", "set_power_dbm",
            "fundamental_power_dbm", "harmonic_power_dbm",
            "harmonic_suppression_dbc", "harmonic_order",
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
            print(f"频率范围: {df['frequency_mhz'].min():.0f} - {df['frequency_mhz'].max():.0f} MHz")
            print(f"设置功率: {df['set_power_dbm'].iloc[0]} dBm")

            if not df['harmonic_suppression_dbc'].isnull().all():
                print(f"平均谐波抑制: {df['harmonic_suppression_dbc'].mean():.2f} dBc")
                print(
                    f"最佳谐波抑制: {df['harmonic_suppression_dbc'].min():.2f} dBc @ {df.loc[df['harmonic_suppression_dbc'].idxmin(), 'frequency_mhz']:.0f} MHz")
                print(
                    f"最差谐波抑制: {df['harmonic_suppression_dbc'].max():.2f} dBc @ {df.loc[df['harmonic_suppression_dbc'].idxmax(), 'frequency_mhz']:.0f} MHz")

        print(f"{'=' * 60}")