#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础测试流程类
提供测试流程的公共功能 — 所有 Procedure 的基类
"""

import time
import csv
import os
from datetime import datetime
import pandas as pd

from utils.formatting import format_frequency


class BaseTestProcedure:
    """基础测试流程类 — 所有 Procedure 统一基类"""

    def __init__(self, instrument_manager):
        """初始化测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        self.instrument_manager = instrument_manager
        self.test_results = []
        self.csv_streamer = None
        self.current_frequency = None
        self.current_power = None

    @staticmethod
    def format_frequency(frequency):
        """格式化频率显示（静态方法，方便子类调用）

        Args:
            frequency: 频率值，单位Hz
        Returns:
            str: 格式化后的频率字符串
        """
        return format_frequency(frequency)

    def setup_signal_generator(self, signal_gen, frequency, power, enable_output=True, settling_time=1.0, frequency_settling_time=0.0):
        """设置信号源

        Args:
            signal_gen: 信号源对象
            frequency: 频率 (Hz)
            power: 功率 (dBm)
            enable_output: 是否启用输出，默认为True
            settling_time: 信号稳定等待时间（秒），默认1.0
            frequency_settling_time: 频率切换稳定等待时间（秒），默认0
        """
        print(f"设置信号源: {format_frequency(frequency)}, {power}dBm")

        signal_gen.set_frequency(frequency)
        if frequency_settling_time > 0:
            print(f"等待频率切换稳定 {frequency_settling_time}秒...")
            time.sleep(frequency_settling_time)
        signal_gen.set_power(power)

        if enable_output:
            signal_gen.enable_output(True)

        self.current_frequency = frequency
        self.current_power = power

        if settling_time > 0:
            time.sleep(settling_time)

    def setup_spectrum_analyzer(self, spectrum_analyzer, center_frequency, config):
        """设置频谱仪

        Args:
            spectrum_analyzer: 频谱仪对象
            center_frequency: 中心频率 (Hz)
            config: 频谱仪配置字典
        """
        print(f"设置频谱仪中心频率: {format_frequency(center_frequency)}")

        spectrum_analyzer.set_center_frequency(center_frequency)

        span = config.get('span', 1e6)
        print(f"使用配置SPAN: {format_frequency(span)}")
        spectrum_analyzer.set_span(span)

        reference_level = config.get('reference_level', 10)
        spectrum_analyzer.set_reference_level(reference_level)

        rbw = config.get('rbw', 1e3)
        print(f"使用配置RBW: {format_frequency(rbw)}")
        if hasattr(spectrum_analyzer, 'set_rbw'):
            spectrum_analyzer.set_rbw(rbw)

        vbw = config.get('vbw', 100e3)
        print(f"使用配置VBW: {format_frequency(vbw)}")
        if hasattr(spectrum_analyzer, 'set_vbw'):
            spectrum_analyzer.set_vbw(vbw)

        if hasattr(spectrum_analyzer, 'set_attenuation'):
            attenuation = config.get('attenuation', 10)
            spectrum_analyzer.set_attenuation(attenuation)
            print(f"设置衰减: {attenuation} dB")

    def measure_fundamental_power(self, spectrum_analyzer, frequency, sa_config, average_count=3):
        """测量基波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            frequency: 基波频率 (Hz)
            sa_config: 频谱仪配置

        Returns:
            float: 基波功率 (dBm)
        """
        print(f"测量基波功率 @ {format_frequency(frequency)}")

        self.setup_spectrum_analyzer(spectrum_analyzer, frequency, sa_config)

        marker_num = 1

        # 执行峰值搜索（先等待一次完整扫描，避免读到过期 trace）
        if hasattr(spectrum_analyzer, 'peak_search'):
            self._sweep_sync(spectrum_analyzer)
            spectrum_analyzer.peak_search()
            time.sleep(0.5)
        else:
            if hasattr(spectrum_analyzer, 'set_marker_frequency'):
                spectrum_analyzer.set_marker_frequency(marker_num, frequency)
                time.sleep(0.2)

        # 多次测量取平均：每次读数前都触发并等待一次完整扫描，确保数值准确
        measurements = []

        for i in range(average_count):
            if not self._sweep_sync(spectrum_analyzer):
                time.sleep(0.3)  # 无扫描同步支持时退化为固定等待
            if hasattr(spectrum_analyzer, 'measure_marker_power'):
                measurement = spectrum_analyzer.measure_marker_power(marker_num)
            else:
                measurement = spectrum_analyzer.measure_power()

            if measurement is not None:
                measurements.append(measurement)

        if measurements:
            avg_power = sum(measurements) / len(measurements)
            print(f"基波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        else:
            print("基波功率测量失败")
            return None

    @staticmethod
    def _sweep_sync(spectrum_analyzer):
        """若频谱仪支持扫描同步，则触发并等待一次完整扫描

        Args:
            spectrum_analyzer: 频谱仪对象

        Returns:
            bool: 是否成功执行了扫描同步
        """
        if hasattr(spectrum_analyzer, 'wait_for_sweep'):
            return spectrum_analyzer.wait_for_sweep(1) is True
        return False

    def save_results_to_csv(self, filename, fieldnames=None):
        """保存测试结果到CSV文件

        Args:
            filename: 输出文件名
            fieldnames: CSV文件的列名列表。如果为None，使用第一条记录的键。
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

            if fieldnames is None:
                fieldnames = list(self.test_results[0].keys())

            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in self.test_results:
                    writer.writerow(result)

            print(f"测试结果已保存到CSV文件: {filename}")
            return True

        except Exception as e:
            print(f"保存CSV文件失败: {e}")
            return False

    def save_results_to_excel(self, filename, summary_data=None):
        """保存测试结果到Excel文件

        Args:
            filename: 输出文件名
            summary_data: 摘要数据字典，可选
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

            df = pd.DataFrame(self.test_results)

            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                if summary_data is not None:
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='测试摘要', index=False)

                df.to_excel(writer, sheet_name='详细数据', index=False)

            print(f"测试结果已保存到Excel文件: {filename}")
            return True

        except ImportError:
            print("未安装pandas/openpyxl，无法保存为Excel格式")
            return False
        except Exception as e:
            print(f"保存Excel文件失败: {e}")
            return False

    def save_results(self, filename, csv_fieldnames=None, excel_summary_data=None):
        """根据文件扩展名保存测试结果

        Args:
            filename: 输出文件名
            csv_fieldnames: CSV文件的列名列表（保存为CSV时使用）
            excel_summary_data: Excel摘要数据（保存为Excel时使用）
        """
        if filename.lower().endswith('.xlsx') or filename.lower().endswith('.xls'):
            return self.save_results_to_excel(filename, excel_summary_data)
        else:
            if not filename.lower().endswith('.csv'):
                filename += '.csv'
            return self.save_results_to_csv(filename, csv_fieldnames)

    def start_csv_stream(self, csv_path, fieldnames):
        """开启 CSV 流式写入

        Args:
            csv_path: CSV 文件路径
            fieldnames: CSV 列名列表
        """
        from utils.csv_streamer import CsvStreamer
        self.csv_streamer = CsvStreamer(csv_path, fieldnames)

    def finish_xlsx(self, xlsx_path, summary_data=None, sheet_name="详细数据"):
        """关闭 CSV 流并转为 XLSX

        Args:
            xlsx_path: 目标 XLSX 路径
            summary_data: 可选的摘要数据字典
            sheet_name: 数据工作表名称
        """
        if not self.csv_streamer:
            return self.save_results(xlsx_path)
        self.csv_streamer.to_xlsx(xlsx_path, sheet_name=sheet_name, summary_data=summary_data)

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
            freq_col = None
            for candidate in ['frequency_hz', 'frequency', 'frequency_mhz']:
                if candidate in df.columns:
                    freq_col = candidate
                    break

            if freq_col:
                freq_values = df[freq_col]
                if freq_col == 'frequency_mhz':
                    freq_values = freq_values * 1e6
                print(f"频率范围: {format_frequency(freq_values.min())} - {format_frequency(freq_values.max())}")

            power_col = None
            for candidate in ['set_power_dbm', 'set_power', 'power']:
                if candidate in df.columns:
                    power_col = candidate
                    break
            if power_col:
                print(f"设置功率: {df[power_col].iloc[0]} dBm")
