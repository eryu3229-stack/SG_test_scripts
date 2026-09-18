# -*- coding: utf-8 -*-
"""PM（相位调制）测量流程。

公共骨架（设置 / 采集 / 读数 / 判定 / 落盘）在 `analog_demod_base.py`，
本文件只声明 PM 的差异。

要读的量（用户 2026-09-18 定案）：**相位偏移 + 调制速率 + 正负峰值不平衡**，
相位偏移单位 **rad**。

相偏取 `(Pk-Pk)/2`（PM 结果表第 10 项）；`(Peak+)` / `(Peak-)` 另列。

⚠ **单位是本测量最大的坑，两处都有：**

  1. 频谱仪：`:UNIT:PM:DEMod` 会**连带改 `:FETC:PM?` 的数值**（不只是标注）。
     真机证实（N9030B / A.36.22，2026-09-16）：RAD 时第 8 项 0.167111437，
     DEGR 时 9.582051469，比值 57.339291918 = 180/π，而该节点复位默认值是 **DEGR**。
     驱动 `read_demod_metrics()` 已按"先读单位再换算回 rad"处理，本流程不依赖
     单位设置正确；配置仍显式锁 RAD，只为面板口径一致。
  2. 信号源：`UNIT:ANGLe` 能把角度默认单位改成度，届时裸数值 `PM:DEV 1` 会被
     当成 1°（0.0175 rad）。驱动 `set_pm_deviation()` 已显式带 `RAD`。
  两处合计，任何一处漏掉都会让结果差 57.3 倍，且**不报任何错**。
"""

from analog_demod_base import AnalogDemodProcedureBase


class PmDemodProcedure(AnalogDemodProcedureBase):
    """PM 解调测量流程。"""

    TEST_TYPE = "pm_demod"
    DEMOD_KIND = "PM"
    MOD_PARAM_UNIT = "rad"

    # 列顺序原则：**结论优先**
    FIELDNAMES = [
        # A 区：标识 + 结论（相偏 → 误差 → 不平衡 → 速率 → 判定）
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "pm_deviation_set_rad", "pm_deviation_measured_rad",
        "deviation_peak_plus_rad", "deviation_peak_minus_rad",
        "deviation_delta_rad", "deviation_rel_error_pct", "deviation_ref",
        "deviation_imbalance_rad",
        "mod_rate_set_hz", "mod_rate_measured_hz", "mod_rate_delta_hz",
        "status", "note",
        # B 区：频谱仪解调条件（读回的生效值）
        "sa_center_hz", "sa_span_hz", "sa_rbw_hz", "sa_channel_bw_hz",
        "sa_af_stop_hz", "sa_demod_time_s",
        "sa_average_on", "sa_average_count", "sa_pm_unit",
        "sa_af_unit", "sa_metric_display",
        # C 区：验证量
        "sinad_db", "thd_pct", "snr_db", "carrier_power_dbm", "rf_center_hz",
        "repeat_count", "deviation_std_rad", "timestamp",
    ]

    PRIMARY_SET_COL = "pm_deviation_set_rad"
    PRIMARY_MEASURED_COL = "pm_deviation_measured_rad"
    PRIMARY_PEAK_PLUS_COL = "deviation_peak_plus_rad"
    PRIMARY_PEAK_MINUS_COL = "deviation_peak_minus_rad"
    PRIMARY_DELTA_COL = "deviation_delta_rad"
    PRIMARY_REL_ERROR_COL = "deviation_rel_error_pct"
    PRIMARY_REF_COL = "deviation_ref"
    PRIMARY_IMBALANCE_COL = "deviation_imbalance_rad"
    PRIMARY_STD_COL = "deviation_std_rad"

    # `:FETC:PM?`（16 项）里对应的字段名；驱动已把角度量统一换算到 rad
    SOURCE_MEASURED_FIELD = "deviation_half_pkpk_rad"
    SOURCE_PEAK_PLUS_FIELD = "deviation_peak_plus_rad"
    SOURCE_PEAK_MINUS_FIELD = "deviation_peak_minus_rad"
    SOURCE_IMBALANCE_FIELD = "deviation_imbalance_rad"

    # PM 的解调 Y 轴单位读回值填进这一列
    EXTRA_SETTING_SOURCES = {"sa_pm_unit": "pm_demod_unit"}

    def _occupied_bandwidth_hz(self, mod_param, mod_rate):
        """PM 按 Carson 带宽：调制指数 β = Δφ(rad)，BW ≈ 2 × (β + 1) × fm。

        β=1、fm=1 kHz 时约 4 kHz；β 越大带宽需求越高（β 是相偏的弧度值本身）。
        """
        return 2.0 * (mod_param + 1.0) * mod_rate

    def _set_modulation(self, signal_generator, mod_param, mod_rate, config):
        """设 PM 相偏并开启 PM：`SOUR:PM1:SOUR` → `:DEV ... RAD` → `:STAT ON`。"""
        ok_source = signal_generator.set_pm_source(config.get("mod_source", "LF1"))
        ok_dev = signal_generator.set_pm_deviation(mod_param)
        ok_on = signal_generator.enable_pm(True)
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
