#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础测试流程类
提供测试流程的公共功能
"""

import time
import csv
import os
from datetime import datetime
import pandas as pd


def format_frequency(frequency):
    """格式化频率显示，根据频率大小自动选择合适的单位

    Args:
        frequency: 频率值，单位Hz

    Returns:
        str: 格式化后的频率字符串
    """
    if frequency < 1e3:
        return f"{frequency:.0f}Hz"
    elif frequency < 1e6:
        return f"{frequency/1e3:.2f}kHz"
    elif frequency < 1e9:
        return f"{frequency/1e6:.2f}MHz"
    else:
        return f"{frequency/1e9:.2f}GHz"


class BaseTestProcedure:
    """基础测试流程类，提供公共功能"""

    def __init__(self, instrument_manager):
        """初始化测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        self.instrument_manager = instrument_manager
        self.test_results = []
        self.current_frequency = None
        self.current_power = None

    def setup_signal_generator(self, signal_gen, frequency, power, enable_output=True):
        """设置信号源

        Args:
            signal_gen: 信号源对象
            frequency: 频率 (Hz)
            power: 功率 (dBm)
            enable_output: 是否启用输出，默认为True
        """
        print(f"设置信号源: {format_frequency(frequency)}, {power}dBm")

        # 设置频率
        signal_gen.set_frequency(frequency)

        # 设置功率
        signal_gen.set_power(power)

        # 启用输出
        if enable_output:
            signal_gen.enable_output(True)
            print("信号源输出已启用")
        else:
            print("保持信号源输出状态")

        self.current_frequency = frequency
        self.current_power = power

    def setup_spectrum_analyzer(self, spectrum_analyzer, center_frequency, config):
        """设置频谱仪 - 基础版本

        Args:
            spectrum_analyzer: 频谱仪对象
            center_frequency: 中心频率 (Hz)
            config: 频谱仪配置字典
        """
        print(f"设置频谱仪中心频率: {format_frequency(center_frequency)}")

        # 获取频谱仪稳定时间
        sa_settling_time = config.get('sa_settling_time', 0.5)

        # 设置中心频率
        spectrum_analyzer.set_center_frequency(center_frequency)

        # SPAN设置：从配置中获取，如未提供则使用默认值
        span = config.get('span', 1e6)  # 默认1MHz
        print(f"使用配置SPAN: {format_frequency(span)}")

        # RBW设置：从配置中获取，如未提供则使用默认值
        rbw = config.get('rbw', 1e3)  # 默认1kHz
        print(f"使用配置RBW: {format_frequency(rbw)}")

        # 设置频率跨度
        spectrum_analyzer.set_span(span)

        # 设置参考电平：从配置中获取，如未提供则使用默认值
        reference_level = config.get('reference_level', 10)  # 默认10dBm
        spectrum_analyzer.set_reference_level(reference_level)

        # 设置分辨率带宽
        if hasattr(spectrum_analyzer, 'set_rbw'):
            spectrum_analyzer.set_rbw(rbw)

        # 设置视频带宽：从配置中获取，如未提供则使用默认值
        vbw = config.get('vbw', 100e3)  # 默认100kHz
        print(f"使用配置VBW: {format_frequency(vbw)}")

        if hasattr(spectrum_analyzer, 'set_vbw'):
            spectrum_analyzer.set_vbw(vbw)

        # 设置衰减
        if hasattr(spectrum_analyzer, 'set_attenuation'):
            attenuation = config.get('attenuation', 10)  # 默认10dB
            spectrum_analyzer.set_attenuation(attenuation)
            print(f"设置衰减: {attenuation} dB")

        # 设置扫描时间
        if hasattr(spectrum_analyzer, 'set_sweep_time'):
            sweep_time = config.get('sweep_time', 1)  # 默认1秒
            spectrum_analyzer.set_sweep_time(sweep_time)
            print(f"设置扫描时间: {sweep_time}秒")

        # 等待设置生效
        print(f"等待频谱仪设置生效 {sa_settling_time}秒...")
        time.sleep(sa_settling_time)

    def measure_fundamental_power(self, spectrum_analyzer, frequency, sa_config, harmonic_config=None):
        """测量基波功率

        Args:
            spectrum_analyzer: 频谱仪对象
            frequency: 基波频率 (Hz)
            sa_config: 频谱仪配置
            harmonic_config: 谐波测量配置（可选）

        Returns:
            float: 基波功率 (dBm)
        """
        print(f"测量基波功率 @ {format_frequency(frequency)}")

        # 设置中心频率为基波频率
        self.setup_spectrum_analyzer(spectrum_analyzer, frequency, sa_config)

        # 执行峰值搜索
        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()

        # 使用配置的标记器编号，默认为1
        if harmonic_config and 'fundamental_marker' in harmonic_config:
            marker_num = harmonic_config['fundamental_marker']
        else:
            marker_num = 1
        print(f"使用标记器{marker_num}测量基波功率")

        # 如果配置了谐波搜索偏移，设置搜索范围
        if harmonic_config and 'harmonic_search_offset' in harmonic_config:
            search_offset = harmonic_config['harmonic_search_offset']
            left_freq = frequency - search_offset
            right_freq = frequency + search_offset
            if hasattr(spectrum_analyzer, 'set_search_frequency_limits'):
                spectrum_analyzer.set_search_frequency_limits(left_freq, right_freq, marker_num=marker_num)
                print(f"设置基波搜索范围: {format_frequency(left_freq)} 到 {format_frequency(right_freq)}")

        # 设置标记器到中心频率
        if hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, frequency)

        # 测量标记器功率
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            power = spectrum_analyzer.measure_marker_power(marker_num)
        else:
            # 备用方法：使用通用功率测量
            power = spectrum_analyzer.measure_power()

        # 多次测量取平均，优先使用谐波配置中的设置
        if harmonic_config and 'measurement_average' in harmonic_config:
            average_count = harmonic_config['measurement_average']
        else:
            average_count = sa_config.get('measurement_average', 3)

        print(f"测量平均次数: {average_count}")
        measurements = []

        for i in range(average_count):
            if hasattr(spectrum_analyzer, 'measure_marker_power'):
                measurement = spectrum_analyzer.measure_marker_power(marker_num)
            else:
                measurement = spectrum_analyzer.measure_power()

            if measurement is not None:
                measurements.append(measurement)
            time.sleep(0.1)

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

    def save_results_to_csv(self, filename, fieldnames):
        """保存测试结果到CSV文件

        Args:
            filename: 输出文件名
            fieldnames: CSV文件的列名列表
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

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

    def save_results_to_excel(self, filename, summary_data):
        """保存测试结果到Excel文件

        Args:
            filename: 输出文件名
            summary_data: 摘要数据字典
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return False

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

            # 转换为DataFrame
            df = pd.DataFrame(self.test_results)

            # 创建摘要DataFrame
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

    def save_results(self, filename, csv_fieldnames=None, excel_summary_data=None):
        """根据文件扩展名保存测试结果

        Args:
            filename: 输出文件名
            csv_fieldnames: CSV文件的列名列表（保存为CSV时使用）
            excel_summary_data: Excel摘要数据（保存为Excel时使用）
        """
        if filename.lower().endswith('.xlsx') or filename.lower().endswith('.xls'):
            if excel_summary_data is None:
                print("警告: 保存为Excel格式但未提供摘要数据")
                return False
            return self.save_results_to_excel(filename, excel_summary_data)
        else:
            # 默认保存为CSV
            if not filename.lower().endswith('.csv'):
                filename += '.csv'
            if csv_fieldnames is None:
                print("警告: 保存为CSV格式但未提供列名")
                return False
            return self.save_results_to_csv(filename, csv_fieldnames)

    def print_summary(self, harmonic_info):
        """打印测试摘要

        Args:
            harmonic_info: 谐波信息字典，包含谐波阶数和对应的列名
        """
        if not self.test_results:
            print("没有测试结果")
            return

        print(f"\n{'=' * 60}")
        print("测试摘要")
        print(f"{'=' * 60}")

        df = pd.DataFrame(self.test_results) if self.test_results else None

        print(f"总测试点数: {len(self.test_results)}")

        if df is not None and not df.empty:
            print(f"频率范围: {format_frequency(df['frequency_hz'].min())} - {format_frequency(df['frequency_hz'].max())}")
            print(f"设置功率: {df['set_power_dbm'].iloc[0]} dBm")

            # 打印各谐波摘要
            for order, col_info in harmonic_info.items():
                power_col = col_info['power']
                suppression_col = col_info['suppression']
                name = col_info['name']

                if not df[power_col].isnull().all():
                    print(f"\n{name}:")
                    if not df[suppression_col].isnull().all():
                        print(f"  平均谐波抑制: {df[suppression_col].mean():.2f} dBc")
                        print(
                            f"  最佳谐波抑制: {df[suppression_col].min():.2f} dBc @ {format_frequency(df.loc[df[suppression_col].idxmin(), 'frequency_hz'])}")
                        print(
                            f"  最差谐波抑制: {df[suppression_col].max():.2f} dBc @ {format_frequency(df.loc[df[suppression_col].idxmax(), 'frequency_hz'])}")
