class SpectrumAnalyzer:
    """频谱仪控制类"""
    
    def __init__(self, instrument):
        """初始化频谱仪
        
        Args:
            instrument: pyvisa仪器对象
        """
        self.instrument = instrument
    
    def set_center_frequency(self, frequency):
        """设置频谱仪中心频率
        
        Args:
            frequency: 频率值，单位Hz
        """
        try:
            self.instrument.write(f"FREQ:CENT {frequency}")
            print(f"设置频谱仪中心频率为: {frequency} Hz")
        except Exception as e:
            print(f"设置中心频率失败: {e}")
    
    def set_span(self, span):
        """设置频谱仪频率跨度
        
        Args:
            span: 跨度值，单位Hz
        """
        try:
            self.instrument.write(f"FREQ:SPAN {span}")
            print(f"设置频谱仪频率跨度为: {span} Hz")
        except Exception as e:
            print(f"设置频率跨度失败: {e}")
    
    def set_reference_level(self, level):
        """设置频谱仪参考电平
        
        Args:
            level: 参考电平值，单位dBm
        """
        try:
            self.instrument.write(f"DISP:WIND:TRAC:Y:RLEV {level}")
            print(f"设置频谱仪参考电平为: {level} dBm")
        except Exception as e:
            print(f"设置参考电平失败: {e}")
    
    def measure_power(self):
        """测量功率
        
        Returns:
            测量的功率值，单位dBm
        """
        try:
            # 假设使用MAX HOLD模式测量最大功率
            self.instrument.write("CALC:MARK:MAX")
            power = float(self.instrument.query("CALC:MARK:Y?"))
            print(f"测量到的功率值: {power} dBm")
            return power
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
    
    def peak_search(self):
        """执行峰值搜索"""
        try:
            self.instrument.write("CALC:MARK:MAX:PEAK")
            print("执行峰值搜索")
        except Exception as e:
            print(f"峰值搜索失败: {e}")
    
    def set_marker_frequency(self, marker_num, frequency):
        """设置标记器频率
        
        Args:
            marker_num: 标记器编号
            frequency: 频率值，单位Hz
        """
        try:
            self.instrument.write(f"CALC:MARK{marker_num}:X {frequency}")
            print(f"设置标记器{marker_num}频率为: {frequency} Hz")
        except Exception as e:
            print(f"设置标记器频率失败: {e}")
    
    def measure_marker_power(self, marker_num):
        """测量标记器功率
        
        Args:
            marker_num: 标记器编号
            
        Returns:
            测量的功率值，单位dBm
        """
        try:
            power = float(self.instrument.query(f"CALC:MARK{marker_num}:Y?"))
            print(f"标记器{marker_num}功率: {power} dBm")
            return power
        except Exception as e:
            print(f"测量标记器功率失败: {e}")
            return None
    
    def set_rbw(self, rbw):
        """设置分辨率带宽
        
        Args:
            rbw: 分辨率带宽，单位Hz
        """
        try:
            self.instrument.write(f"BAND:RES {rbw}")
            print(f"设置分辨率带宽为: {rbw} Hz")
        except Exception as e:
            print(f"设置分辨率带宽失败: {e}")
    
    def set_vbw(self, vbw):
        """设置视频带宽
        
        Args:
            vbw: 视频带宽，单位Hz
        """
        try:
            self.instrument.write(f"BAND:VID {vbw}")
            print(f"设置视频带宽为: {vbw} Hz")
        except Exception as e:
            print(f"设置视频带宽失败: {e}")
    
    def set_attenuation(self, attenuation):
        """设置衰减
        
        Args:
            attenuation: 衰减值，单位dB
        """
        try:
            self.instrument.write(f"INP:ATT {attenuation}")
            print(f"设置衰减为: {attenuation} dB")
        except Exception as e:
            print(f"设置衰减失败: {e}")
    
    def set_input_coupling(self, coupling):
        """设置输入耦合方式
        
        Args:
            coupling: 耦合方式，'AC' 或 'DC'
        """
        try:
            self.instrument.write(f"INP:COUP {coupling}")
            print(f"设置输入耦合为: {coupling}")
        except Exception as e:
            print(f"设置输入耦合失败: {e}")
