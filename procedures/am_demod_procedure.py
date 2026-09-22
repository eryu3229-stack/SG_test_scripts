# -*- coding: utf-8 -*-
"""AM 解调测量流程。

严格按用户提供的 SCPI 参考流程驱动信号源：

    LFO1:SHAP SINE
    LFO1:FREQ <rate>
    AM:TYPE LIN
    AM1:SOUR LF1
    AM1:DEPT:LIN <depth>
    AM1:STAT ON
    SOUR:MOD:ALL:STAT ON

并在测试结束阶段按指定顺序清理：

    OUTP:STAT OFF
    AM1:STAT OFF
    SOUR:MOD:ALL:STAT OFF

解调主指标取 `depth_half_pkpk_pct`（双边带半峰峰值深度），与信号源设定深度
直接对应。正/负峰深度、不平衡、SINAD/THD/SNR 全部写入 CSV 供追溯。
"""

import time

from analog_demod_base import AnalogDemodProcedureBase
from utils.formatting import format_frequency


class AmDemodProcedure(AnalogDemodProcedureBase):
    """AM 解调测量流程。"""

    DEMOD_KIND = "AM"
    TEST_TYPE = "am_demod"
    MOD_PARAM_UNIT = "%"

    FIELDNAMES = [
        # A 区：运行标识 + 结论
        "run_id", "test_type",
        "carrier_hz", "set_power_dbm",
        "am_depth_set_pct", "am_depth_measured_pct",
        "am_depth_delta_pct", "am_depth_rel_error_pct", "am_depth_ref",
        "am_depth_peak_plus_pct", "am_depth_peak_minus_pct",
        "am_depth_imbalance_pct", "am_depth_std_pct",
        "mod_rate_set_hz", "mod_rate_measured_hz", "mod_rate_delta_hz",
        "status", "note",
        # B 区：频谱仪生效条件
        "sa_center_hz", "sa_span_hz", "sa_rbw_hz", "sa_channel_bw_hz",
        "sa_af_stop_hz", "sa_demod_time_s", "sa_af_unit",
        "sa_average_on", "sa_average_count", "sa_metric_display",
        "sa_am_genre",
        # C 区：验证量
        "sinad_db", "thd_pct", "snr_db",
        "carrier_power_dbm", "rf_center_hz",
        "repeat_count", "timestamp",
    ]

    PRIMARY_SET_COL = "am_depth_set_pct"
    PRIMARY_MEASURED_COL = "am_depth_measured_pct"
    PRIMARY_PEAK_PLUS_COL = "am_depth_peak_plus_pct"
    PRIMARY_PEAK_MINUS_COL = "am_depth_peak_minus_pct"
    PRIMARY_DELTA_COL = "am_depth_delta_pct"
    PRIMARY_REL_ERROR_COL = "am_depth_rel_error_pct"
    PRIMARY_REF_COL = "am_depth_ref"
    PRIMARY_IMBALANCE_COL = "am_depth_imbalance_pct"
    PRIMARY_STD_COL = "am_depth_std_pct"

    # 用于计算重复性标准差的样本字段
    SOURCE_MEASURED_FIELD = "depth_half_pkpk_pct"

    EXTRA_SETTING_SOURCES = {
        "sa_am_genre": "genre_am",
    }

    # ------------------------------------------------------------------
    # AM 专用实现
    # ------------------------------------------------------------------
    def _occupied_bandwidth_hz(self, mod_param, mod_rate):
        """AM 双边带占用带宽 ≈ 2 * fm。"""
        return 2.0 * mod_rate

    def _set_modulation(self, signal_generator, mod_param, mod_rate, config):
        """按用户 SCPI 顺序下发 AM 调制并回读关键参数。

        LF 源（LFO1:SHAP / LFO1:FREQ / LFO1:STAT）由基类 _prepare_modulation()
        统一设置；这里只负责 AM 本身的配置链。所有设置命令都带返回值检查，
        任一失败即返回 False。
        """
        ok = True

        # AM 类型：参考流程固定 LIN
        ok = signal_generator.set_am_type(config.get("am_type", "LIN")) and ok

        # AM 源：参考流程固定 LF1
        ok = signal_generator.set_am_source(config.get("am_source", "LF1")) and ok

        # 线性深度：参考流程为 AM1:DEPT:LIN <depth>
        ok = signal_generator.set_am_depth_lin(mod_param) and ok

        # 开启 AM
        ok = signal_generator.enable_am(True) and ok

        # 开启总调制路径：参考流程要求 AM1:STAT ON 之后发 SOUR:MOD:ALL:STAT ON
        ok = signal_generator.set_all_modulation(True) and ok

        # 回读深度与 LF 源，作为设置生效的旁证（终端可见，供人工核对）
        signal_generator.get_am_type()
        signal_generator.get_am_depth_lin()
        signal_generator.get_lf_shape()
        signal_generator.get_lf_frequency()

        return ok

    def _read_primary(self, mean, set_value):
        """从 SA 回读结果中提取 AM 主指标。"""
        measured = mean.get("depth_half_pkpk_pct") if mean else None
        peak_plus = mean.get("depth_peak_plus_pct") if mean else None
        peak_minus = mean.get("depth_peak_minus_pct") if mean else None
        delta = None
        rel_error = None
        if measured is not None and set_value is not None:
            delta = measured - set_value
            if abs(set_value) > 0:
                rel_error = delta / set_value * 100.0
        imbalance = mean.get("depth_imbalance_pct") if mean else None

        return {
            self.PRIMARY_SET_COL: set_value,
            self.PRIMARY_MEASURED_COL: measured,
            self.PRIMARY_PEAK_PLUS_COL: peak_plus,
            self.PRIMARY_PEAK_MINUS_COL: peak_minus,
            self.PRIMARY_DELTA_COL: delta,
            self.PRIMARY_REL_ERROR_COL: rel_error,
            self.PRIMARY_REF_COL: "set",
            self.PRIMARY_IMBALANCE_COL: imbalance,
        }

    # ------------------------------------------------------------------
    # 结束阶段：恢复未调制信号 + 清理
    # ------------------------------------------------------------------
    def verify_unmodulated_carrier(self, signal_generator, spectrum_analyzer,
                                   carrier_frequency, config):
        """关 AM 后在普通频谱模式下复测载波功率/频率，验证 ALC 已恢复。"""
        if not config.get("verify_unmodulated_carrier"):
            return

        print(f"\n恢复未调制信号，复测载波 {format_frequency(carrier_frequency)}")
        signal_generator.enable_am(False)
        signal_generator.set_all_modulation(False)

        settle = config.get("verify_settling_time_s", 1.0)
        if settle > 0:
            time.sleep(settle)

        sa_config = config.get("verify_sa_config", {})
        self.setup_spectrum_analyzer(spectrum_analyzer, carrier_frequency, sa_config)

        if not self._acquire(spectrum_analyzer):
            print("  未调制载波复测采集失败")
            return

        if hasattr(spectrum_analyzer, "peak_search"):
            spectrum_analyzer.peak_search()
            time.sleep(0.05)

        power = self._read_marker(spectrum_analyzer, 1)
        freq = None
        if hasattr(spectrum_analyzer, "get_marker_frequency"):
            freq = spectrum_analyzer.get_marker_frequency(1)

        if power is None:
            print("  未调制载波复测读数失败")
            return

        freq_str = format_frequency(freq) if freq is not None else "未知"
        print(f"  未调制载波复测: {freq_str}, {power:.2f} dBm")

    def cleanup_am(self, signal_generator):
        """按用户指定顺序关闭输出与调制：

            OUTP:STAT OFF → AM1:STAT OFF → SOUR:MOD:ALL:STAT OFF
        """
        print("\nAM 解调测试结束，按指定顺序清理...")
        signal_generator.enable_output(False)
        signal_generator.enable_am(False)
        signal_generator.set_all_modulation(False)
        print("  清理完成")
