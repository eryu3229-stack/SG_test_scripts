# -*- coding: utf-8 -*-
import time


class PowerMeter:
    """功率计控制类"""

    # NRP 归零耗时：手册 p127 写 "can take more than 8 s to complete"，
    # 因此默认 12 s 留足裕量。若传感器仍返回忙/超时，可继续调大。
    DEFAULT_ZERO_WAIT_S = 12.0

    def __init__(self, instrument, zero_wait_s=None):
        """初始化功率计

        Args:
            instrument: pyvisa仪器对象
            zero_wait_s: 归零等待秒数；None 则用 DEFAULT_ZERO_WAIT_S
        """
        self.instrument = instrument
        self.zero_wait_s = (
            self.DEFAULT_ZERO_WAIT_S if zero_wait_s is None else float(zero_wait_s)
        )
        # 初始化时设置功率单位为dBm
        self.set_power_unit("DBM")
        # 禁用连续测量模式，使用单次触发
        self.instrument.write("INIT:CONT OFF")
        # 默认设置为立即触发，确保后续测量无需等待外部信号
        self.instrument.write("TRIGger:SOURce IMMediate")
    
    def check_errors(self):
        """检查并打印错误队列中的所有错误"""
        while True:
            err = self.instrument.query("SYST:ERR?")
            print(err.strip())
            if err.startswith("0"):
                break

    def set_frequency(self, frequency):
        """设置功率计测量频率

        Args:
            frequency: 频率值，单位Hz
        """
        try:
            self.instrument.write(f"SENSe:FREQuency {frequency}")
            print(f"设置功率计测量频率为: {frequency} Hz")
        except Exception as e:
            print(f"设置频率失败: {e}")

    def set_power_unit(self, unit):
        """设置功率单位

        Args:
            unit: 功率单位 (WATT 或 DBM)
        """
        try:
            self.instrument.write(f"UNIT:POWer {unit}")
            print(f"设置功率单位为: {unit}")
        except Exception as e:
            print(f"设置功率单位失败: {e}")

    def reset(self):
        """复位功率计到默认状态"""
        try:
            self.instrument.write("*RST")
            print("复位功率计到默认状态")
            # 复位后重新设置功率单位、连续测量禁用和触发源
            self.set_power_unit("DBM")
            self.instrument.write("INIT:CONT OFF")
            self.instrument.write("TRIGger:SOURce IMMediate")
        except Exception as e:
            print(f"复位功率计失败: {e}")

    def zero(self, wait_s=None):
        """执行功率计归零（Zero calibration）

        依据 R&S NRPxS(N) 手册 1177.5079.02 - 26，CALibration<Channel>:ZERO:AUTO：
          - 唯一有效参数 ONCE；OFF 是"无归零进行中"时的查询返回值
          - 归零前必须关闭所有测试信号，否则归零报错
          - 归零期间为同步命令，禁止任何查询/设置命令，通信可能超时
          - 归零耗时 "can take more than 8 s"（p127），默认等待 12 s 留裕量
          - 归零后先查静态错误队列 SYSTem:SERRor?（手册指定），再查 SCPI 错误队列 SYST:ERR? 兜底

        注意：命令虽是同步的，但 pyvisa 的 write() 发送即返回，并不会阻塞到
        归零结束。因此必须在此显式等待，否则上层会在归零尚未完成时开始测量，
        读数会带着未补偿的零点漂移。

        Args:
            wait_s: 归零等待秒数；None 则用构造时的 zero_wait_s

        Raises:
            Exception: 归零等待后静态错误队列非 0（如 -240 归零失败）
        """
        wait_s = self.zero_wait_s if wait_s is None else float(wait_s)
        try:
            print(f"正在执行功率计归零，请确保无输入信号...（预计 {wait_s:.1f}s）")
            self.instrument.write("*CLS")
            self.instrument.write("CALibration:ZERO:AUTO ONCE")
            # 归零期间不允许任何查询，这里只等待、不轮询，避免通信超时。
            # 手册 p127：zeroing "can take more than 8 s"
            time.sleep(wait_s)
            # 归零后先查静态错误队列（手册指定），再查 SCPI 错误队列兜底
            static_error = self.instrument.query("SYSTem:SERRor?").strip()
            scpi_error = self.instrument.query("SYST:ERR?").strip()
            if not static_error.startswith("0") or not scpi_error.startswith("0"):
                raise RuntimeError(
                    f"功率计归零失败。静态错误队列: {static_error}; "
                    f"SCPI 错误队列: {scpi_error}。"
                    f"最常见原因：归零时输入信号未断开，请断开后重试。"
                )
            print(f"归零完成（等待 {wait_s:.1f}s）")
        except Exception as e:
            print(f"归零失败: {e}")
            raise  # 重新抛出异常，让上层知道归零失败

    def measure_power(self, times=1):
        """测量功率（多次测量并返回平均值）

        Args:
            times: 测量次数，默认1次。每次测量均使用立即触发。

        Returns:
            测量次数的平均值，单位dBm。如果失败返回None。
        """
        try:
            # 确保触发源为立即触发
            self.instrument.write("TRIGger:SOURce IMMediate")

            results = []
            for i in range(times):
                # 先触发测量
                self.instrument.write("INITiate")
                # 等待测量完成（同步查询）
                self.instrument.query("*OPC?")
                # 读取结果
                result_str = self.instrument.query("FETCh?")
                power = float(result_str.strip())
                results.append(power)

            avg_power = sum(results) / len(results)
            print(f"功率计测量 {times} 次，平均值: {avg_power:.6f} dBm")
            return avg_power
        except Exception as e:
            print(f"测量功率失败: {e}")
            return None

    def get_idn(self):
        """获取仪器ID信息"""
        try:
            return self.instrument.query("*IDN?")
        except Exception as e:
            print(f"获取ID信息失败: {e}")
            return None