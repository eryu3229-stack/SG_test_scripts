import time
from datetime import datetime
from base_test_procedure import BaseTestProcedure


class TestProcedure(BaseTestProcedure):
    """功率扫描测试流程类（功率计读数，只输出 CSV）"""

    TEST_TYPE = "power_sweep"

    FIELDNAMES = [
        "run_id", "test_type", "carrier_hz", "set_power_dbm",
        "measured_power_dbm", "delta_db", "delta_ref",
        "ext_att_db", "compensated_power_dbm",
        "status", "note", "timestamp",
    ]

    def __init__(self, instrument_manager):
        """初始化测试流程"""
        super().__init__(instrument_manager)
        self.test_prepared = False
        self.run_id = ""

    def add_test_result(self, frequency, set_power, measured_power, attenuator_value=0):
        """添加测试结果

        Args:
            frequency: 测量频率 (Hz)
            set_power: 设定功率 (dBm)
            measured_power: 功率计读数 (dBm)
            attenuator_value: 外接物理衰减值 (dB)，仅用于折算读数，从不下发仪器
        """
        compensated_power = (
            measured_power + attenuator_value
            if (measured_power is not None and attenuator_value)
            else measured_power
        )
        delta_db = None
        if set_power is not None and compensated_power is not None:
            delta_db = round(compensated_power - set_power, 3)

        row = {
            "run_id": self.run_id,
            "test_type": self.TEST_TYPE,
            "carrier_hz": frequency,
            "set_power_dbm": set_power,
            "measured_power_dbm": measured_power,
            "delta_db": delta_db,
            "delta_ref": "set",
            "ext_att_db": attenuator_value,
            "compensated_power_dbm": compensated_power,
            "status": "OK" if measured_power is not None else "SKIP",
            "note": "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.test_results.append(row)
        if self.csv_streamer:
            self.csv_streamer.append(row)

    def prepare_test(self, signal_generator, power_meter):
        """测试前准备步骤"""
        print("等待功率计归零稳定...")
        time.sleep(2.0)
        print("开启测试准备...")
        signal_generator.enable_output(False)
        time.sleep(0.5)
        self.test_prepared = True
        print("测试准备完成")

    def run_test(self, signal_generator, power_meter, test_config, keep_output=False):
        """运行测试"""
        print(f"开始测试: {test_config['test_name']}")

        signal_generator.set_frequency(test_config['frequency'])
        signal_generator.set_power(test_config['power'])
        signal_generator.enable_output(True)

        settling_time = test_config.get('settling_time', 1.5)
        time.sleep(settling_time)

        power_meter.set_frequency(test_config['frequency'])
        pm_settling_time = test_config.get('pm_settling_time', 0.5)
        time.sleep(pm_settling_time)

        measurement_times = test_config.get('measurement_times', 5)
        measured_power = power_meter.measure_power(times=measurement_times)

        attenuator_value = 0
        if test_config.get('attenuator_enabled', False):
            attenuator_value = test_config.get('attenuator_value', 0)

        self.add_test_result(test_config['frequency'], test_config['power'], measured_power, attenuator_value)

        if not keep_output:
            signal_generator.enable_output(False)
            post_close_wait = test_config.get('post_close_wait', 0.1)
            time.sleep(post_close_wait)

        print(f"测试完成: {test_config['test_name']}")

    def start_csv_stream(self, csv_path):
        """开启 CSV 流式写入"""
        from utils.csv_streamer import CsvStreamer
        self.run_id = self.derive_run_id(csv_path)
        self.csv_streamer = CsvStreamer(csv_path, self.FIELDNAMES)
