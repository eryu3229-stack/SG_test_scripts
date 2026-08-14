
class PowerMeter:
    """功率计控制类"""

    def __init__(self, instrument):
        """初始化功率计

        Args:
            instrument: pyvisa仪器对象
        """
        self.instrument = instrument
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

    def zero(self, timeout_ms=30000):
        """执行功率计归零（Zeroing）

        归零前必须断开所有输入信号。该命令为同步操作，仪器在归零完成前
        不处理其他远程命令，因此需要足够长的 VISA 超时时间。归零完成后
        通过静态错误队列 SYSTem:SERRor? 确认结果。
        """
        try:
            print("正在执行功率计归零，请确保无输入信号...")
            old_timeout = self.instrument.timeout
            self.instrument.timeout = timeout_ms
            try:
                # 清空状态和错误队列，确保后续查询的是本次归零结果
                self.instrument.write("*CLS")
                # 归零命令是同步的，执行期间仪器会阻塞直到完成
                self.instrument.write("CALibration:ZERO:AUTO ONCE")
                # 归零完成后查询静态错误队列：0 表示成功，-240 表示失败
                result = self.instrument.query("SYSTem:SERRor?").strip()
                if result != "0":
                    raise RuntimeError(f"归零失败，SYSTem:SERRor? 返回 {result}")
                print("归零完成")
            finally:
                self.instrument.timeout = old_timeout
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
