# -*- coding: utf-8 -*-
"""FM（频率调制）测量流程。

公共骨架（设置 / 采集 / 读数 / 判定 / 落盘）在 `analog_demod_base.py`，
本文件只声明 FM 的差异。

要读的量（用户 2026-09-18 定案）：**频偏 + 调制速率 + 正负峰值不平衡**。

频偏取 `(Pk-Pk)/2`（FM 结果表第 10 项）；`(Peak+)` / `(Peak-)` 另列。
手册 p366 提示：载波频率误差会给解调波形引入 **DC 偏置**，而这个 DC 项
**直接影响 Peak+/Peak-** 的读数 —— 所以"正负峰不平衡"在本测量里同时是
频偏精度的旁证：不平衡明显偏大，先查载波频率与解调时间够不够，
再怀疑信号源。

⚠ FM 与 PM 在信号源侧**硬件互斥**（手册 p454：激活 PM 会关闭 FM）。基类每次设
  调制前会显式关掉 **PM** —— **只关 PM，不关 AM**。AM 与 FM 没有互斥关系，
  流程不替用户改动本测量用不到的开关状态（用户 2026-09-18 要求）；
  残留的 AM 只由回读告警提示，不会主动清理。
"""

from analog_demod_base import AnalogDemodProcedureBase


class FmDemodProcedure(AnalogDemodProcedureBase):
    """FM 解调测量流程。"""

    TEST_TYPE = "fm_demod"
    DEMOD_KIND = "FM"
    MOD_PARAM_UNIT = "Hz"

    # 列顺序原则：**结论优先**
    FIELDNAMES = [
        # A 区：标识 + 结论（频偏 → 误差 → 不平衡 → 速率 → 判定）
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "fm_deviation_set_hz", "fm_deviation_measured_hz",
        "deviation_peak_plus_hz", "deviation_peak_minus_hz",
        "deviation_delta_hz", "deviation_rel_error_pct", "deviation_ref",
        "deviation_imbalance_hz",
        "mod_rate_set_hz", "mod_rate_measured_hz", "mod_rate_delta_hz",
        "status", "note",
        # B 区：频谱仪解调条件（读回的生效值）
        "sa_center_hz", "sa_span_hz", "sa_rbw_hz", "sa_channel_bw_hz",
        "sa_af_stop_hz", "sa_demod_time_s",
        "sa_average_on", "sa_average_count", "sa_fm_deemphasis",
        "sa_af_unit", "sa_metric_display",
        # C 区：验证量
        "sinad_db", "thd_pct", "snr_db", "carrier_power_dbm", "rf_center_hz",
        "repeat_count", "deviation_std_hz", "timestamp",
    ]

    PRIMARY_SET_COL = "fm_deviation_set_hz"
    PRIMARY_MEASURED_COL = "fm_deviation_measured_hz"
    PRIMARY_PEAK_PLUS_COL = "deviation_peak_plus_hz"
    PRIMARY_PEAK_MINUS_COL = "deviation_peak_minus_hz"
    PRIMARY_DELTA_COL = "deviation_delta_hz"
    PRIMARY_REL_ERROR_COL = "deviation_rel_error_pct"
    PRIMARY_REF_COL = "deviation_ref"
    PRIMARY_IMBALANCE_COL = "deviation_imbalance_hz"
    PRIMARY_STD_COL = "deviation_std_hz"

    # `:FETC:FM?`（16 项）里对应的字段名
    SOURCE_MEASURED_FIELD = "deviation_half_pkpk_hz"
    SOURCE_PEAK_PLUS_FIELD = "deviation_peak_plus_hz"
    SOURCE_PEAK_MINUS_FIELD = "deviation_peak_minus_hz"
    SOURCE_IMBALANCE_FIELD = "deviation_imbalance_hz"

    EXTRA_SETTING_SOURCES = {"sa_fm_deemphasis": "fm_deemphasis"}

    def _occupied_bandwidth_hz(self, mod_param, mod_rate):
        """FM 按 Carson 带宽：BW ≈ 2 × (Δf + fm)。

        通道带宽不足会切掉边带 → 解调出来的频偏偏低、THD 上升，
        现象与"信号源频偏不准"几乎一样，是最容易误判的一类问题。
        """
        return 2.0 * (mod_param + mod_rate)

    def _set_modulation(self, signal_generator, mod_param, mod_rate, config):
        """设 FM 频偏并开启 FM：`SOUR:FM1:SOUR` → `:DEV` → `:STAT ON`。"""
        ok_source = signal_generator.set_fm_source(config.get("mod_source", "LF1"))
        ok_dev = signal_generator.set_fm_deviation(mod_param)
        ok_on = signal_generator.enable_fm(True)
        return bool(ok_source and ok_dev and ok_on)

    def _read_primary(self, metrics, mod_param):
        if not metrics:
            return {
                self.PRIMARY_SET_COL: mod_param,
                self.PRIMARY_MEASURED_COL: None,
                self.PRIMARY_PEAK_PLUS_COL: None,
                self.PRIMARY_PEAK_MINUS_COL: None,
                self.PRIMARY_DELTA_COL: None,
                self.PRIMARY_REL_ERROR_COL: None,
                self.PRIMARY_REF_COL: "set",
                self.PRIMARY_IMBALANCE_COL: None,
            }
        measured = metrics.get(self.SOURCE_MEASURED_FIELD)
        delta = None if measured is None else measured - mod_param
        rel = None if (delta is None or not mod_param) else delta / mod_param * 100.0
        return {
            self.PRIMARY_SET_COL: mod_param,
            self.PRIMARY_MEASURED_COL: measured,
            self.PRIMARY_PEAK_PLUS_COL: metrics.get(self.SOURCE_PEAK_PLUS_FIELD),
            self.PRIMARY_PEAK_MINUS_COL: metrics.get(self.SOURCE_PEAK_MINUS_FIELD),
            self.PRIMARY_DELTA_COL: delta,
            self.PRIMARY_REL_ERROR_COL: rel,
            self.PRIMARY_REF_COL: "set",
            self.PRIMARY_IMBALANCE_COL: metrics.get(self.SOURCE_IMBALANCE_FIELD),
        }
