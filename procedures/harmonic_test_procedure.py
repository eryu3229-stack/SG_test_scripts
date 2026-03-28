#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谐波测试流程类
用于执行信号源的二次谐波测试
"""

import time
import csv
import os
from datetime import datetime
import pandas as pd


class HarmonicTestProcedure:
    """谐波测试流程类"""

    def __init__(self, instrument_manager):
        """初始化谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        self.instrument_manager = instrument_manager
        self.test_results = []
        self.current_frequency = None
        self.current_power = None

    def setup_signal_generator(self, signal_gen, frequency, power):
        """设置信号源

        Args:
            signal_gen: 信号源对象
            frequency: 频率 (Hz)
            power: 功率 (dBm)
        """
        print(f"设置信号源: {frequency / 1e6:.2f}MHz, {power}dBm")

        # 设置频率
        signal_gen.set_frequency(frequency)

        # 设置功率
        signal_gen.set_power(power)

        # 启用输出
        signal_gen.enable_output(True)

        self.current_frequency = frequency
        self.current_power = power

        # 等待信号稳定
        time.sleep(1)

    def setup_spectrum_analyzer(self, spectrum_analyzer, center_frequency, config):
        """设置频谱仪

        Args:
            spectrum_analyzer: 频谱仪对象
            center_frequency: 中心频率 (Hz)
            config: 频谱仪配置字典
        """
        print(f"设置频谱仪中心频率: {center_frequency / 1e6:.2f}MHz")

        # 设置中心频率
        spectrum_analyzer.set_center_frequency(center_frequency)

        # 设置频率跨度
        spectrum_analyzer.set_span(config.get('span', 10e6))

        # 设置参考电平
        spectrum_analyzer.set_reference_level(config.get('reference_level', 10))

        # 设置分辨率带宽
        if hasattr(spectrum_analyzer, 'set_rbw'):
            spectrum_analyzer.set_rbw(config.get('rbw', 100e3))

        # 设置视频带宽
        if hasattr(spectrum_analyzer, 'set_vbw'):
            spectrum_analyzer.set_vbw(config.get('vbw', 100e3))

        # 设置衰减
        if hasattr(spectrum_analyzer, 'set_attenuation'):
            spectrum_analyzer.set_attenuation(config.get('attenuation', 10))

        # 等待设置生效
        time.sleep(0.5)

    def measure_fundamental_power(self, spectrum_analyzer, frequency, sa_config):
        """测量基波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            frequency: 基波频率 (Hz)
            sa_config: 频谱仪配置

        Returns:
            float: 基波功率 (dBm)
        """
        print(f"测量基波功率 @ {frequency / 1e6:.2f}MHz")

        # 设置中心频率为基波频率
        self.setup_spectrum_analyzer(spectrum_analyzer, frequency, sa_config)

        # 执行峰值搜索
        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()

        # 使用同一个标记器（固定为1）测量基波功率
        marker_num = 1

        # 设置标记器到中心频率
        if hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, frequency)

        # 测量标记器功率
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            power = spectrum_analyzer.measure_marker_power(marker_num)
        else:
            # 备用方法：使用通用功率测量
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
            print(f"基波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        elif power is not None:
            print(f"基波功率: {power:.2f} dBm")
            return power
        else:
            print("基波功率测量失败")
            return None

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

        # 设置中心频率为谐波频率
        self.setup_spectrum_analyzer(spectrum_analyzer, harmonic_freq, sa_config)

        # 执行峰值搜索
        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()

        # 使用同一个标记器（固定为1）测量谐波功率
        marker_num = 1

        # 设置标记器到谐波频率
        if hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, harmonic_freq)

        # 测量谐波功率
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            power = spectrum_analyzer.measure_marker_power(marker_num)
        else:
            # 备用方法：使用通用功率测量
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
            print(f"{harmonic_order}次谐波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        elif power is not None:
            print(f"{harmonic_order}次谐波功率: {power:.2f} dBm")
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

        # 1. 设置信号源
        self.setup_signal_generator(signal_gen, frequency, set_power)

        # 等待信号稳定
        time.sleep(settling_time)

        # 2. 测量基波功率
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config
        )

        # 3. 测量二次谐波功率
        harmonic_order = harmonic_config.get('harmonic_order', 2)
        harmonic_power = self.measure_harmonic_power(
            spectrum_analyzer, frequency, harmonic_order, sa_config
        )

        # 4. 计算谐波抑制比 (dBc)
        if fundamental_power is not None and harmonic_power is not None:
            harmonic_suppression = harmonic_power - fundamental_power  # dBc
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
        }

        self.test_results.append(result)

        print(f"测试完成: {frequency / 1e6:.2f}MHz")
        print(f"基波功率: {fundamental_power:.2f} dBm")
        print(f"二次谐波功率: {harmonic_power:.2f} dBm")
        if harmonic_suppression is not None:
            print(f"谐波抑制: {harmonic_suppression:.2f} dBc")

        return result

    def save_results_to_csv(self, filename):
        """保存测试结果到CSV文件

        Args:
            filename: 输出文件名
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'timestamp',
                    'frequency_hz',
                    'frequency_mhz',
                    'set_power_dbm',
                    'fundamental_power_dbm',
                    'harmonic_power_dbm',
                    'harmonic_suppression_dbc',
                    'harmonic_order',
                    'test_duration_sec'
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for result in self.test_results:
                    writer.writerow(result)

            print(f"测试结果已保存到CSV文件: {filename}")
            return True

        except Exception as e:
            print(f"保存CSV文件失败: {e}")
            return False

    def save_results_to_excel(self, filename):
        """保存测试结果到Excel文件

        Args:
            filename: 输出文件名
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

            # 转换为DataFrame
            df = pd.DataFrame(self.test_results)

            # 添加摘要信息
            summary_data = {
                '测试项目': ['谐波测试'],
                '测试时间': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                '总测试点数': [len(self.test_results)],
                '频率范围': [f"{df['frequency_mhz'].min():.0f}-{df['frequency_mhz'].max():.0f} MHz"],
                '平均谐波抑制': [f"{df['harmonic_suppression_dbc'].mean():.2f} dBc" if not df[
                    'harmonic_suppression_dbc'].isnull().all() else 'N/A'],
            }
            summary_df = pd.DataFrame(summary_data)

            # 创建Excel写入器
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 写入摘要
                summary_df.to_excel(writer, sheet_name='测试摘要', index=False)

                # 写入详细数据
                df.to_excel(writer, sheet_name='详细数据', index=False)

            print(f"测试结果已保存到Excel文件: {filename}")
            return True

        except ImportError:
            print("未安装pandas/openpyxl，无法保存为Excel格式")
            return False
        except Exception as e:
            print(f"保存Excel文件失败: {e}")
            return False

    def save_results(self, filename):
        """根据文件扩展名保存测试结果

        Args:
            filename: 输出文件名
        """
        if filename.lower().endswith('.xlsx') or filename.lower().endswith('.xls'):
            return self.save_results_to_excel(filename)
        else:
            # 默认保存为CSV
            if not filename.lower().endswith('.csv'):
                filename += '.csv'
            return self.save_results_to_csv(filename)

    def print_summary(self):
        """打印测试摘要"""
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