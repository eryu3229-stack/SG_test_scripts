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
      run_id / test_type / carrier_hz / set_power_dbm / measured_power_dbm / delta_db / delta_ref
      delta_db = (measured_power_dbm + ext_att_db) - 参考值；delta_ref 指明参考值来源
      ext_att_db：外接物理衰减器数值，**仅用于折算读数，从不下发仪器**
    布尔列写 "true"/"false"。
    """

    TEST_TYPE = "max_power"

    SUMMARY_FIELDNAMES = [
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
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

    def add_test_result(self, frequency, set_power_at_max, max_measured_power,
                        max_actual_power, attenuation, saturation_point, steps, notes):
        """添加总结结论（每频点一行）

        Args:
            frequency: 测量频率 (Hz)
            set_power_at_max: 取到最大实际功率时的信号源设定功率 (dBm)
            max_measured_power: 最大测量功率 (dBm)，功率计/频谱仪原始读数
            max_actual_power: 最大实际功率 (dBm)，= 读数 + 外接衰减（折算到 DUT 端）
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

        self.test_results.append({
            "run_id": self.run_id,
            "test_type": self.TEST_TYPE,
            "carrier_hz": frequency,
            "set_power_dbm": set_power_at_max if _finite(set_power_at_max) else None,
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
        })

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
