class SignalGenerator:
    """信号源控制类"""
    
    def __init__(self, instrument):
        """初始化信号源
        
        Args:
            instrument: pyvisa仪器对象
        """
        self.instrument = instrument
    
    def set_frequency(self, frequency):
        """设置信号源频率
        
        Args:
            frequency: 频率值，单位Hz
        """
        try:
            self.instrument.write(f"FREQ {frequency}")
            print(f"设置信号源频率为: {frequency} Hz")
        except Exception as e:
            print(f"设置频率失败: {e}")
    
    def set_power(self, power):
        """设置信号源功率
        
        Args:
            power: 功率值，单位dBm
        """
        try:
            self.instrument.write(f"POW {power}")
            print(f"设置信号源功率为: {power} dBm")
        except Exception as e:
            print(f"设置功率失败: {e}")
    
    def enable_output(self, enable=True):
        """启用或禁用信号源输出
        
        Args:
            enable: True为启用，False为禁用
        """
        try:
            if enable:
                self.instrument.write("OUTP:STATe ON")
                print("启用信号源输出")
            else:
                self.instrument.write("OUTP:STATe OFF")
                print("禁用信号源输出")
        except Exception as e:
            print(f"设置输出状态失败: {e}")
    
    def get_idn(self):
        """获取仪器ID信息"""
        try:
            return self.instrument.query("*IDN?")
        except Exception as e:
            print(f"获取ID信息失败: {e}")
            return None
