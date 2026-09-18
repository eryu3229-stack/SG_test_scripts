# -*- coding: utf-8 -*-
"""模拟解调（AM / FM / PM）测量流程的公共基类。

三个测量的骨架完全一样，差异只有四处：

    1. 频谱仪的解调测量类型（AM / FM / PM）
    2. 信号源的调制设置（调幅深度 / 调频偏差 / 相位偏差）
    3. 从 `:FETC:<K>?` 结果表里取哪几个字段作为主指标
    4. 主指标的列名与判定容差

故公共逻辑放这里，三个子类只声明差异（参考 `procedures/power_sweep_base.py` 的做法）。

## 读数口径（与项目既有流程一致，勿另起一套）

- 读数走 `spectrum_analyzer.read_demod_metrics()`，它内部是
  `:INIT:CONT OFF` → `:INIT:IMM` → `*OPC?` → `:FETC:<K>?`。
  缺 `:INIT:IMM` 会读到上一轮残留结果 —— 与本项目 marker 哨兵缺陷同源。
- **重复采样 = N 次独立采集 + N 次读数，不是打开仪器平均。**
  仪器平均会让 N 次 FETC 返回同一个值，标准差恒为 0，重复性判据失效。
  故本流程固定 `:SENS:<K>:AVER:STAT OFF`（见配置 `sa_average_on`，默认 False）。

## 展开顺序

频率（外）→ 调制参数（中）→ 调制速率（内），每组合一行 CSV。
同一次运行的 `run_id` 全局唯一。

## 带宽为什么是算出来的

通道带宽不足会切掉调制边带，解调出来的深度/频偏低、THD 上升 ——
现象与"信号源调制不准"几乎一样，是最容易误判的一类问题。
故按物理公式算需求带宽（子类 `_occupied_bandwidth_hz`），再乘余量下发，
而不是拍一个固定值。AM 双边带 ≈ 2·fm；FM 用 Carson ≈ 2(Δf+fm)；
PM 调制指数 β=Δφ，Carson ≈ 2(β+1)·fm。
"""

import time
from datetime import datetime

from base_test_procedure import BaseTestProcedure, format_frequency


