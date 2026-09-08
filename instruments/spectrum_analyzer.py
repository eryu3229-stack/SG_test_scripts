# -*- coding: utf-8 -*-
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
            # 使用更通用的峰值搜索命令
            self.instrument.write("CALC:MARK:MAX")
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
    
    def get_marker_frequency(self, marker_num):
        """获取标记器频率
        
        Args:
            marker_num: 标记器编号
            
        Returns:
            标记器频率值，单位Hz
        """
        try:
            frequency = float(self.instrument.query(f"CALC:MARK{marker_num}:X?"))
            print(f"标记器{marker_num}频率: {frequency} Hz")
            return frequency
        except Exception as e:
            print(f"获取标记器频率失败: {e}")
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
            # 是德 X 系列（N9030B）标准 SA 模式输入衰减的层级为 [:SENSe]:POWer[:RF]:ATTenuation，
            # 用完整短写 SENS:POW:RF:ATT，并确保 mnemonic 与数值间有空格（POW:ATT/INP:ATT 均会报 undefined header）。
            self.instrument.write(f"SENS:POW:RF:ATT {attenuation}")
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

    def wait_for_sweep(self, sweep_count=1):
        """切换到单次扫描并等待扫描完成

        持续扫描模式下 *OPC? 可能一直不返回，因此先禁用连续扫描，
        然后触发指定次数的单次扫描，再通过 *OPC? 同步。

        Args:
            sweep_count: 需要完成的扫描次数，默认1
        """
        try:
            self.instrument.write("INIT:CONT OFF")
            # 查询扫描时间并把 VISA 超时放大，避免窄 RBW + 宽 Span 时
            # *OPC? 在连接时设置的默认超时(5s)内扫不完
            try:
                sweep_time = float(self.instrument.query("SENS:SWE:TIME?"))
            except Exception:
                sweep_time = 0.0
            if sweep_time and sweep_time > 0.0:
                timeout_ms = max(120000, int(sweep_time * 2500.0))
            else:
                # 查询不到扫描时间时按 5 分钟兜底，避免 10s 上限过早超时
                timeout_ms = 300000
            self.instrument.timeout = timeout_ms
            print(
                f"单次扫描预计 {sweep_time:.1f} s，"
                f"等待超时设为 {timeout_ms / 1000:.0f} s"
            )
            for _ in range(max(1, sweep_count)):
                self.instrument.write("INIT:IMM")
                self.instrument.query("*OPC?")
            return True
        except Exception as e:
            print(f"等待扫描完成失败: {e}")
            return False

    def set_trace_mode(self, mode="MAXH"):
        """设置 trace 模式，例如 MAXH/WRITE/AVERAGE

        Args:
            mode: trace 模式
        """
        try:
            self.instrument.write(f"TRAC:MODE {mode}")
            print(f"设置频谱仪trace模式为: {mode}")
        except Exception as e:
            print(f"设置trace模式失败: {e}")

    def set_detector(self, detector="POS"):
        """设置检测器，例如 POS/NEG/SAMPLE/AVERAGE/RMS

        Args:
            detector: 检测器类型
        """
        try:
            self.instrument.write(f"DET:TRAC {detector}")
            print(f"设置频谱仪检测器为: {detector}")
        except Exception as e:
            print(f"设置检测器失败: {e}")

    def get_trace(self, trace=1):
        """读取频谱 trace 数据

        Args:
            trace: trace 编号，默认1

        Returns:
            幅度列表，单位为 dBm；读取失败返回 None
        """
        try:
            data = self.instrument.query(f"TRAC:DATA? TRACE{trace}")
            values = [float(value.strip()) for value in data.split(",") if value.strip()]
            print(f"读取频谱trace{trace}成功，共 {len(values)} 个点")
            return values
        except Exception as e:
            print(f"读取频谱trace失败: {e}")
            return None
