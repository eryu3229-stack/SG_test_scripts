# -*- coding: utf-8 -*-
"""频谱仪品牌后端公共基类。

本基类承载与品牌无关的实现：
- `*IDN?` 读取
- 扫描同步（连续扫描 + 固定等待，宽/窄 SPAN 两档）
- trace 数据读取
- 超时清理

各品牌后端只需实现品牌相关的指令路径；未实现的方法在基类抛
`NotImplementedError`，便于新增品牌时快速发现漏实现。

指令来源：
- 罗德 R&S：R&S FSWP-B1 User Manual, 1177.5656.02 ─ 11
- 是德 Keysight：X-Series SA Mode User's & Programmer's Reference, N9060-90041
"""
import time


class SpectrumAnalyzerBackend:
    """品牌后端基类（同时作为未知品牌的通用回退实现）。"""

    BRAND = "unknown"

    # 通用 SCPI 子集：两大品牌共用的短写形式
    CMD_CENTER_FREQ = "FREQ:CENT"
    CMD_SPAN = "FREQ:SPAN"
    CMD_RBW = "BAND:RES"
    CMD_VBW = "BAND:VID"
    CMD_MARKER_X = "CALC:MARK{m}:X"
    CMD_MARKER_XQ = "CALC:MARK{m}:X?"
    CMD_MARKER_YQ = "CALC:MARK{m}:Y?"
    CMD_TRACE_QUERY = "TRAC:DATA? TRACE{t}"
    CMD_SWEEP_TIME_Q = "SENS:SWE:TIME?"
    CMD_CONT = "INIT:CONT"

    # 读回校验用的查询命令（两大品牌短写一致）
    Q_RBW = "BAND:RES?"
    Q_VBW = "BAND:VID?"
    Q_SWEEP_POINTS = "SWE:POIN?"

    def __init__(self, instrument):
        self.instrument = instrument

    # ------------------------------------------------------------------
    # 通用：身份
    # ------------------------------------------------------------------
    def get_idn(self):
        """获取仪器 ID 信息 (`*IDN?`)。"""
        try:
            return self.instrument.query("*IDN?")
        except Exception as e:
            print(f"获取ID信息失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 通用：读回校验（只读）
    # ------------------------------------------------------------------
    def query(self, command):
        """只读查询任意 SCPI 命令，返回原始字符串（失败返回 None）。

        仅用于**读回校验**：确认下发过的设置仪器是否真的接受。
        不含任何写入动作。
        """
        try:
            return self.instrument.query(command)
        except Exception as e:
            print(f"查询失败 {command!r}: {e}")
            return None

    def _query_float(self, command):
        """只读查询并转 float；查询失败或非数值时返回 None。"""
        raw = self.query(command)
        if raw is None:
            return None
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            return None

    def read_key_settings(self):
        """读回影响测量结论的关键设置。

        Returns:
            dict，键为设置名，值为读到的数值；读不到的项为 None。
            调用方据此判断"下发值是否被仪器接受"，读不到的项按"无法校验"处理。
        """
        settings = {
            "rbw_hz": self._query_float(self.Q_RBW),
            "vbw_hz": self._query_float(self.Q_VBW),
            "sweep_points": self._query_float(self.Q_SWEEP_POINTS),
        }
        settings.update(self._read_extra_settings())
        return settings

    def _read_extra_settings(self):
        """品牌相关的幅度/RF 设置读回；基类无对应命令，返回空字典。"""
        return {}

    # ------------------------------------------------------------------
    # 通用：标记点（两大品牌短写一致）
    # ------------------------------------------------------------------
    def set_marker_frequency(self, marker_num, frequency):
        """设置标记器频率 (`CALC:MARK<m>:X`)。"""
        try:
            self.instrument.write(self.CMD_MARKER_X.format(m=marker_num) + f" {frequency}")
        except Exception as e:
            print(f"设置标记器频率失败: {e}")

    @staticmethod
    def _sanitize_raw(raw):
        """仪器原始返回值 -> float；哨兵值(>=1e30)与非法值一律返回 None。

        是德在"无有效数据"时（marker 未开启 / marker 屏外 / trace 未就绪）
        返回 9.91e+37。不拦截就会被当成真实功率写入结果。
        """
        if raw is None:
            return None
        try:
            f = float(str(raw).strip())
        except (TypeError, ValueError):
            return None
        if abs(f) >= 1e30:
            print(f"    仪器返回哨兵值 {f:.4e}（无有效数据），按 None 处理")
            return None
        return f

    def measure_marker_power(self, marker_num):
        """读取标记器功率 (`CALC:MARK<m>:Y?`)。哨兵/非法值返回 None。"""
        try:
            return self._sanitize_raw(self.instrument.query(self.CMD_MARKER_YQ.format(m=marker_num)))
        except Exception as e:
            print(f"测量标记器功率失败: {e}")
            return None

    def get_marker_frequency(self, marker_num):
        """读取标记器频率 (`CALC:MARK<m>:X?`)。哨兵/非法值返回 None。"""
        try:
            return self._sanitize_raw(self.instrument.query(self.CMD_MARKER_XQ.format(m=marker_num)))
        except Exception as e:
            print(f"获取标记器频率失败: {e}")
            return None

    def get_error_queue(self, limit=30):
        """读取 SCPI 错误队列直到 'no error'，返回错误字符串列表。

        用于替代"猜"：仪器是否真的接受了命令、峰值搜索是否报告 No peak found，
        都只能通过错误队列确认。
        """
        errors = []
        try:
            for _ in range(limit):
                err = str(self.instrument.query("SYST:ERR?")).strip()
                if "no error" in err.lower():
                    break
                errors.append(err)
        except Exception as e:
            print(f"读取错误队列失败: {e}")
        return errors

    def trigger_single(self):
        """显式触发一次单次扫描并阻塞等待完成（`INIT:CONT OFF` + `INIT:IMM` + `*OPC?`）。

        与 `wait_for_sweep_fast` 的固定等待互补：后者保证"扫够时间"，本方法保证
        "确实完成了一次采集、trace 可读"，避免同步结束后仪器停在待触发态、
        marker 落在无有效数据上而返回哨兵。
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.timeout = max(original_timeout or 0, 30000)
            self.instrument.write(f"{self.CMD_CONT} OFF")
            self.instrument.write("INIT:IMM")
            self.instrument.query("*OPC?")
            return True
        except Exception as e:
            print(f"单次触发失败: {e}")
            self._cleanup_after_timeout()
            return False
        finally:
            if original_timeout is not None:
                try:
                    self.instrument.timeout = original_timeout
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 通用：带宽
    # ------------------------------------------------------------------
    def set_rbw(self, rbw):
        """设置分辨率带宽 (`BAND:RES`)。"""
        try:
            self.instrument.write(f"{self.CMD_RBW} {rbw}")
        except Exception as e:
            print(f"设置分辨率带宽失败: {e}")

    def set_vbw(self, vbw):
        """设置视频带宽 (`BAND:VID`)。"""
        try:
            self.instrument.write(f"{self.CMD_VBW} {vbw}")
        except Exception as e:
            print(f"设置视频带宽失败: {e}")

    # ------------------------------------------------------------------
    # 通用：输入耦合（两大品牌均为 INP:COUP）
    # ------------------------------------------------------------------
    def set_input_coupling(self, coupling):
        """设置输入耦合 (`INP:COUP AC|DC`)。"""
        try:
            self.instrument.write(f"INP:COUP {coupling}")
        except Exception as e:
            print(f"设置输入耦合失败: {e}")

    # ------------------------------------------------------------------
    # 通用：扫描同步
    # ------------------------------------------------------------------
    def _query_sweep_time(self):
        """查询单次扫描时间，查询失败返回 0.0。"""
        try:
            return float(self.instrument.query(self.CMD_SWEEP_TIME_Q))
        except Exception:
            return 0.0

    def wait_for_sweep(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        """宽 SPAN 扫描同步（连续扫描 + 固定等待，余量偏保守）。

        两大品牌均支持 `INIT:CONT` 与 `SENS:SWE:TIME?`，故实现放在基类。
        不用 `SWE:COUN`/`*OPC?`：是德 X 系列 SA 无 `SWEep:COUNt`，
        且窄 RBW/宽 SPAN 下 `*OPC?` 的可靠性不如固定等待。

        Args:
            sweep_count: 需要完成的扫描次数，默认 1
            span_hz: 当前 SPAN，用于自动选择安全系数
            factor: 扫描时间放大系数（None 则按 SPAN 自动）
            margin: 固定余量秒数（None 则按 SPAN 自动）

        Returns:
            bool: 是否成功完成
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.write(f"{self.CMD_CONT} OFF")
            sweep_time = self._query_sweep_time()

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

            sweep_count = max(1, sweep_count)
            if sweep_time and sweep_time > 0.0:
                total_time = sweep_count * sweep_time
                timeout_ms = max(120000, int(total_time * factor * 1000) + int(margin * 1000))
            else:
                timeout_ms = max(300000, 120000 * sweep_count)
            self.instrument.timeout = timeout_ms

            self.instrument.write(f"{self.CMD_CONT} ON")
            wait_s = (sweep_count * sweep_time * factor) + margin
            print(f"    等待 {wait_s:.1f}s (sweep_time={sweep_time:.3f}s × {sweep_count} × {factor})")
            time.sleep(wait_s)
            self.instrument.write(f"{self.CMD_CONT} OFF")
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
        """小 SPAN 快速扫描同步（余量比 wait_for_sweep 小）。

        适配谐波/分谐波这类小 SPAN（FFT 扫描，sweep_time 仅几十毫秒）场景。
        宽 SPAN 扫描请用 wait_for_sweep。

        Args:
            sweep_count: 需要完成的扫描次数，默认 1
            span_hz: 当前 SPAN（保留参数，便于调用方统一传参）
            factor: 扫描时间放大系数，默认 1.5
            margin: 固定余量秒数，默认 0.15
            extra_margin: 切回单次模式后再等 sweep_time×1.2 + extra_margin 秒

        Returns:
            bool: 是否成功完成
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.write(f"{self.CMD_CONT} OFF")
            sweep_time = self._query_sweep_time()

            sweep_count = max(1, sweep_count)
            if sweep_time and sweep_time > 0.0:
                wait_s = sweep_count * sweep_time * factor + margin
            else:
                wait_s = sweep_count * 0.3 + margin

            self.instrument.timeout = max(60000, int(wait_s * 1000) + 5000)
            print(f"    快速同步等待 {wait_s:.3f}s "
                  f"(sweep_time={sweep_time:.3f}s × {sweep_count} × {factor} + {margin})")

            self.instrument.write(f"{self.CMD_CONT} ON")
            time.sleep(wait_s)
            self.instrument.write(f"{self.CMD_CONT} OFF")
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
        """扫描同步超时后清理仪器状态，防止后续命令挂死。"""
        try:
            self.instrument.write("ABOR")
            self.instrument.write(f"{self.CMD_CONT} ON")
            self.instrument.write("*CLS")
        except Exception as cleanup_e:
            print(f"超时后清理仪器状态失败: {cleanup_e}")

    # ------------------------------------------------------------------
    # 通用：trace 读取
    # ------------------------------------------------------------------
    def get_trace(self, trace=1):
        """读取频谱 trace 数据 (`TRAC:DATA? TRACE<t>`)。

        Args:
            trace: trace 编号，默认 1

        Returns:
            幅度列表（dBm）；读取失败返回 None
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            # 强制 ASCII 返回，避免二进制块解析卡住
            self.instrument.write("FORM:DATA ASC")
            self.instrument.timeout = max(original_timeout, 30000)

            data = self.instrument.query(self.CMD_TRACE_QUERY.format(t=trace))

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

    # ------------------------------------------------------------------
    # 品牌相关：基类给出通用子集实现或抛 NotImplementedError
    # ------------------------------------------------------------------
    def set_center_frequency(self, frequency):
        try:
            self.instrument.write(f"{self.CMD_CENTER_FREQ} {frequency}")
        except Exception as e:
            print(f"设置中心频率失败: {e}")

    def set_span(self, span):
        try:
            self.instrument.write(f"{self.CMD_SPAN} {span}")
        except Exception as e:
            print(f"设置频率跨度失败: {e}")

    def peak_search(self, marker_num=1):
        """峰值搜索：通用子集用标记点最大搜索。"""
        try:
            self.instrument.write(f"CALC:MARK{marker_num}:MAX")
            print("执行峰值搜索")
        except Exception as e:
            print(f"峰值搜索失败: {e}")

    def measure_power(self, marker_num=1):
        """峰值搜索后读取标记点功率。"""
        try:
            self.peak_search(marker_num)
            return float(self.instrument.query(self.CMD_MARKER_YQ.format(m=marker_num)))
        except Exception as e:
            print(f"测量功率失败: {e}")
            return None


class GenericSpectrumAnalyzer(SpectrumAnalyzerBackend):
    """未知品牌的回退后端：仅下发通用 SCPI 子集，品牌独有设置跳过并告警。"""

    BRAND = "generic"

    def _warn(self, feature):
        print(f"警告: 未识别频谱仪品牌，跳过 {feature}（需品牌后端支持）")

    def set_reference_level(self, level):
        self._warn("参考电平设置")

    def set_attenuation(self, attenuation):
        self._warn("衰减设置")

    def set_attenuation_auto(self, state=True):
        self._warn("自动衰减")

    def set_preamp(self, state=True, band=None):
        self._warn("预放设置")

    def set_rbw_auto(self, state=True):
        self._warn("RBW 自动")

    def set_vbw_auto(self, state=True):
        self._warn("VBW 自动")

    def set_trace_mode(self, mode="MAXHold", trace=1):
        self._warn("trace 模式")

    def set_detector(self, detector="POSitive", trace=1):
        self._warn("检波器")