class AnalogDemodProcedureBase(BaseTestProcedure):
    """AM / FM / PM 模拟解调测量的公共骨架（子类只声明差异）。"""

    # ------------------------------------------------------------------
    # 子类必须声明
    # ------------------------------------------------------------------
    DEMOD_KIND = None          # "AM" / "FM" / "PM"
    TEST_TYPE = None           # CSV 的 test_type 列
    FIELDNAMES = []            # 列顺序（**结论优先**）

    # 主指标块的列名（A 区）
    PRIMARY_SET_COL = None         # 设定值
    PRIMARY_MEASURED_COL = None    # 实测值
    PRIMARY_PEAK_PLUS_COL = None   # 正峰
    PRIMARY_PEAK_MINUS_COL = None  # 负峰
    PRIMARY_DELTA_COL = None       # 实测 − 设定
    PRIMARY_REL_ERROR_COL = None   # 相对误差（%）
    PRIMARY_REF_COL = None         # 误差基准说明（恒 "set"）
    PRIMARY_IMBALANCE_COL = None   # 正负峰值不平衡
    PRIMARY_STD_COL = None         # 重复性标准差

    MOD_PARAM_UNIT = ""        # 打印用单位："%" / "Hz" / "rad"

    # 子类追加的 SA 条件列：{列名: read_demod_settings() 返回的键}
    EXTRA_SETTING_SOURCES = {}

    # 所有后端都有的 SA 条件列：{列名: read_demod_settings() 返回的键}
    COMMON_SETTING_SOURCES = {
        "sa_span_hz": "span_hz",
        "sa_rbw_hz": "rbw_hz",
        "sa_channel_bw_hz": "channel_bw_hz",
        "sa_af_stop_hz": "af_stop_hz",
        "sa_demod_time_s": "demod_time_s",
        "sa_af_unit": "af_unit",
    }

    #: 调制种类 -> 信号源开关方法名
    _MOD_SETTERS = {"AM": "enable_am", "FM": "enable_fm", "PM": "enable_pm"}

    #: 信号源侧**硬件互斥**关系：有且只有 FM ↔ PM 这一对。
    #: 依据：SMB100A 手册 p454"激活相位调制会关闭频率调制"（单向副作用，
    #: 关 PM 不会把 FM 开回来）。
    #:
    #: ⚠ **AM 不在此表中，这是有意的**：AM 与 FM/PM 之间**没有硬件互斥**，
    #: 信号源允许三者同时开启。所以测 AM 时**不下发、也不回读任何 FM/PM 指令**
    #: （用户 2026-09-18 要求"AM 完全不碰 FM/PM"，并追加"回读 PM 也没必要"）——
    #: 既不改动、也不去探问本测量用不到的开关状态。
    #: 代价：若上一轮/上一支脚本残留的 FM 还开着，AM 读数仍会被污染，
    #: 而程序**既不清除也不告警** —— 这是用户明确选择的口径：
    #: 终端里不出现任何与 AM 无关的状态行，比"顺手多看一眼"更重要。
    _HARDWARE_EXCLUSIVE = {"FM": ("PM",), "PM": ("FM",)}

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)
        self.test_results = []
        self.csv_streamer = None
        self.run_id = ""
        self._output_enabled = False
        # 已按 Meas Preset 初始化过的测量类型；只在"第一次"或"类型变了"时再复位，
        # 避免每个调制组合都白白复位一次（预设的意义只是给一个已知起点）。
        self._demod_ready_kind = None

    # ------------------------------------------------------------------
    # CSV 流式输出
    # ------------------------------------------------------------------
    def start_csv_stream(self, csv_path):
        from utils.csv_streamer import CsvStreamer
        self.run_id = self.derive_run_id(csv_path)
        self.csv_streamer = CsvStreamer(csv_path, self.FIELDNAMES)

    def finish_csv(self):
        if self.csv_streamer:
            self.csv_streamer.close()
            print(f"CSV流式存储已关闭: {self.csv_streamer.filepath}")

    def add_result(self, result):
        self.test_results.append(result)
        if self.csv_streamer:
            self.csv_streamer.append(result)

    def sort_results(self):
        self.test_results.sort(
            key=lambda row: (
                row["carrier_hz"] if row["carrier_hz"] is not None else 0.0,
                row[self.PRIMARY_SET_COL] if row[self.PRIMARY_SET_COL] is not None else 0.0,
                row["mod_rate_set_hz"] if row["mod_rate_set_hz"] is not None else 0.0,
            )
        )

    # ------------------------------------------------------------------
    # 带宽与时间的自动推导
    # ------------------------------------------------------------------
    def _occupied_bandwidth_hz(self, mod_param, mod_rate):
        """本调制方式所需的占用带宽（Hz）。子类必须实现。"""
        raise NotImplementedError

    def _suggest_channel_bw(self, mod_param, mod_rate, config):
        """解调通道带宽：显式配置优先，否则按占用带宽 × 余量。"""
        if config.get("channel_bw_hz"):
            return float(config["channel_bw_hz"])
        wanted = self._occupied_bandwidth_hz(mod_param, mod_rate) * float(
            config.get("channel_bw_margin_factor", 1.5))
        return max(wanted, float(config.get("min_channel_bw_hz", 8e3)))

    def _suggest_span(self, channel_bw, config):
        """RF 跨度：必须容得下通道带宽（仪器要求 通道带宽 ≤ 跨度）。"""
        if config.get("demod_span_hz"):
            return float(config["demod_span_hz"])
        return max(channel_bw * float(config.get("span_margin_factor", 1.5)),
                   float(config.get("min_demod_span_hz", 20e3)))

    def _suggest_af_stop(self, mod_rate, config):
        """AF 频谱上限：必须覆盖调制速率及其谐波，否则 SINAD/THD 被带宽截断。"""
        if config.get("af_stop_hz"):
            return float(config["af_stop_hz"])
        return max(float(config.get("af_span_margin", 20.0)) * mod_rate,
                   float(config.get("min_af_stop_hz", 20e3)))

    def _suggest_demod_time(self, mod_rate, config):
        """解调时间（秒）：保证记录内至少 N 个调制周期。

        手册 p366 明确提示："记录内少于 10 个调制周期"会让载波频率自动估计产生
        偏差，而 FM 的频率误差会给解调波形带来 DC 偏置，**直接影响 Peak+/Peak- 的
        读数**（也就是本流程要测的正负峰不平衡）。故取 20 个周期留一倍余量。
        """
        if config.get("demod_time_s"):
            return float(config["demod_time_s"])
        if not mod_rate or mod_rate <= 0:
            return None
        cycles = float(config.get("demod_time_cycles", 20.0))
        return max(cycles / mod_rate, float(config.get("min_demod_time_s", 0.01)))

    # ------------------------------------------------------------------
    # 信号源侧：调制设置
    # ------------------------------------------------------------------
    def _set_modulation(self, signal_generator, mod_param, mod_rate, config):
        """下发本测量的调制（子类必须实现）。返回 bool。"""
        raise NotImplementedError

    def _prepare_modulation(self, signal_generator, mod_param, mod_rate, config):
        """设置调制：先按**硬件互斥**关掉冲突的调制，再配内部 LF 源，最后下发本测量调制。

        关谁不关谁，只看 `_HARDWARE_EXCLUSIVE`（也就是只有 FM ↔ PM 这一对）：

        - 测 **FM** → 关 PM（手册 p454：激活 PM 会自动关掉 FM，不主动关就会在
          设 FM 之后被上一轮的 PM 状态吃掉）；
        - 测 **PM** → 关 FM（同上，反向）；
        - 测 **AM** → **不关、也不回读 FM/PM/PULM**。AM 与 FM/PM 没有硬件互斥
          关系，流程不去改动、也不去探问本测量用不到的开关状态
          （用户 2026-09-18 要求）。

        设置完**必须回读**：下发成功 ≠ 生效（本项目反复踩过的坑）。
        但回读范围严格限定为 **本调制自己 + 本次真正关过的那一个**：

        - 测 AM → 只读 AM，终端里不会出现任何 FM/PM 行；
        - 测 FM → 读 FM 与 PM（PM 是本次刚关掉的，要确认关闭真的生效）；
        - 测 PM → 读 PM 与 FM（同上）。
        """
        siblings = self._HARDWARE_EXCLUSIVE.get(self.DEMOD_KIND, ())
        for other in siblings:
            getattr(signal_generator, self._MOD_SETTERS[other])(False)

        signal_generator.set_lf_shape(config.get("lf_shape", "SINE"))
        signal_generator.set_lf_frequency(mod_rate)
        signal_generator.enable_lf_output(True)

        ok = bool(self._set_modulation(signal_generator, mod_param, mod_rate, config))
        if not ok:
            print("    信号源调制设置失败")
            return False

        if hasattr(signal_generator, "get_modulation_state"):
            state = signal_generator.get_modulation_state(
                kinds=(self.DEMOD_KIND,) + tuple(siblings)) or {}
            own = str(state.get(self.DEMOD_KIND) or "").strip()
            if own not in ("1", "ON"):
                print(f"    ⚠ {self.DEMOD_KIND} 调制回读为 {own!r}，未生效")
                return False
            for other in siblings:
                if str(state.get(other) or "").strip() in ("1", "ON"):
                    print(f"    ⚠ {other} 回读仍为开启：{self.DEMOD_KIND} 与 {other} "
                          f"硬件互斥，说明本次关闭未生效，读数不可信")
        return True

    # ------------------------------------------------------------------
    # 频谱仪侧：解调设置
    # ------------------------------------------------------------------
    def _apply_kind_specific(self, spectrum_analyzer, config):
        """按测量类型下发种类专属设置（AM 种类 / FM 去加重 / PM 单位）。"""
        if self.DEMOD_KIND == "AM" and config.get("am_genre"):
            spectrum_analyzer.set_am_genre(config["am_genre"])
        elif self.DEMOD_KIND == "FM" and config.get("fm_deemphasis"):
            spectrum_analyzer.set_fm_deemphasis(config["fm_deemphasis"])
        elif self.DEMOD_KIND == "PM" and config.get("pm_demod_unit"):
            # 只锁 DEMod 窗口单位（真机证实它决定 :FETC:PM? 的数值单位）
            spectrum_analyzer.set_demod_unit(config["pm_demod_unit"], window="DEMod")

    def _configure_demod_sa(self, spectrum_analyzer, carrier_frequency, config,
                            mod_param, mod_rate):
        """配置频谱仪解调测量，返回读回的**生效值**字典。

        顺序有讲究：
          1. 先切测量（ADEMOD 命令树只在该模式下存在），可选 Meas Preset；
          2. 再定载波频率 —— 它走 SA 模式节点 `SENS:FREQ:CENT`，且手册注明
             "retained as you go from measurement to measurement"，
             切测量后不重发就会沿用上一个频点；
          3. 通道带宽与跨度成对下发（仪器要求 通道带宽 ≤ 跨度，先算再夹逼）；
          4. 其余范围/时间类；
          5. 最后清一次错误队列 —— 被固件静默拒绝的命令只能从这里看出来。
        """
        kind = self.DEMOD_KIND

        # 只在第一次或测量类型变化时走 Meas Preset：预设给一个已知起点
        # （尤其把 `:DISP:<K>:VIEW:METR:MMAG` 复位到 ALL），之后每项都显式重设。
        preset = bool(config.get("demod_preset", True)) and (
            self._demod_ready_kind != kind)
        if not spectrum_analyzer.select_demod_measurement(kind, preset=preset):
            print(f"    切换到 {kind} 解调测量失败")
        self._demod_ready_kind = kind

        if hasattr(spectrum_analyzer, "set_demod_center_frequency"):
            spectrum_analyzer.set_demod_center_frequency(carrier_frequency)

        channel_bw = self._suggest_channel_bw(mod_param, mod_rate, config)
        span = self._suggest_span(channel_bw, config)
        if channel_bw > span:
            print(f"    通道带宽 {format_frequency(channel_bw)} > 跨度 "
                  f"{format_frequency(span)}，按跨度夹逼（仪器要求 通道带宽 ≤ 跨度）")
            channel_bw = span
        spectrum_analyzer.set_demod_span(span)
        spectrum_analyzer.set_demod_channel_bandwidth(channel_bw)

        if config.get("demod_rbw_hz"):
            spectrum_analyzer.set_demod_rbw(bandwidth=config["demod_rbw_hz"])
        if config.get("demod_rbw_auto", True):
            spectrum_analyzer.set_demod_rbw(auto=True)

        spectrum_analyzer.set_af_span(start_hz=config.get("af_start_hz", 0.0),
                                      stop_hz=self._suggest_af_stop(mod_rate, config))
        demod_time = self._suggest_demod_time(mod_rate, config)
        if demod_time:
            spectrum_analyzer.set_demod_time(seconds=demod_time)
        # 正弦周期调制 → 周期性标志置 1（仪器据此优化测量），默认也是 1，显式发更稳
        spectrum_analyzer.set_demod_periodic(True)
        spectrum_analyzer.set_demod_average(
            state=bool(config.get("sa_average_on", False)),
            count=config.get("sa_average_count"))
        self._apply_kind_specific(spectrum_analyzer, config)
        # 自动化测试不需要扬声器；它不影响读数，但避免现场出声（部分机型无此节点）
        if hasattr(spectrum_analyzer, "set_speaker"):
            spectrum_analyzer.set_speaker(False)

        time.sleep(config.get("sa_settling_time_s", 0.5))

        if hasattr(spectrum_analyzer, "report_error_queue"):
            spectrum_analyzer.report_error_queue(tag="解调设置后")
        return self._read_back_settings(spectrum_analyzer)

    def _read_back_settings(self, spectrum_analyzer):
        """读回解调设置（生效值）。记录"实际生效值"而不是"请求值"。"""
        handler = getattr(spectrum_analyzer, "read_demod_settings", None)
        actual = {}
        if handler is not None:
            actual = handler(self.DEMOD_KIND) or {}
        if hasattr(spectrum_analyzer, "read_demod_center_frequency"):
            center = spectrum_analyzer.read_demod_center_frequency()
            if center is not None:
                actual["center_hz"] = center
        return actual

    # ------------------------------------------------------------------
    # 采样与统计
    # ------------------------------------------------------------------
    def _sample(self, spectrum_analyzer, config):
        """N 次独立采集 + 读数，返回样本列表（失败的不计入但会打印）。"""
        target = max(1, int(config.get("repeat_count", 3)))
        samples = []
        for index in range(target):
            metrics = spectrum_analyzer.read_demod_metrics(self.DEMOD_KIND, acquire=True)
            if not metrics or metrics.get("error"):
                reason = metrics.get("error") if isinstance(metrics, dict) else "空结果"
                print(f"    第 {index + 1}/{target} 次读数失败: {reason}")
                continue
            samples.append(metrics)
        return samples

    @staticmethod
    def _mean_metrics(samples):
        """对 N 个样本逐字段取平均；非数值字段取第一个非空值。sample 为空返回 {}。"""
        if not samples:
            return {}
        keys = set()
        for sample in samples:
            keys.update(sample.keys())
        mean = {}
        for key in keys:
            if key == "raw":
                continue
            values = [s.get(key) for s in samples
                      if isinstance(s.get(key), (int, float))
                      and not isinstance(s.get(key), bool)]
            if len(values) == len(samples):
                mean[key] = sum(values) / len(values)
            else:
                mean[key] = next((s.get(key) for s in samples
                                  if s.get(key) is not None), None)
        # 保留第一份原始串，便于事后与仪器原始回值核对
        mean["raw"] = samples[0].get("raw")
        return mean

    @staticmethod
    def _std_of(samples, field):
        """样本标准差（n−1）。样本不足 2 个返回 None。

        用样本标准差而不是总体标准差：采样次数少（默认 3），
        总体标准差会系统性低估离散度，让重复性判据偏松。
        """
        values = [s.get(field) for s in samples
                  if isinstance(s.get(field), (int, float))
                  and not isinstance(s.get(field), bool)]
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return variance ** 0.5

    # ------------------------------------------------------------------
    # 判定
    # ------------------------------------------------------------------
    def _judge(self, primary, rate, samples, config, setting_note=None):
        """判定 status（OK / SUSPECT / SKIP）并拼 note。

        三态口径与项目其它流程一致：
            SKIP    —— 读数无效（无样本 / 主指标为 None），无法判定
            SUSPECT —— 有读数，但有任一项超出容差或指标异常
            OK      —— 全部通过
        """
        measured = primary.get(self.PRIMARY_MEASURED_COL)
        set_value = primary.get(self.PRIMARY_SET_COL)
        if measured is None or set_value in (None, 0):
            return "SKIP", (setting_note or "读数无效")

        flags = []
        rel = abs(primary.get(self.PRIMARY_DELTA_COL) or 0.0) / abs(set_value) * 100.0
        tol = float(config.get("param_tolerance_rel_pct", 5.0))
        if rel > tol:
            flags.append(f"{self.DEMOD_KIND} 主指标偏差 {rel:.2f}% 超 {tol:g}%")

        rate_tol = float(config.get("mod_rate_tolerance_rel_pct", 1.0))
        rate_delta = rate.get("delta")
        rate_set = rate.get("set")
        if rate_delta is None or not rate_set:
            flags.append("调制速率未读到")
        elif abs(rate_delta) / abs(rate_set) * 100.0 > rate_tol:
            flags.append(f"调制速率偏差 {abs(rate_delta) / abs(rate_set) * 100.0:.2f}% "
                         f"超 {rate_tol:g}%")

        sinad = primary.get("sinad_db")
        sinad_min = config.get("sinad_min_db")
        if sinad is not None and sinad_min is not None and sinad < float(sinad_min):
            flags.append(f"SINAD {sinad:.1f} dB 低于 {float(sinad_min):g} dB")

        std = primary.get(self.PRIMARY_STD_COL)
        if std is not None and abs(set_value) > 0:
            std_rel = std / abs(set_value) * 100.0
            limit = float(config.get("repeat_limit_rel_pct", 2.0))
            if std_rel > limit:
                flags.append(f"重复性 {std_rel:.2f}% 超 {limit:g}%")

        if setting_note:
            flags.append(setting_note)
        if not flags:
            return "OK", ""
        return "SUSPECT", "；".join(flags)

    # ------------------------------------------------------------------
    # 行组装
    # ------------------------------------------------------------------
    def _build_row(self, carrier_frequency, set_power, mod_param, mod_rate,
                   primary, rate, settings, status, note, repeat_count):
        """按 FIELDNAMES 组装一行；键集合不符直接抛错。

        为什么抛错而不是补 None：`csv.DictWriter` 遇到多余键本来就会抛
        `ValueError`，而缺键会静默写成空 —— 那是结构性缺陷，必须立刻暴露，
        不能让"列名写错"变成一份看起来正常的 CSV。
        """
        row = {
            # A 区：标识 + 结论
            "run_id": self.run_id,
            "test_type": self.TEST_TYPE,
            "carrier_hz": carrier_frequency,
            "set_power_dbm": set_power,
        }
        row.update(primary)
        row.update({
            "mod_rate_set_hz": mod_rate,
            "mod_rate_measured_hz": rate.get("measured"),
            "mod_rate_delta_hz": rate.get("delta"),
            "status": status,
            "note": note,
        })

        # B 区：频谱仪生效条件（读回值）
        row["sa_center_hz"] = settings.get("center_hz")
        for column, source_key in self.COMMON_SETTING_SOURCES.items():
            row[column] = settings.get(source_key)
        for column, source_key in self.EXTRA_SETTING_SOURCES.items():
            row[column] = settings.get(source_key)
        # 开关类回读是 "1"/"0"（真机实测），统一转成 true/false 才是给下游读的格式
        row["sa_average_on"] = self.bool_str(
            str(settings.get("average", "")).strip() in ("1", "ON"))
        row["sa_average_count"] = settings.get("average_count")
        row["sa_metric_display"] = settings.get("metric_display")

        # C 区：验证量
        row.update({
            "sinad_db": primary.get("sinad_db"),
            "thd_pct": primary.get("thd_pct"),
            "snr_db": primary.get("snr_db"),
            "carrier_power_dbm": primary.get("carrier_power_dbm"),
            "rf_center_hz": primary.get("rf_center_hz"),
            "repeat_count": repeat_count,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        missing = [key for key in self.FIELDNAMES if key not in row]
        extra = [key for key in row if key not in self.FIELDNAMES]
        if missing or extra:
            raise ValueError(
                f"{type(self).__name__} 结果行与 FIELDNAMES 不一致："
                f"缺少 {missing}；多余 {extra}")
        return {key: row[key] for key in self.FIELDNAMES}

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run_demod_test(self, signal_generator, spectrum_analyzer, carrier_frequency,
                       carrier_power, mod_param_list, mod_rate_list, config,
                       keep_output=False):
        """测一个载波频点：对 调制参数 × 调制速率 的每个组合各出一行。"""
        if not mod_param_list or not mod_rate_list:
            print(f"调制参数或速率列表为空，跳过 {format_frequency(carrier_frequency)}")
            return

        signal_generator.set_frequency(carrier_frequency)
        time.sleep(config.get("frequency_settling_time_s", 0.5))
        signal_generator.set_power(carrier_power)
        time.sleep(config.get("power_settling_time_s", 0.5))
        if not self._output_enabled:
            signal_generator.enable_output(True)
            self._output_enabled = True

        print(f"\n[载波 {format_frequency(carrier_frequency)}, {carrier_power} dBm] "
              f"开始 {self.DEMOD_KIND} 解调测量")

        total = len(mod_param_list) * len(mod_rate_list)
        index = 0
        for mod_param in mod_param_list:
            for mod_rate in mod_rate_list:
                index += 1
                print(f"  [{index}/{total}] 设定 {mod_param:g}{self.MOD_PARAM_UNIT}"
                      f" / 速率 {mod_rate:g} Hz")
                setting_note = ""
                if not self._prepare_modulation(signal_generator, mod_param,
                                                mod_rate, config):
                    setting_note = "信号源调制设置失败或未生效"
                time.sleep(config.get("source_settling_time_s", 0.5))

                settings = self._configure_demod_sa(
                    spectrum_analyzer, carrier_frequency, config, mod_param, mod_rate)

                # 「调制量度显示」不为 ALL 时，手册 p206 说其余量度会被装入
                # "not a number" —— 若固件对 FETC 走同一套计算，那些位置会回 NaN。
                # 只读不写（写它属 :DISPlay:* 子系统，驱动明确不做），但必须报出来。
                display = None
                if hasattr(spectrum_analyzer, "read_demod_metric_display"):
                    display = spectrum_analyzer.read_demod_metric_display(self.DEMOD_KIND)
                if display is not None and str(display).strip().upper() != "ALL":
                    print(f"    ⚠ 调制量度显示 = {display}（非 ALL），"
                          f"部分量度可能未被计算，读数需谨慎")
                    setting_note = (setting_note + "；" if setting_note else "") + \
                        f"量度显示={display}（非 ALL）"

                samples = self._sample(spectrum_analyzer, config)
                mean = self._mean_metrics(samples)
                primary = self._read_primary(mean if samples else None, mod_param)
                primary[self.PRIMARY_STD_COL] = self._std_of(
                    samples, self.SOURCE_MEASURED_FIELD)
                primary["sinad_db"] = mean.get("sinad_db")
                primary["thd_pct"] = mean.get("thd_pct")
                primary["snr_db"] = mean.get("snr_db")
                primary["carrier_power_dbm"] = mean.get("carrier_power_dbm")
                primary["rf_center_hz"] = mean.get("rf_center_hz")

                mod_rate_measured = mean.get("mod_rate_hz")
                rate = {
                    "set": mod_rate,
                    "measured": mod_rate_measured,
                    "delta": (None if mod_rate_measured is None
                              else mod_rate_measured - mod_rate),
                }
                if display is not None:
                    settings["metric_display"] = display

                status, note = self._judge(primary, rate, samples, config, setting_note)

                row = self._build_row(
                    carrier_frequency, carrier_power, mod_param, mod_rate,
                    primary, rate, settings, status, note, len(samples))
                self.add_result(row)

                print(f"    实测 {primary.get(self.PRIMARY_MEASURED_COL)}"
                      f"{self.MOD_PARAM_UNIT}"
                      f"（设定 {mod_param:g}，标准 {primary.get(self.PRIMARY_STD_COL)}）"
                      f"，速率 {mod_rate_measured} Hz"
                      f"，不平衡 {primary.get(self.PRIMARY_IMBALANCE_COL)}"
                      f"，样本 {len(samples)}，状态 {status}"
                      + (f"：{note}" if note else ""))

        if not keep_output:
            signal_generator.enable_output(False)
            self._output_enabled = False
