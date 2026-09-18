#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分谐波测试流程类
用于执行信号源的分谐波测试
"""

import time
from datetime import datetime
from base_test_procedure import BaseTestProcedure, MeasurementFailed


class SubharmonicTestProcedure(BaseTestProcedure):
    """分谐波测试流程类（长表：每 (基波频率, 阶数) 一行）"""

    TEST_TYPE = "subharmonic"

    FIELDNAMES = [
        # A 区：标识与数值
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
        # B 区：频谱仪采集条件
        "sa_ref_level_dbm", "sa_input_att_db", "sa_att_mode",
        "sa_span_hz", "sa_rbw_hz", "sa_vbw_hz", "sa_noise_floor_dbm",
        # C 区：源专有
        "subharmonic_order", "subharmonic_freq_hz", "fundamental_power_dbm",
        # 判定与时间
        "status", "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        """初始化分谐波测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)
        self.run_id = ""
        self._floor_rows = 0   # 本轮里"读数为底噪"（未检出分谐波）的行数

    def measure_subharmonic_power(self, spectrum_analyzer, fundamental_freq, subharmonic_order,
                                  sa_config, average_count=3, attempts=3, retry_delay=0.3):
        """测量分谐波功率（读数失败自动重试）

        Args:
            spectrum_analyzer: 频谱仪对象
            fundamental_freq: 基波频率 (Hz)
            subharmonic_order: 分谐波阶数
            sa_config: 频谱仪配置
            average_count: 平均次数（= 独立单次采集次数）
            attempts: 最多尝试次数（1 次原始 + attempts-1 次重试）
            retry_delay: 两次尝试之间的等待秒数

        Returns:
            dict: {"power": 分谐波功率/底噪(dBm) 或 None,
                   "detected": 是否检出分谐波,
                   "noise_floor": 本地噪声底(dBm) 或 None,
                   "attempts": 实际尝试次数}
        """
        attempts = max(1, attempts)
        for attempt in range(1, attempts + 1):
            result = self._measure_subharmonic_power_once(
                spectrum_analyzer, fundamental_freq, subharmonic_order, sa_config,
                average_count)
            result["attempts"] = attempt
            if result["power"] is not None:
                if attempt > 1:
                    print(f"    1/{subharmonic_order}分谐波测量第 {attempt} 次尝试成功")
                return result
            if attempt < attempts:
                print(f"    1/{subharmonic_order}分谐波测量第 {attempt} 次尝试失败，{retry_delay}s 后重试...")
                time.sleep(retry_delay)
        print(f"1/{subharmonic_order}分谐波功率测量失败（已尝试 {attempts} 次）")
        return result

    def _measure_subharmonic_power_once(self, spectrum_analyzer, fundamental_freq, subharmonic_order,
                                        sa_config, average_count=3):
        """分谐波功率的单次尝试：配置 → 确定性采集（搜峰）→ N 次独立采集取平均。"""
        subharmonic_freq = fundamental_freq / subharmonic_order
        print(f"测量1/{subharmonic_order}分谐波功率 @ {self.format_frequency(subharmonic_freq)}")

        self.setup_spectrum_analyzer(spectrum_analyzer, subharmonic_freq, sa_config)
        # 确定性采集一次完整扫描（*OPC? 握手）；搜峰必须在这条 trace 上进行
        if not self._acquire(spectrum_analyzer):
            return {'power': None, 'detected': False, 'noise_floor': None}

        marker_num = 1

        # 先搜峰并记下峰位（用于"检出/未检出"判定的频率一侧），
        # 再把 marker 钉到理论分谐波频率读数——分谐波只可能出现在 f×m/n 上，
        # 按理论频率读数比跟随噪声峰更可靠。
        peak_frequency = None
        if hasattr(spectrum_analyzer, 'peak_search'):
            spectrum_analyzer.peak_search()
            time.sleep(0.05)
            if hasattr(spectrum_analyzer, 'get_marker_frequency'):
                peak_frequency = spectrum_analyzer.get_marker_frequency(marker_num)

        if hasattr(spectrum_analyzer, 'set_marker_frequency'):
            spectrum_analyzer.set_marker_frequency(marker_num, subharmonic_freq)
            time.sleep(0.05)

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
            print(f"1/{subharmonic_order}分谐波功率: {avg_power:.2f} dBm (平均{len(measurements)}次)")
        else:
            print(f"1/{subharmonic_order}分谐波功率测量失败（本轮读数全部无效）")
            return {'power': None, 'detected': False, 'noise_floor': None}

        # 本地噪声底（trace 中位数）——刚采集完，此处有效；用于"检出/未检出"的电平判据，
        # 同时写入 sa_noise_floor_dbm 列，让"该行读的是底噪"这件事可被追溯
        noise_floor = self._read_noise_floor(spectrum_analyzer, 1)

        # 检出判据与谐波一致：频率需落在理论分谐波附近（按 span 截断），
        # 且电平需明显高于本地噪声底，否则视为"没测到、读数为底噪"
        span = sa_config.get('span', 10e3)
        rbw = sa_config.get('rbw', 100)
        margin = sa_config.get('subharmonic_detection_margin_db', 10)
        tol = max(span * sa_config.get('subharmonic_freq_tolerance_ratio', 0.25), rbw * 5, 500.0)
        frequency_ok = peak_frequency is not None and abs(peak_frequency - subharmonic_freq) <= tol
        if noise_floor is None:
            level_ok = True      # 取不到底噪时不做电平判定，避免误判成"未检出"
        else:
            level_ok = (avg_power - noise_floor) >= margin
        detected = frequency_ok and level_ok

        if detected:
            print(f"检出1/{subharmonic_order}分谐波，频率: {self.format_frequency(peak_frequency)}"
                  f" (理论: {self.format_frequency(subharmonic_freq)})")
        else:
            floor_txt = f"约{noise_floor:.1f}dBm" if noise_floor is not None else "未知"
            print(f"未检出1/{subharmonic_order}分谐波，读数按底噪处理（本地底噪{floor_txt}）")

        return {'power': avg_power, 'detected': detected, 'noise_floor': noise_floor}

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
        print(f"开始测试: {self.format_frequency(frequency)}")
        print(f"{'=' * 60}")

        # 1. 设置信号源（使用基类方法）
        self.setup_signal_generator(signal_gen, frequency, set_power, settling_time=0)
        time.sleep(settling_time)

        # 输入耦合判断：低于阈值用 DC（AC 耦合有低频截止，会严重压低低频读数）。
        # 按基波频率判断、每个测试点只设一次，使基波与分谐波测量使用同一耦合，避免 dBc 被耦合切换影响。
        # 仪器只支持 DC 时按能力折算（见 _resolve_input_coupling），不再下发注定被拒的 AC。
        coupling, folded_from_ac = self._resolve_input_coupling(sa_config, frequency)
        if hasattr(spectrum_analyzer, 'set_input_coupling'):
            spectrum_analyzer.set_input_coupling(coupling)
            extra = "（配置要 AC，但仪器只支持 DC，已用 DC）" if folded_from_ac else ""
            print(f"频谱仪输入耦合: {coupling} (基波 {self.format_frequency(frequency)}){extra}")

        # 2. 测量基波功率（内部含重试）
        average_count = subharmonic_config.get('measurement_average', 3)
        max_attempts = subharmonic_config.get('measurement_attempts', 3)
        retry_delay = subharmonic_config.get('retry_delay_s', 0.3)
        fundamental_power = self.measure_fundamental_power(
            spectrum_analyzer, frequency, sa_config,
            average_count=average_count, attempts=max_attempts, retry_delay=retry_delay
        )
        fundamental_attempts = self.last_measure_attempts

        # 3. 测量分谐波功率（内部含重试）
        subharmonic_orders = subharmonic_config.get('subharmonic_orders', [2])
        subharmonic_powers = {}
        subharmonic_suppressions = {}
        subharmonic_attempts = {}
        subharmonic_detected = {}
        subharmonic_floors = {}

        for order in subharmonic_orders:
            sh_result = self.measure_subharmonic_power(
                spectrum_analyzer, frequency, order, sa_config,
                average_count=average_count, attempts=max_attempts, retry_delay=retry_delay
            )
            subharmonic_power = sh_result['power']
            sh_attempts = sh_result['attempts']
            subharmonic_powers[order] = subharmonic_power
            subharmonic_attempts[order] = sh_attempts
            subharmonic_detected[order] = sh_result['detected']
            subharmonic_floors[order] = sh_result['noise_floor']

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

        # 创建测试结果（长表：每 (基波频率, 阶数) 一行）
        sa_ref_level = sa_config.get('reference_level', 10)
        sa_att = sa_config.get('attenuation', 10)
        results = []
        failure_notes = []
        if fundamental_power is None:
            failure_notes.append(f"基波功率测量失败（尝试 {fundamental_attempts} 次）")
        for order in subharmonic_orders:
            sh_power = subharmonic_powers[order]
            sh_suppression = subharmonic_suppressions[order]
            attempts_used = subharmonic_attempts.get(order, 0)
            sh_detected = subharmonic_detected.get(order, False)
            if fundamental_power is None:
                status = "FAIL"
                note = f"基波功率测量失败（尝试 {fundamental_attempts} 次），无法计算 dBc"
            elif sh_power is None:
                status = "FAIL"
                note = f"分谐波功率测量失败（尝试 {attempts_used} 次）"
                failure_notes.append(f"1/{order}分谐波功率测量失败（尝试 {attempts_used} 次）")
            else:
                status = "OK"
                note_parts = []
                # 底噪读数必须标注：分谐波测不到是常态，此时 dBc 应按上限理解
                if sh_detected:
                    note_parts.append(f"检出1/{order}分谐波")
                else:
                    floor_txt = (f"约{subharmonic_floors[order]:.1f}dBm"
                                 if subharmonic_floors[order] is not None else "见 sa_noise_floor_dbm")
                    note_parts.append(f"读数为分谐波频率处底噪（未检出1/{order}分谐波，{floor_txt}；"
                                      f"dBc 按上限理解）")
                    self._floor_rows += 1
                if fundamental_attempts > 1:
                    note_parts.append(f"基波重试{fundamental_attempts - 1}次后成功")
                if attempts_used > 1:
                    note_parts.append(f"分谐波重试{attempts_used - 1}次后成功")
                note = "；".join(note_parts)

            row = {
                # A 区：标识与数值
                "run_id": getattr(self, "run_id", ""),
                "test_type": self.TEST_TYPE,
                "carrier_hz": frequency,
                "set_power_dbm": set_power,
                "measured_power_dbm": sh_power,
                "delta_db": None if sh_suppression is None else round(sh_suppression, 3),
                "delta_ref": "fundamental",
                # B 区：频谱仪采集条件
                "sa_ref_level_dbm": sa_ref_level,
                "sa_input_att_db": sa_att,
                "sa_att_mode": "manual",
                "sa_span_hz": sa_config.get('span', 10e6),
                "sa_rbw_hz": sa_config.get('rbw', 100e3),
                "sa_vbw_hz": sa_config.get('vbw', 100e3),
                "sa_noise_floor_dbm": subharmonic_floors.get(order),
                # C 区：源专有
                "subharmonic_order": order,
                "subharmonic_freq_hz": frequency / order,
                "fundamental_power_dbm": fundamental_power,
                # 判定与时间
                "status": status,
                "note": note,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            results.append(row)
            self.test_results.append(row)
            if self.csv_streamer:
                self.csv_streamer.append(row)

        print(f"测试完成: {self.format_frequency(frequency)}")
        print(f"基波功率: {fundamental_power:.2f} dBm" if fundamental_power is not None else "基波功率: 测量失败")
        for order in subharmonic_orders:
            sh_value = subharmonic_powers[order]
            print(f"1/{order}分谐波功率: {sh_value:.2f} dBm" if sh_value is not None
                  else f"1/{order}分谐波功率: 测量失败")
            if subharmonic_suppressions[order] is not None:
                print(f"分谐波抑制: {subharmonic_suppressions[order]:.2f} dBc")

        # 失败 → 该行已判 FAIL 并写入 CSV（留证据），此处显式中止整轮测试
        if failure_notes:
            signal_gen.enable_output(False)
            raise MeasurementFailed(
                f"{self.format_frequency(frequency)}: {'；'.join(failure_notes)}，测试中止")

        return results

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        self.run_id = self.derive_run_id(csv_path)
        super().start_csv_stream(csv_path, self.FIELDNAMES)

    def print_summary(self):
        """打印测试摘要（分谐波专项）"""
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

        # 按阶数分组统计平均抑制比
        by_order = {}
        for r in rows:
            order = r.get("subharmonic_order")
            if r.get("delta_db") is not None:
                by_order.setdefault(order, []).append(r["delta_db"])
        for order in sorted(by_order, key=lambda o: (o is None, o)):
            values = by_order[order]
            avg = sum(values) / len(values)
            print(f"平均1/{order}分谐波抑制: {avg:.2f} dBc ({len(values)} 点)")

        # 分谐波大多落在底噪里（未检出是常态），这里的 dBc 是"读数 − 基波实测"，
        # 对未检出的点应按**抑制上限**理解，不能当作真实抑制能力。
        floor_rows = getattr(self, "_floor_rows", 0)
        if floor_rows:
            print(f"注: {floor_rows}/{len(rows)} 点为底噪读数（未检出分谐波），"
                  f"其 dBc 应按上限理解（优于该值），非真实抑制量")
        print(f"{'=' * 60}")
