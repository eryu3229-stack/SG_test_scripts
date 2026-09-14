# -*- coding: utf-8 -*-
import time

class SpectrumAnalyzer:
    """频谱仪控制类"""
    
    def __init__(self, instrument):
        """初始化频谱仪
        
        Args:
            instrument: pyvisa仪器对象
        """
        self.instrument = instrument
    
    def set_center_frequency(self, frequency):
        """设置频谱仪中心频率"""
        try:
            self.instrument.write(f"FREQ:CENT {frequency}")
        except Exception as e:
            print(f"设置中心频率失败: {e}")

    def set_span(self, span):
        """设置频谱仪频率跨度"""
        try:
            self.instrument.write(f"FREQ:SPAN {span}")
        except Exception as e:
            print(f"设置频率跨度失败: {e}")

    def set_reference_level(self, level):
        """设置频谱仪参考电平"""
        try:
            self.instrument.write(f"DISP:WIND:TRAC:Y:RLEV {level}")
        except Exception as e:
            print(f"设置参考电平失败: {e}")

    def set_attenuation_auto(self, state=True):
        """设置机械衰减自动/手动（N9030B，手册 Swept SA 模式指令）

        手册指令:
            [:SENSe]:POWer[:RF]:ATTenuation:AUTO OFF | ON | 0 | 1
        注意: 手动发送 [:SENSe]:POWer[:RF]:ATTenuation <值> 会自动切回手动模式。

        Args:
            state: True 自动衰减，False 手动
        """
        try:
            self.instrument.write(f"SENS:POW:ATT:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置自动衰减失败: {e}")

    def set_preamp(self, state=True, band=None):
        """设置内置预放（N9030B，手册 Swept SA 模式指令）

        手册指令:
            [:SENSe]:POWer[:RF]:GAIN[:STATe] OFF | ON | 0 | 1
            [:SENSe]:POWer[:RF]:GAIN:BAND OFF | LOW | FULL

        Args:
            state: True 打开预放，False 关闭
            band: 预放频段，"LOW"(仅低波段) 或 "FULL"(全频段)；None 不改频段
        """
        try:
            if state:
                if band:
                    self.instrument.write(f"SENS:POW:GAIN:BAND {band}")
                self.instrument.write("SENS:POW:GAIN ON")
            else:
                self.instrument.write("SENS:POW:GAIN OFF")
        except Exception as e:
            print(f"设置预放失败: {e}")

    def measure_power(self):
        """测量功率

        Returns:
            测量的功率值，单位dBm
        """
        try:
            # 假设使用MAX HOLD模式测量最大功率
            self.instrument.write("CALC:MARK:MAX")
            power = float(self.instrument.query("CALC:MARK:Y?"))
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
        except Exception as e:
            print(f"设置分辨率带宽失败: {e}")
    
    def set_vbw(self, vbw):
        """设置视频带宽
        
        Args:
            vbw: 视频带宽，单位Hz
        """
        try:
            self.instrument.write(f"BAND:VID {vbw}")
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
            self.instrument.write(f"INP:ATT {attenuation}")
        except Exception as e:
            print(f"设置衰减失败: {e}")
    
    def set_input_coupling(self, coupling):
        """设置输入耦合方式
        
        Args:
            coupling: 耦合方式，'AC' 或 'DC'
        """
        try:
            self.instrument.write(f"INP:COUP {coupling}")
        except Exception as e:
            print(f"设置输入耦合失败: {e}")

    def wait_for_sweep(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        """切换到单次扫描并等待扫描完成（保守版，供宽 SPAN 扫描使用）

        N9030B 不支持 SWE:COUN，*OPC? 在某些模式下也不可靠。
        改用连续扫描 + 固定等待：根据 SPAN 大小动态调整安全系数，
        避免远端大 SPAN 没扫完就进入下一步。杂散扫描（宽 SPAN）依赖此实现。
        小 SPAN 的快速场景请改用 wait_for_sweep_fast。

        Args:
            sweep_count: 需要完成的扫描次数，默认1
            span_hz: 当前 SPAN，用于调整等待时间（可选）
            factor: 扫描时间放大系数（None 则按 SPAN 自动选择）
            margin: 固定余量秒数（None 则按 SPAN 自动选择）

        Returns:
            bool: 是否成功完成所有扫描
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.write("INIT:CONT OFF")
            # 查询扫描时间并把 VISA 超时放大
            try:
                sweep_time = float(self.instrument.query("SENS:SWE:TIME?"))
            except Exception:
                sweep_time = 0.0

            # 根据 SPAN 动态调整安全系数：SPAN 越大，实际扫描时间波动越大
            if factor is None or margin is None:
                span = span_hz if span_hz else 10e6
                if span <= 10e6:
                    default_factor, default_margin = 1.5, 1.0
                elif span <= 100e6:
                    default_factor, default_margin = 2.0, 2.0
                elif span <= 1e9:
                    default_factor, default_margin = 3.0, 3.0
                else:
                    default_factor, default_margin = 4.0, 5.0
                factor = factor if factor is not None else default_factor
                margin = margin if margin is not None else default_margin

            # 总超时 = sweep_count 次扫描 + 余量
            sweep_count = max(1, sweep_count)
            if sweep_time and sweep_time > 0.0:
                total_time = sweep_count * sweep_time
                timeout_ms = max(120000, int(total_time * factor * 1000) + int(margin * 1000))
            else:
                timeout_ms = max(300000, 120000 * sweep_count)
            self.instrument.timeout = timeout_ms

            # 改用连续扫描 + 固定等待
            self.instrument.write("INIT:CONT ON")
            wait_s = (sweep_count * sweep_time * factor) + margin
            print(f"    等待 {wait_s:.1f}s (sweep_time={sweep_time:.3f}s × {sweep_count} × {factor})")
            time.sleep(wait_s)
            self.instrument.write("INIT:CONT OFF")
            # 再额外等一次扫描时间确保当前扫描完成
            time.sleep(sweep_time * 1.2 + 0.5)
            return True
        except Exception as e:
            print(f"等待扫描完成失败: {e}")
            self._cleanup_after_timeout()
            return False
        finally:
            if original_timeout is not None:
                try:
                    self.instrument.timeout = original_timeout
                except Exception:
                    pass

    def wait_for_sweep_fast(self, sweep_count=1, span_hz=None, factor=1.5, margin=0.15, extra_margin=0.0):
        """小 SPAN 快速扫描同步（连续扫描方式，余量比 wait_for_sweep 小）

        与 wait_for_sweep 使用相同的「连续扫描 + 固定等待」机制（保证真正触发并
        完成扫描），只是把安全系数/余量压小，适配谐波/分谐波这类小 SPAN
        （FFT 扫描，sweep_time 仅几十毫秒）的场景，避免被与扫描无关的
        固定兜底（如原来的 +0.5s）拖慢。宽 SPAN 的杂散扫描请用 wait_for_sweep。

        若发现读数未刷新（扫描没跑完就进入下一步），可适当增大 factor/margin。

        Args:
            sweep_count: 需要完成的扫描次数，默认1
            span_hz: 当前 SPAN（保留参数，便于调用方统一传参）
            factor: 扫描时间放大系数，默认1.5
            margin: 固定余量秒数，默认0.15
            extra_margin: 切回单次模式后再等 sweep_time×1.2 + extra_margin 秒，
                          确保当前扫描完成，默认0.0

        Returns:
            bool: 是否成功完成所有扫描
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.write("INIT:CONT OFF")
            try:
                sweep_time = float(self.instrument.query("SENS:SWE:TIME?"))
            except Exception:
                sweep_time = 0.0

            sweep_count = max(1, sweep_count)
            if sweep_time and sweep_time > 0.0:
                wait_s = sweep_count * sweep_time * factor + margin
            else:
                # 查询不到扫描时间时退化为保守估计
                wait_s = sweep_count * 0.3 + margin

            # VISA 超时给足即可，不影响实际等待时长
            self.instrument.timeout = max(60000, int(wait_s * 1000) + 5000)
            print(f"    快速同步等待 {wait_s:.3f}s "
                  f"(sweep_time={sweep_time:.3f}s × {sweep_count} × {factor} + {margin})")

            # 连续扫描一段时间确保完成 sweep_count 次扫描
            self.instrument.write("INIT:CONT ON")
            time.sleep(wait_s)
            self.instrument.write("INIT:CONT OFF")
            # 切回单次后再补一小段，确保当前扫描完成、trace 已刷新
            time.sleep(sweep_time * 1.2 + extra_margin)
            return True
        except Exception as e:
            print(f"等待扫描完成失败: {e}")
            self._cleanup_after_timeout()
            return False
        finally:
            if original_timeout is not None:
                try:
                    self.instrument.timeout = original_timeout
                except Exception:
                    pass

    def _cleanup_after_timeout(self):
        """扫描同步超时后尝试清理仪器状态，防止后续命令挂死"""
        try:
            # 中止当前扫描并清状态
            self.instrument.write("ABOR")
            self.instrument.write("INIT:CONT ON")
            self.instrument.write("*CLS")
        except Exception as cleanup_e:
            print(f"超时后清理仪器状态失败: {cleanup_e}")

    def set_trace_mode(self, mode="MAXH"):
        """设置 trace 模式，例如 MAXH/WRITE/AVERAGE

        N9030B 使用 :TRACe:MODE 子系统。由于不知道仪器当前
        AVG|HOLD 计数的准确清除命令，改用连续扫描 + 固定等待来避免
        被历史平均设置阻塞。

        Args:
            mode: trace 模式
        """
        try:
            self.instrument.write(f"TRAC:MODE {mode}")
        except Exception as e:
            print(f"设置trace模式失败: {e}")

    def set_detector(self, detector="POS"):
        """设置检测器，例如 POS/NEG/SAMPLE/AVERAGE/RMS

        Args:
            detector: 检测器类型
        """
        try:
            self.instrument.write(f"DET:TRAC {detector}")
        except Exception as e:
            print(f"设置检测器失败: {e}")

    def get_trace(self, trace=1):
        """读取频谱 trace 数据

        Args:
            trace: trace 编号，默认1

        Returns:
            幅度列表，单位为 dBm；读取失败返回 None
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            # 强制 ASCII 返回，避免 N9030B 二进制块解析卡住
            self.instrument.write("FORM:DATA ASC")
            # trace 数据量可能很大，给 30 秒读取超时
            self.instrument.timeout = max(original_timeout, 30000)

            data = self.instrument.query(f"TRAC:DATA? TRACE{trace}")

            # 兼容二进制块头：若数据以 '#' 开头，按块长度跳过 header
            if data.startswith("#"):
                digits = int(data[1])
                byte_count = int(data[2:2 + digits])
                payload = data[2 + digits:2 + digits + byte_count]
                values = [float(v.strip()) for v in payload.split(",") if v.strip()]
            else:
                values = [float(value.strip()) for value in data.split(",") if value.strip()]

            return values
        except Exception as e:
            print(f"读取频谱trace失败: {e}")
            return None
        finally:
            if original_timeout is not None:
                try:
                    self.instrument.timeout = original_timeout
                except Exception:
                    pass
