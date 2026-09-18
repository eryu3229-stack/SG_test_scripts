# -*- coding: utf-8 -*-
"""频谱仪品牌后端基类 —— 同时充当「未知品牌」的通用回退驱动。

本类承担两件事，**只有这一个类**：

1. **基类**：承载与品牌无关的实现
   - `*IDN?` 读取、只读查询与数值解析
   - 扫描同步（`acquire_once` 确定性采集 / `accumulate_sweeps` 时间法累积）
   - trace 数据读取、错误队列读取、超时清理
   - 两大品牌共用的通用 SCPI 子集（`FREQ:CENT` / `BAND:RES` / `CALC:MARK<n>:X` 等）
2. **回退驱动**：`*IDN?` 识别不出品牌时，门面直接实例化本类。此时品牌专有设置
   （参考电平、衰减、预放、RBW/VBW 自动耦合、trace 模式、检波器、模拟解调…）
   一律**告警并跳过**，绝不抛异常 —— 跨品牌脚本要能继续跑完后面的步骤。

因此品牌后端只需覆盖「本品牌与基类不同」的指令路径；未覆盖的方法继承基类的
通用实现或告警桩。**刻意不抛 `NotImplementedError`**：那会让"这台没装该功能"
与"代码漏了实现"变成同一个异常，现场无法区分；告警桩则能明确指出缺哪一项。

指令来源：
- 罗德 R&S：R&S FSWP-B1 User Manual, 1177.5656.02 ─ 11
- 是德 Keysight：X-Series SA Mode User's & Programmer's Reference, N9060-90041
- 模拟解调：X-Series Analog Demod Mode User's & Programmer's Reference（选件 N9063EM0E）
"""
import time


