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

from utils.formatting import format_frequency


class MeasurementFailed(RuntimeError):
    """测量失败且重试耗尽——中止整轮测试，由入口脚本统一收尾（关 RF/关 CSV/断开仪器）。"""


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
        # 最近一次测量的尝试次数（1=首次成功，>1=重试后成功；供结果行 note 使用）
        self.last_measure_attempts = 0

    @staticmethod
    def format_frequency(frequency):
        """格式化频率显示（静态方法，方便子类调用）

        Args:
            frequency: 频率值，单位Hz
        Returns:
            str: 格式化后的频率字符串
        """
        return format_frequency(frequency)

    @staticmethod
    def bool_str(value):
        """布尔值统一以小写 true/false 输出；None → 空串

        Args:
            value: 任意真值
        Returns:
            str: "true" / "false" / ""
        """
        if value is None:
            return ""
        return "true" if value else "false"

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

        # 设置后立刻核对错误队列：某条品牌专有命令被固件拒绝时，
        # 只有这里能看出来（控制台打印的永远是请求值，不是生效值）
        if hasattr(spectrum_analyzer, 'report_error_queue'):
            spectrum_analyzer.report_error_queue(tag="设置后")

    def measure_fundamental_power(self, spectrum_analyzer, frequency, sa_config, average_count=3,
                                  attempts=3, retry_delay=0.3):
        """测量基波功率（读数失败自动重试）

        Args:
            spectrum_analyzer: 频谱仪对象
            frequency: 基波频率 (Hz)
            sa_config: 频谱仪配置
            average_count: 平均次数（= 独立单次采集次数）
            attempts: 最多尝试次数（1 次原始 + attempts-1 次重试）
            retry_delay: 两次尝试之间的等待秒数

        Returns:
            float: 基波功率 (dBm)；**全部尝试均失败时返回 None**，由调用方判 FAIL。
        """
        attempts = max(1, attempts)
        for attempt in range(1, attempts + 1):
            power = self._measure_fundamental_power_once(
                spectrum_analyzer, frequency, sa_config, average_count)
            self.last_measure_attempts = attempt
            if power is not None:
                if attempt > 1:
                    print(f"    基波测量第 {attempt} 次尝试成功")
                return power
            if attempt < attempts:
                print(f"    基波测量第 {attempt} 次尝试失败，{retry_delay}s 后重试...")
                time.sleep(retry_delay)
        print(f"基波功率测量失败（已尝试 {attempts} 次）")
        return None

    def _measure_fundamental_power_once(self, spectrum_analyzer, frequency, sa_config, average_count):
        """基波功率的单次尝试：配置 → 确定性采集（搜峰）→ N 次独立采集取平均。"""
        print(f"测量基波功率 @ {format_frequency(frequency)}")
        self.setup_spectrum_analyzer(spectrum_analyzer, frequency, sa_config)
        marker_num = 1

        # 1) 先完成一次完整采集（*OPC? 握手），搜峰必须在这条 trace 上进行
        if not self._acquire(spectrum_analyzer):
            return None

        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()
            time.sleep(0.05)
            # 搜峰后校验 marker 是否真的定位成功；无效则回退钉到理论基波频率
            if hasattr(spectrum_analyzer, 'get_marker_frequency'):
                pf = spectrum_analyzer.get_marker_frequency(marker_num)
                if pf is None and hasattr(spectrum_analyzer, 'set_marker_frequency'):
                    print("峰值搜索后 marker 频率无效，回退到理论基波频率")
                    spectrum_analyzer.set_marker_frequency(marker_num, frequency)
                    time.sleep(0.05)
        elif hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, frequency)
            time.sleep(0.05)

        # 2) N 次独立单次采集：每次采集完成后读一次 marker
        #    （marker 位置固定，不重复搜峰——否则样本会混入峰位抖动）
        measurements = []
        for _ in range(max(1, average_count)):
            if not self._acquire(spectrum_analyzer):
                continue
            measurement = self._read_marker(spectrum_analyzer, marker_num)
            if measurement is not None:
                measurements.append(measurement)

        if measurements:
            avg_power = sum(measurements) / len(measurements)
            print(f"基波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
            return avg_power
        print("基波功率测量失败（本轮读数全部无效）")
        return None

    @staticmethod
    def _acquire(spectrum_analyzer):
        """确定性采集一次完整扫描：优先 acquire_once()，旧接口回退 trigger_single()。"""
        for name in ("acquire_once", "trigger_single"):
            handler = getattr(spectrum_analyzer, name, None)
            if handler is not None:
                return bool(handler())
        time.sleep(0.3)  # 既无采集原语也无单次触发时退化为固定等待
        return False

    @staticmethod
    def _read_marker(spectrum_analyzer, marker_num):
        """读数前幂等开启 marker，再读标记点功率。"""
        if hasattr(spectrum_analyzer, 'ensure_marker_on'):
            spectrum_analyzer.ensure_marker_on(marker_num)
        if hasattr(spectrum_analyzer, 'measure_marker_power'):
            return spectrum_analyzer.measure_marker_power(marker_num)
        return spectrum_analyzer.measure_power()

    @staticmethod
    def _resolve_input_coupling(sa_config, frequency):
        """按频率与仪器能力，决定**实际下发**的输入耦合方式。

        默认逻辑：低于 `dc_coupling_below_hz` 用 DC（AC 耦合有低频截止，会压低
        低频读数），其余用 `input_coupling`。

        仪器能力约束：部分仪器（如本项目的 N9030B 配置）**只支持 DC 耦合**，
        下发 AC 会被固件拒绝并在错误队列里留一条 `-113 undefined header`。
        这类机器在配置里声明 `input_coupling_ac_supported: False` 即可：
        程序直接把 AC 折算成 DC，不再反复下发一条注定被拒的命令。
        该错误本身不影响读数（仪器保持 DC），但会污染错误队列诊断。

        Returns:
            (实际下发的耦合, 是否因仪器限制把 AC 折算成了 DC)
        """
        dc_below = sa_config.get('dc_coupling_below_hz', 10e6)
        requested = 'DC' if frequency < dc_below else sa_config.get('input_coupling', 'AC')
        if requested == 'AC' and not sa_config.get('input_coupling_ac_supported', True):
            return 'DC', True
        return requested, False

    @staticmethod
    def _estimate_noise_floor(trace):
        """用轨迹采样的中位数近似本地噪声底（dBm）。

        单音只占少量 bin，中位数几乎不受峰值影响；trace 为空返回 None。
        """
        if not trace:
            return None
        sorted_trace = sorted(trace)
        return sorted_trace[len(sorted_trace) // 2]

    def _read_noise_floor(self, spectrum_analyzer, trace_num=1):
        """读取当前 trace 并估计本地噪声底；读不到返回 None。

        调用前必须保证 trace 是按当前设置**刚采集**的（否则读到的是旧数据）。
        """
        if not hasattr(spectrum_analyzer, 'get_trace'):
            return None
        try:
            trace = spectrum_analyzer.get_trace(trace_num)
        except Exception as e:
            print(f"    读取噪声底失败: {e}")
            return None
        return self._estimate_noise_floor(trace)

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

    def derive_run_id(self, reference):
        """派生本次运行的 run_id（同一次运行的所有行共用同一值）

        Args:
            reference: 输出文件路径或任意可命名字符串
        Returns:
            str: 形如 "spurious_20260913_194010"
        """
        stem = os.path.splitext(os.path.basename(str(reference)))[0] or "run"
        return f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def save_results(self, filename, csv_fieldnames=None):
        """保存测试结果到 CSV（本工程只输出 CSV）

        Args:
            filename: 输出文件名（非 .csv 时自动补后缀）
            csv_fieldnames: CSV 列名列表（保存为 CSV 时使用）
        """
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

    def finish_csv(self):
        """关闭 CSV 流并 flush 落盘"""
        if self.csv_streamer:
            self.csv_streamer.close()
            print(f"CSV 已保存: {self.csv_streamer.filepath}")

    def print_summary(self):
        """打印测试摘要"""
        if not self.test_results:
            print("没有测试结果")
            return

        print(f"\n{'=' * 60}")
        print("测试摘要")
        print(f"{'=' * 60}")
        print(f"总测试点数: {len(self.test_results)}")

        rows = self.test_results
        if not rows:
            return

        # 频率范围：优先 carrier_hz，兼容旧键
        freq_key = None
        for candidate in ('carrier_hz', 'frequency_hz', 'frequency', 'frequency_mhz'):
            if candidate in rows[0]:
                freq_key = candidate
                break
        if freq_key:
            freqs = [r[freq_key] for r in rows if r.get(freq_key) is not None]
            if freqs:
                if freq_key == 'frequency_mhz':
                    freqs = [f * 1e6 for f in freqs]
                print(f"频率范围: {format_frequency(min(freqs))} - {format_frequency(max(freqs))}")

        # 设置功率
        for candidate in ('set_power_dbm', 'set_power', 'power'):
            if candidate in rows[0]:
                print(f"设置功率: {rows[0][candidate]} dBm")
                break
