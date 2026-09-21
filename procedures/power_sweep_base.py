import csv
import math
import os
from datetime import datetime
from base_test_procedure import BaseTestProcedure


def _finite(value):
    """数值是否为有限实数（过滤 None / -inf / nan）"""
    return isinstance(value, (int, float)) and math.isfinite(value)


class PowerSweepBaseProcedure(BaseTestProcedure):
    """最大功率 / 低频最大功率 测试的公共基类

    输出两个 CSV：
      - 详细数据（逐点，流式写入，测一点写一点）—— start_csv_stream 指定的路径
      - 总结结论（每频点一行，最大可用功率）—— finish_csv 指定的路径

    统一字段约定（A 区所有源一致）：
      run_id / test_type / carrier_hz / set_power_dbm / actual_power_dbm /
      measured_power_dbm / delta_db / delta_ref
      actual_power_dbm = 折算到 DUT 端的功率 = measured_power_dbm + ext_att_db
        —— **仅 summary 表有此列**；detail 表不插（2026-09-20 用户明确要求）。
        （master 曾有对应列：summary 叫 `max_power`、detail 叫 `actual_power`，
          重构到本基类时丢失，2026-09-20 补回 —— 但只补 summary。）
      measured_power_dbm：功率计/频谱仪**原始读数**，含外接衰减，不是 DUT 端功率
      delta_db = actual_power_dbm - 参考值；delta_ref 指明参考值来源
      ext_att_db：外接物理衰减器数值，**仅用于折算读数，从不下发仪器**
    行字典的键顺序由 `_order_row()` 统一对齐到 SUMMARY_FIELDNAMES / DETAIL_FIELDNAMES
    （`**self.sa_context` 会展开到字典末尾，字面量顺序对不齐），并在缺键/多键时显式报错
    —— DictWriter 对缺键是静默写空串，不能指望它兜底。
    布尔列写 "true"/"false"。
    """

    TEST_TYPE = "max_power"

    SUMMARY_FIELDNAMES = [
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "actual_power_dbm", "measured_power_dbm", "delta_db", "delta_ref",
        "ext_att_db", "saturated", "steps",
        "status", "note", "timestamp",
    ]

    DETAIL_FIELDNAMES = [
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
        "ext_att_db", "step_index",
        "status", "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        """初始化测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        super().__init__(instrument_manager)
        self.power_sweep_data = []   # 逐点详细数据
        self.csv_sweep_streamer = None
        self.run_id = ""
        # 频谱仪采集条件（仅低频最大功率这类用频谱仪的源需要；键名以 sa_ 开头）
        # 子类在 run_test 中填充，写入时合并进每一行。
        self.sa_context = {}

    def _order_row(self, row, fieldnames):
        """把行字典按声明字段顺序重排，并显式做双向键校验

        **为什么必须显式校验**：`csv.DictWriter` 对**缺键**是静默写空串（不报错），
        只对**多余键**抛 ValueError。也就是说"少一列"这种最常见的字段表漂移
        永远不会自己暴露，必须在写入前把它变成显式错误。

        **为什么需要重排**：`**self.sa_context` 是展开到字典**末尾**的，
        而 FIELDNAMES 把 `sa_*` 排在中间（`delta_ref` 与 `ext_att_db` 之间），
        字典字面量的顺序无法与之对齐。落盘列序本由 `DictWriter(fieldnames=...)`
        决定，重排只是为了消除"源码两处顺序不一致"这个改歪隐患。

        Args:
            row: 待写入的行字典
            fieldnames: 声明的字段列表（summary / detail 各一份）

        Returns:
            键顺序与 fieldnames 完全一致的新字典

        Raises:
            ValueError: 缺键或多键（宁可报错，不可静默写空）
        """
        missing = [k for k in fieldnames if k not in row]
        extra = [k for k in row if k not in fieldnames]
        if missing or extra:
            raise ValueError(
                f"{type(self).__name__} 行字典与字段表不匹配: "
                f"missing={missing} extra={extra}"
            )
        return {k: row[k] for k in fieldnames}

    def add_test_result(self, frequency, set_power_at_max, max_measured_power,
                        max_actual_power, attenuation, saturation_point, steps, notes):
        """添加总结结论（每频点一行）

        Args:
            frequency: 测量频率 (Hz)
            set_power_at_max: 取到最大实际功率时的信号源设定功率 (dBm)
            max_measured_power: 最大测量功率 (dBm)，功率计/频谱仪原始读数
            max_actual_power: 最大实际功率 (dBm)，= 读数 + 外接衰减（折算到 DUT 端）。
                **写入 summary 的 `actual_power_dbm` 列**，同时是 `delta_db` 的被减数
            attenuation: 外接物理衰减值 (dB)
            saturation_point: 是否检测到饱和
            steps: 执行的功率步进数
            notes: 备注（停止原因等）
        """
        delta_db = None
        if _finite(max_actual_power) and _finite(set_power_at_max):
            delta_db = round(max_actual_power - set_power_at_max, 3)

        if not _finite(max_actual_power):
            status = "SKIP"
        elif saturation_point:
            status = "SATURATED"
        else:
            status = "OK"

        self.test_results.append(self._order_row({
            "run_id": self.run_id,
            "test_type": self.TEST_TYPE,
            "carrier_hz": frequency,
            "set_power_dbm": set_power_at_max if _finite(set_power_at_max) else None,
            "actual_power_dbm": max_actual_power if _finite(max_actual_power) else None,
            "measured_power_dbm": max_measured_power if _finite(max_measured_power) else None,
            "delta_db": delta_db,
            "delta_ref": "set",
            "ext_att_db": attenuation,
            "saturated": self.bool_str(saturation_point),
            "steps": steps,
            "status": status,
            "note": notes,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **self.sa_context,
        }, self.SUMMARY_FIELDNAMES))

    def add_power_sweep_point(self, frequency, set_power, measured_power,
                              actual_power, step_index, status, ext_att_db=0.0):
        """添加逐点详细数据

        Args:
            frequency: 频率 (Hz)
            set_power: 设定功率 (dBm)
            measured_power: 原始读数 (dBm)，可能为 None
            actual_power: 折算后实际功率 (dBm) = 读数 + 外接衰减
            step_index: 步进索引
            status: 步进结论，取值 OK / SATURATED / OVERLOAD / LIMIT / MEAS_FAIL
            ext_att_db: 外接物理衰减值 (dB)
        """
        delta_db = None
        if _finite(actual_power) and _finite(set_power):
            delta_db = round(actual_power - set_power, 3)

        row = {
            "run_id": self.run_id,
            "test_type": self.TEST_TYPE,
            "carrier_hz": frequency,
            "set_power_dbm": set_power,
            "measured_power_dbm": measured_power if _finite(measured_power) else None,
            "delta_db": delta_db,
            "delta_ref": "set",
            "ext_att_db": ext_att_db,
            "step_index": step_index,
            "status": status,
            "note": "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **self.sa_context,
        }
        row = self._order_row(row, self.DETAIL_FIELDNAMES)
        self.power_sweep_data.append(row)
        if self.csv_sweep_streamer:
            self.csv_sweep_streamer.append(row)

    def start_csv_stream(self, csv_path):
        """开启逐点详细数据的 CSV 流式写入

        Args:
            csv_path: 详细数据 CSV 路径
        """
        from utils.csv_streamer import CsvStreamer
        self.run_id = self.derive_run_id(csv_path)
        self.csv_sweep_streamer = CsvStreamer(csv_path, self.DETAIL_FIELDNAMES)

    def finish_csv(self, summary_path=None):
        """关闭详细数据流；若给定路径，另写一份总结结论 CSV

        Args:
            summary_path: 总结结论 CSV 路径（省略则只关闭详细流）
        """
        if self.csv_sweep_streamer:
            self.csv_sweep_streamer.close()
            print(f"CSV 详细数据已保存: {self.csv_sweep_streamer.filepath}")
        if summary_path:
            self._write_summary(summary_path)

    def _write_summary(self, summary_path):
        if not self.test_results:
            print("没有总结结论可保存")
            return
        os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
        with open(summary_path, "w", newline="", encoding="utf-8-sig") as summary_file:
            writer = csv.DictWriter(summary_file, fieldnames=self.SUMMARY_FIELDNAMES)
            writer.writeheader()
            for row in self.test_results:
                writer.writerow(row)
        print(f"CSV 总结已保存: {summary_path}")
