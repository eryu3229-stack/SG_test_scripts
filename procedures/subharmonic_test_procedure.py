#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分谐波测试流程类
用于执行信号源的分谐波测试
"""

import time
import os
from datetime import datetime
import pandas as pd
from base_test_procedure import BaseTestProcedure, format_frequency


class SubharmonicTestProcedure(BaseTestProcedure):
    """分谐波测试流程类"""

    def __init__(self, instrument_manager):
        """初始化分谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)

    def measure_subharmonic_power(self, spectrum_analyzer, fundamental_freq, subharmonic_order, sa_config):
        """测量分谐波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            fundamental_freq: 基波频率 (Hz)
            subharmonic_order: 分谐波阶数
            sa_config: 频谱仪配置

        Returns:
            float: 分谐波功率 (dBm)
        """
        subharmonic_freq = fundamental_freq / subharmonic_order
        print(f"测量1/{subharmonic_order}分谐波功率 @ {subharmonic_freq / 1e6:.2f}MHz")

        self.setup_spectrum_analyzer(spectrum_analyzer, subharmonic_freq, sa_config)

        marker_num = 1

        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()

        if hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, subharmonic_freq)

        # 测量分谐波功率
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
            print(f"1/{subharmonic_order}分谐波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        elif power is not None:
            print(f"1/{subharmonic_order}分谐波功率: {power:.2f} dBm")
            return power
        else:
            print(f"1/{subharmonic_order}分谐波功率测量失败")
            return None

    def run_subharmonic_test(self, signal_gen, spectrum_analyzer, test_point, sa_config, subharmonic_config, keep_output=False):
        """执行单个频率点的分谐波测试

        Args:
            signal_gen: 信号源对象
            spectrum_analyzer: 频谱仪对象
            test_point: 测试点配置
            sa_config: 频谱仪配置
            subharmonic_config: 分谐波测量配置
            keep_output: 是否保持信号源输出（默认False）

        Returns:
            dict: 测试结果
        """
        frequency = test_point['frequency']
        set_power = test_point['set_power']
        settling_time = test_point.get('settling_time', 1.0)

        print(f"\n{'=' * 60}")
        print(f"开始测试: {frequency / 1e6:.2f}MHz")
        print(f"{'=' * 60}")

        # 1. 设置信号源（使用基类方法）
        self.setup_signal_generator(signal_gen, frequency, set_power, settling_time=0)
        time.sleep(settling_time)

        # 2. 测量基波功率（使用基类方法）
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config
        )

        # 3. 测量分谐波功率
        subharmonic_orders = subharmonic_config.get('subharmonic_orders', [2])
        subharmonic_powers = {}
        subharmonic_suppressions = {}

        for order in subharmonic_orders:
            subharmonic_power = self.measure_subharmonic_power(
                spectrum_analyzer, frequency, order, sa_config
            )
            subharmonic_powers[order] = subharmonic_power

            if fundamental_power is not None and subharmonic_power is not None:
                suppression = subharmonic_power - fundamental_power
                subharmonic_suppressions[order] = suppression
                print(f"1/{order}分谐波抑制: {suppression:.2f} dBc")
            else:
                subharmonic_suppressions[order] = None
                print(f"无法计算1/{order}分谐波抑制比")

        # 4. 根据keep_output参数决定是否关闭信号源输出
        if not keep_output:
            signal_gen.enable_output(False)

        # 创建测试结果
        result = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'frequency_hz': frequency,
            'frequency_mhz': frequency / 1e6,
            'set_power_dbm': set_power,
            'fundamental_power_dbm': fundamental_power,
        }

        for order in subharmonic_orders:
            result[f'subharmonic_{order}_power_dbm'] = subharmonic_powers[order]
            result[f'subharmonic_{order}_suppression_dbc'] = subharmonic_suppressions[order]

        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

        print(f"测试完成: {frequency / 1e6:.2f}MHz")
        print(f"基波功率: {fundamental_power:.2f} dBm")
        for order in subharmonic_orders:
            print(f"1/{order}分谐波功率: {subharmonic_powers[order]:.2f} dBm")
            if subharmonic_suppressions[order] is not None:
                print(f"分谐波抑制: {subharmonic_suppressions[order]:.2f} dBc")

        return result

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        fieldnames = [
            "timestamp", "frequency_hz", "frequency_mhz", "set_power_dbm",
            "fundamental_power_dbm",
            "subharmonic_2_power_dbm", "subharmonic_2_suppression_dbc",
        ]
        super().start_csv_stream(csv_path, fieldnames)

    def finish_xlsx(self, xlsx_path):
        """关闭 CSV 流并转为 XLSX"""
        super().finish_xlsx(xlsx_path, sheet_name="详细数据")

    def print_summary(self):
        """打印测试摘要（分谐波专项）"""
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

            for col in df.columns:
                if 'subharmonic_' in col and 'suppression' in col:
                    order = col.split('_')[1]
                    if not df[col].isnull().all():
                        print(f"平均1/{order}分谐波抑制: {df[col].mean():.2f} dBc")

        print(f"{'=' * 60}")