class SpectrumAnalyzerBackend:
    """频谱仪后端基类，同时充当「未知品牌」的通用回退驱动。

    两点分工见模块 docstring：通用实现 + 品牌专有设置的告警桩。
    品牌后端（`KeysightSpectrumAnalyzer` / `RohdeSpectrumAnalyzer`）只覆盖
    「与本类不同」的指令路径，其余全部继承。
    """

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
        # 模拟解调（ADEMOD）当前测量类型 AM/FM/PM。由 select_demod_measurement()
        # 记录，供后续 set_demod_* 解析"按测量分树"的节点（:SENSe:AM:* 等）。
        self._demod_kind = None

    # ------------------------------------------------------------------
    # 通用：不支持项的告警桩
    # ------------------------------------------------------------------
    def _unsupported(self, feature):
        """本后端不支持该设置：打印告警并跳过（**不抛异常**，调用方继续跑）。

        两处会走到这里，带 `BRAND` 就是让现场一眼看清是哪台仪器缺哪一项：
        1. 未知品牌走本类做回退驱动（`BRAND="unknown"`）；
        2. 品牌后端确实没覆盖、或该机型无此功能。

        与「静默返回 None」的区别：静默会让"设置成功"的假象写进记录，
        而这正是本项目反复踩过的坑（仪器不报错但结果错）。
        """
        print(f"警告: 后端 {self.BRAND} 不支持 {feature}，已跳过")

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

    def _query_float_first(self, *commands):
        """依次尝试多个等价查询命令，返回第一个成功解析的数值。

        用途：同一设置在不同固件上可能只接受其中一种写法（例如预放状态的
        `...:GAIN:STAT?` 与 `...:GAIN?`）。若写死一种、恰好被拒，就要白跑一轮
        真机测试才能拿到证据，故这里做一次容错尝试。
        """
        for command in commands:
            value = self._query_float(command)
            if value is not None:
                return value
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

    def ensure_marker_on(self, marker_num=1):
        """幂等开启标记器 (`CALC:MARK<m>:STAT ON`)。

        读数前必须确保 marker 处于开启态：是德 X 系列 marker 默认 OFF，
        此时 `CALC:MARK<m>:Y?` 返回哨兵值 9.91e+37（被 `_sanitize_raw` 归为
        None）。此前只有搜峰路径顺手开过一次 marker，读数路径完全依赖"它没被
        关掉"这个假设。
        """
        try:
            self.instrument.write(f"CALC:MARK{marker_num}:STAT ON")
        except Exception as e:
            print(f"开启标记器失败: {e}")

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

    def acquire_once(self, report_errors=True):
        """采集原语：确定性完成「一次完整扫描」。**要取数值就只走这里。**

        序列：`INIT:CONT OFF` → `INIT:IMM` → `*OPC?`（阻塞到采集真正完成）
              → 可选 `SYST:ERR?` 诊断（**只打印，绝不作为失败判据**）。

        `*OPC?` 返回时 trace 必然是本次扫描的完整结果，因此不依赖任何「等够时间」
        的假设。与 `accumulate_sweeps`（时间法、仅用于 MAXHold 累积）分工明确：

            要一个准确数值        → acquire_once()
            要把连续扫描跑够时长  → accumulate_sweeps()

        Args:
            report_errors: 采集后是否把仪器错误队列打印出来**作为诊断**。
                **只报告、不判失败** —— 错误队列里的历史错误或与本次采集无关的
                错误（例如某条品牌专有设置命令被固件拒绝）绝不能让一次已经
                `*OPC?` 确认完成的采集被判为失败。早期版本把这个查询当成失败
                门限，结果在真机上每次采集都被判失败、连 marker 都没打开就退出。

        Returns:
            bool: True=触发并等到采集完成；False=触发失败或等待超时
        """
        original_timeout = None
        try:
            original_timeout = self.instrument.timeout
            self.instrument.timeout = max(original_timeout or 0, 30000)
            self.instrument.write(f"{self.CMD_CONT} OFF")
            self.instrument.write("INIT:IMM")
            self.instrument.query("*OPC?")
            if report_errors:
                self.report_error_queue(tag="采集后")
            return True
        except Exception as e:
            print(f"单次采集失败: {e}")
            self._cleanup_after_timeout()
            return False
        finally:
            if original_timeout is not None:
                try:
                    self.instrument.timeout = original_timeout
                except Exception:
                    pass

    def trigger_single(self):
        """兼容旧名：等价于 `acquire_once()`。"""
        return self.acquire_once()

    def report_error_queue(self, tag="", limit=10):
        """把 SCPI 错误队列内容打印出来（纯诊断，顺带清空队列）。

        队列为空时不打印任何东西。返回错误字符串列表。
        这是排查"哪条命令被固件拒绝"的唯一手段 —— 控制台打印的一直是请求值。
        """
        errors = self.get_error_queue(limit)
        if errors:
            prefix = f"（{tag}）" if tag else ""
            print(f"    仪器错误队列{prefix}: " + "；".join(errors))
        return errors

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
    # 通用：扫描累积（时间法，仅杂散的 MAXHold 累积使用）
    # ------------------------------------------------------------------
    def _query_sweep_time(self):
        """查询单次扫描时间，查询失败返回 0.0。"""
        try:
            return float(self.instrument.query(self.CMD_SWEEP_TIME_Q))
        except Exception:
            return 0.0

    def accumulate_sweeps(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        """连续扫描累积 N 次（时间法）——**只用于 MAXHold 累积，不是取数原语**。

        使用者只有杂散流程：它需要在 MAXHold 迹线上累积多次扫描，而此时不需要
        等待任何单次采集完成。谐波/分谐波/小信号这类「要一个准确数值」的流程
        一律用 `acquire_once()`，不得调用本方法（历史上混用正是 trace 不新鲜、
        marker 读回哨兵值的根源）。

        两大品牌均支持 `INIT:CONT` 与 `SENS:SWE:TIME?`，故实现放在基类。
        这里不用 `SWE:COUN`：是德 X 系列 SA 无 `SWEep:COUNt`；而本方法的目的
        只是「让连续扫描跑够时长」，不需要等某一次采集完成，所以用 `SWE:TIME?`
        加系数估算即可。**要等某一次采集真正完成请用 `acquire_once()`。**

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

    def wait_for_sweep(self, sweep_count=1, span_hz=None, factor=None, margin=None):
        """兼容旧名：等价于 `accumulate_sweeps()`（仅供本地旧脚本调用）。"""
        return self.accumulate_sweeps(sweep_count, span_hz=span_hz,
                                      factor=factor, margin=margin)

    def wait_for_sweep_fast(self, sweep_count=1, span_hz=None, factor=1.5, margin=0.15, extra_margin=0.0):
        """已弃用：保留只为兼容旧调用（原 `_sweep_sync` 的快速档）。

        它本质仍是时间法（`CONT ON` → 等一段固定时间 → `CONT OFF`），**不保证
        单次采集已完成**。需要准确数值请改用 `acquire_once()`；需要 MAXHold
        累积请用 `accumulate_sweeps()`。

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
    # 通用子集实现（两大品牌短写一致，基类直接实现，品牌后端按需覆盖）
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
            # 必须先开 marker：marker 处于关闭态时，MAX / X? / Y? 都可能返回哨兵值
            self.ensure_marker_on(marker_num)
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

    # ------------------------------------------------------------------
    # 品牌专有设置 —— 基类只告警并跳过（由品牌后端覆盖后才有实际动作）
    # ------------------------------------------------------------------
    def set_reference_level(self, level):
        """参考电平：品牌专有，基类仅告警。"""
        self._unsupported("参考电平设置")

    def set_attenuation(self, attenuation):
        """输入衰减：品牌专有，基类仅告警。"""
        self._unsupported("衰减设置")

    def set_attenuation_auto(self, state=True):
        """衰减自动耦合：品牌专有，基类仅告警。"""
        self._unsupported("自动衰减")

    def set_preamp(self, state=True, band=None):
        """内置预放：品牌专有（罗德传增益值，是德传波段），基类仅告警。"""
        self._unsupported("预放设置")

    def set_rbw_auto(self, state=True):
        """RBW 自动耦合：品牌专有（节点名不同），基类仅告警。"""
        self._unsupported("RBW 自动")

    def set_vbw_auto(self, state=True):
        """VBW 自动耦合：品牌专有（节点名不同），基类仅告警。"""
        self._unsupported("VBW 自动")

    def set_trace_mode(self, mode="MAXHold", trace=1):
        """trace 模式：品牌专有（取值表不同），基类仅告警。"""
        self._unsupported("trace 模式")

    def set_detector(self, detector="POSitive", trace=1):
        """检波器：品牌专有（取值表不同），基类仅告警。"""
        self._unsupported("检波器")

    def set_detector_auto(self, state=True, trace=1):
        """检波器自动耦合：仅是德实现，其余后端告警跳过。"""
        self._unsupported("检波器自动耦合设置")

    def set_sweep_points(self, points):
        """扫描点数：仅是德实现（`SENS:SWE:POIN`），其余后端告警跳过。"""
        self._unsupported("扫描点数设置")

    # ------------------------------------------------------------------
    # 模拟解调（ADEMOD）—— 基类给出显式的"不支持"默认
    #
    # 目前只有"是德 X 系列 + N9063EM0E 模拟解调测量选件"有这套命令树
    # （模式名 ADEMOD）；罗德的解调走 VSA/FSWP 的另一套测量树，本驱动不覆盖。
    #
    # 为什么在基类留桩而不是让子类缺方法：跨品牌脚本跑到解调步骤时会撞
    # AttributeError，现场无法区分"这台没装选件"和"代码漏了"。有桩就能
    # 打印出是哪台仪器、缺哪一项，然后继续跑后面的步骤。
    # ------------------------------------------------------------------
    DEMOD_KINDS = ("AM", "FM", "PM")

    def select_demod_measurement(self, kind="AM", preset=False):
        """选择 AM/FM/PM 解调测量（仅 ADEMOD 支持）。"""
        self._unsupported("解调测量选择")

    def set_demod_span(self, span_hz):
        self._unsupported("解调跨度")

    def set_demod_center_frequency(self, frequency_hz):
        self._unsupported("解调载波频率")

    def set_demod_rbw(self, bandwidth=None, auto=None):
        self._unsupported("解调分辨率带宽")

    def set_demod_channel_bandwidth(self, bandwidth_hz):
        self._unsupported("解调通道带宽")

    def set_af_span(self, start_hz=None, stop_hz=None):
        self._unsupported("AF 频谱范围")

    def set_af_bandwidth(self, bandwidth=None, auto=None):
        self._unsupported("AF 分辨率带宽")

    def set_post_demod_filter(self, which, value, manual_hz=None):
        self._unsupported("后解调滤波器")

    def set_demod_time(self, seconds=None, auto=None):
        self._unsupported("解调时间")

    def set_demod_periodic(self, state):
        self._unsupported("调制周期性")

    def set_demod_average(self, state=None, count=None):
        self._unsupported("解调平均")

    def set_am_genre(self, genre):
        self._unsupported("AM 解调类型")

    def set_fm_deemphasis(self, value):
        self._unsupported("FM 去加重")

    def set_speaker(self, state):
        self._unsupported("扬声器")

    def set_demod_unit(self, unit, kind=None, window="AFSPectrum"):
        self._unsupported("解调单位")

    def read_demod_settings(self, kind=None):
        """读回解调设置；本后端无解调测量，返回空字典（不是全 None）。"""
        self._unsupported("解调设置读回")
        return {}

    def read_demod_center_frequency(self):
        """读回解调载波频率；本后端无解调测量，返回 None。"""
        self._unsupported("解调载波频率读回")
        return None

    def read_demod_metric_display(self, kind=None):
        """读回「调制量度显示」设置；本后端无解调测量，返回 None。"""
        self._unsupported("调制量度显示读回")
        return None

    def read_demod_metrics(self, kind=None, acquire=True):
        """读取解调测量结果（调制深度 / 频偏 / 相偏 / 调制速率）。

        与 `read_demod_settings()` 一样只是告警桩：本后端没有解调测量树
        （只有是德 X 系列 + ADEMOD 选件有）。返回带 `error` 的字典而不是
        空字典，好让调用方能一眼看出"这台不支持"，而不是把空结果当成
        "测了但没测到"。
        """
        self._unsupported("解调结果读取")
        return {"error": f"后端 {self.BRAND} 无解调测量树，无法读取解调结果"}
