# -*- coding: utf-8 -*-
"""AM（幅度调制）测量流程。

公共骨架（设置 / 采集 / 读数 / 判定 / 落盘）在 `analog_demod_base.py`，
本文件只声明 AM 的差异：测什么、怎么设、取哪些字段、容差多少。

要读的量（用户 2026-09-18 定案）：**调制深度 + 调制速率 + 正负峰值不平衡**。

深度取 `(Pk-Pk)/2`（手册 p157 结果表第 10 项），它是 AM 深度的标准定义；
`(Peak+)` / `(Peak-)` 另列，两者之差即正负峰值不平衡
（不对称调制、残留载波泄漏、解调器 DC 偏置都会表现在这个差上）。
"""

from analog_demod_base import AnalogDemodProcedureBase


class AmDemodProcedure(AnalogDemodProcedureBase):
    """AM 解调测量流程。"""

    TEST_TYPE = "am_demod"
    DEMOD_KIND = "AM"
    MOD_PARAM_UNIT = "%"

    # 列顺序原则：**结论优先** —— 设定/实测/误差/判定紧跟运行标识，
    # 打开 CSV 不用横向滚动就能读结论；采集条件与验证量一律后置。
    FIELDNAMES = [
        # A 区：标识 + 结论（深度 → 误差 → 不平衡 → 速率 → 判定）
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "am_depth_set_pct", "am_depth_measured_pct",
        "depth_peak_plus_pct", "depth_peak_minus_pct",
        "depth_delta_pct", "depth_rel_error_pct", "depth_ref",
        "depth_imbalance_pct",
        "mod_rate_set_hz", "mod_rate_measured_hz", "mod_rate_delta_hz",
        "status", "note",
        # B 区：频谱仪解调条件（读回的生效值，不是请求值）
        "sa_center_hz", "sa_span_hz", "sa_rbw_hz", "sa_channel_bw_hz",
        "sa_af_stop_hz", "sa_demod_time_s",
        "sa_average_on", "sa_average_count", "sa_am_genre",
        "sa_af_unit", "sa_metric_display",
        # C 区：验证量（结论可信度）
        "sinad_db", "thd_pct", "snr_db", "carrier_power_dbm", "rf_center_hz",
        "repeat_count", "depth_std_pct", "timestamp",
    ]

    # 主指标块列名
    PRIMARY_SET_COL = "am_depth_set_pct"
    PRIMARY_MEASURED_COL = "am_depth_measured_pct"
    PRIMARY_PEAK_PLUS_COL = "depth_peak_plus_pct"
    PRIMARY_PEAK_MINUS_COL = "depth_peak_minus_pct"
    PRIMARY_DELTA_COL = "depth_delta_pct"
    PRIMARY_REL_ERROR_COL = "depth_rel_error_pct"
    PRIMARY_REF_COL = "depth_ref"
    PRIMARY_IMBALANCE_COL = "depth_imbalance_pct"
    PRIMARY_STD_COL = "depth_std_pct"

    # `:FETC:AM?`（DSB，18 项）里对应的字段名 —— 见驱动 _DEMOD_RESULT_FIELDS
    SOURCE_MEASURED_FIELD = "depth_half_pkpk_pct"
    SOURCE_PEAK_PLUS_FIELD = "depth_peak_plus_pct"
    SOURCE_PEAK_MINUS_FIELD = "depth_peak_minus_pct"
    SOURCE_IMBALANCE_FIELD = "depth_imbalance_pct"

    # AM 种类（DSB/SSB）读回值填进这一列
    EXTRA_SETTING_SOURCES = {"sa_am_genre": "genre_am"}

    # ------------------------------------------------------------------
    # 子类差异
    # ------------------------------------------------------------------
    def _occupied_bandwidth_hz(self, mod_param, mod_rate):
        """AM 双边带占用带宽 ≈ 2·fm（上、下边带各偏离载波 fm）。"""
        return 2.0 * mod_rate

    def _set_modulation(self, signal_generator, mod_param, mod_rate, config):
        """设 AM 深度并开启 AM：`SOUR:AM1:SOUR` → `:DEPTH` → `:STAT ON`。"""
        ok_source = signal_generator.set_am_source(config.get("mod_source", "LF1"))
        ok_depth = signal_generator.set_am_depth(mod_param)
        ok_on = signal_generator.enable_am(True)
        return bool(ok_source and ok_depth and ok_on)

    def _read_primary(self, metrics, mod_param):
        """从解调结果里取 AM 主指标（metrics 为 None 时全部留空）。"""
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
