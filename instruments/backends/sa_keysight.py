# -*- coding: utf-8 -*-
"""是德 Keysight 频谱仪后端（X 系列 SA：N9000B/N9010B/N9020B/N9030B 等）。

指令来源：
1. X-Series Signal Analyzers
   Spectrum Analyzer Mode User's & Programmer's Reference
   Manual Part Number N9060-90041, Edition 19 (2025-12)
   均取 Swept SA 测量下的指令。
2. X-Series Signal Analyzers
   Analog Demod Mode User's & Programmer's Reference
   模拟解调（AM/FM/PM Demod，模式名 ADEMOD）测量，需选件 N9063EM0E。

手册页面引用均为文档页脚页码。
"""
import math

from backends.sa_base import SpectrumAnalyzerBackend


class KeysightSpectrumAnalyzer(SpectrumAnalyzerBackend):
    """是德 X 系列 SA 后端。"""

    BRAND = "keysight"

    # ---------------------------------------------------------------- 幅度
    def set_reference_level(self, level):
        """参考电平：`DISPlay:WINDow[1]:TRACe:Y[:SCALe]:RLEVel <real>`。

        例：`:DISP:WIND:TRAC:Y:RLEV 20 dBm`（手册 p.213）
        """
        try:
            self.instrument.write(f"DISP:WIND:TRAC:Y:RLEV {level}")
        except Exception as e:
            print(f"设置参考电平失败: {e}")

    def set_attenuation(self, attenuation):
        """输入衰减：`[:SENSe]:POWer[:RF]:ATTenuation <rel_ampl>`。

        例：`:SENS:POW:RF:ATT 20`（手册 p.226）
        注意：手动下发会自动把衰减从参考电平解耦。

        下发用**显式路径**：项目 README 记录过 `POW:ATT` 在 N9030B 上报
        `undefined header`（N9030B 实测）。命令被拒不只是衰减没设上，
        还会往错误队列里灌错，干扰后续诊断。
        """
        try:
            self.instrument.write(f"SENS:POW:RF:ATT {attenuation}")
        except Exception as e:
            print(f"设置衰减失败: {e}")

    def set_attenuation_auto(self, state=True):
        """衰减自动耦合：`[:SENSe]:POWer[:RF]:ATTenuation:AUTO OFF|ON|0|1`。

        例：`:SENS:POW:RF:ATT:AUTO ON`（手册 p.227）
        """
        try:
            self.instrument.write(f"SENS:POW:RF:ATT:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置自动衰减失败: {e}")

    def set_preamp(self, state=True, band=None):
        """内置预放：`[:SENSe]:POWer[:RF]:GAIN[:STATe]` + `:GAIN:BAND`。

        例：`:POW:GAIN OFF` / `:POW:GAIN:BAND LOW`（手册 p.235）

        Args:
            state: True 开预放，False 关
            band: "LOW"(仅低波段) / "FULL"(全频段)；
                  兼容罗德写法 15→LOW、30→FULL
        """
        try:
            if state:
                resolved_band = self._resolve_preamp_band(band)
                if resolved_band:
                    self.instrument.write(f"SENS:POW:RF:GAIN:BAND {resolved_band}")
                self.instrument.write("SENS:POW:RF:GAIN:STAT ON")
            else:
                self.instrument.write("SENS:POW:RF:GAIN:STAT OFF")
        except Exception as e:
            print(f"设置预放失败: {e}")

    @staticmethod
    def _resolve_preamp_band(band):
        """把兼容参数解析为 Keysight 预放波段 LOW/FULL。"""
        if band is None:
            return None
        if isinstance(band, (int, float)):
            # 罗德的增益值语义：15 dB 对应低波段，30 dB 对应全频段
            return "LOW" if int(band) <= 15 else "FULL"
        key = str(band).upper().strip()
        if key in ("LOW", "FULL"):
            return key
        return None

    # ---------------------------------------------------------------- 标记点
    def peak_search(self, marker_num=1):
        """峰值搜索：`CALCulate:MARKer[1]|2|…|24:MAXimum`。

        例：`:CALC:MARK2:MAX`（手册 p.330）
        前置 `CALC:MARK<n>:STAT ON`：X 系列 marker 默认 OFF，`CALC:MARK:MAX`
        虽会开启 marker，但在无有效 trace 时可能定位不到，令 X? 返回哨兵。
        """
        try:
            self.instrument.write(f"CALC:MARK{marker_num}:STAT ON")
            self.instrument.write(f"CALC:MARK{marker_num}:MAX")
            print("执行峰值搜索")
        except Exception as e:
            print(f"峰值搜索失败: {e}")

    def measure_power(self, marker_num=1):
        """峰值搜索后读取标记点功率 (`CALC:MARK<m>:Y?`，手册 p.322)。"""
        try:
            self.peak_search(marker_num)
            return float(self.instrument.query(self.CMD_MARKER_YQ.format(m=marker_num)))
        except Exception as e:
            print(f"测量功率失败: {e}")
            return None

    # ---------------------------------------------------------------- 带宽
    def set_rbw_auto(self, state=True):
        """RBW 自动耦合：`[:SENSe]:BANDwidth|BWIDth[:RESolution]:AUTO`（手册 p.255）。"""
        try:
            self.instrument.write(f"BAND:RES:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置RBW自动失败: {e}")

    def set_vbw_auto(self, state=True):
        """VBW 自动耦合：`[:SENSe]:BANDwidth|BWIDth:VIDeo:AUTO`（手册 p.258）。"""
        try:
            self.instrument.write(f"BAND:VID:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置VBW自动失败: {e}")

    # ---------------------------------------------------------------- 迹线/检波器
    # 手册 p.410：TRACe[1]|2|…|6:MODE WRITe|MAXHold|MINHold|VIEW|BLANk
    # （该命令为向后兼容保留，当前推荐 :TRACe:TYPE / :UPDate / :DISPlay）
    _TRACE_MODE_MAP = {
        "WRITE": "WRITe", "WRIT": "WRITe", "WRITe": "WRITe",
        "MAXH": "MAXHold", "MAXHold": "MAXHold",
        "MINH": "MINHold", "MINHold": "MINHold",
        "VIEW": "VIEW",
        "BLANK": "BLANk", "BLANk": "BLANk",
    }

    # 手册 p.557：[SENSe]:DETector:TRACe[1]|2|…|6
    #   AVERage | NEGative | NORMal | POSitive | SAMPle | QPEak | EAVerage | RAVerage
    # 注意：X 系列无 APEak 取值，自动检波由 :DETector:TRACe:AUTO ON 实现
    _DETECTOR_MAP = {
        "AVERAGE": "AVERage", "AVER": "AVERage", "AVERage": "AVERage",
        "NEG": "NEGative", "NEGative": "NEGative",
        "NORM": "NORMal", "NORMAL": "NORMal", "NORMal": "NORMal",
        "POS": "POSitive", "POSitive": "POSitive",
        "SAMP": "SAMPle", "SAMPLE": "SAMPle", "SAMPle": "SAMPle",
        "QPEAK": "QPEak", "QPE": "QPEak", "QPEak": "QPEak",
        "EAVERAGE": "EAVerage", "EAVer": "EAVerage",
        "RAVERAGE": "RAVerage", "RAVer": "RAVerage",
    }

    def set_trace_mode(self, mode="MAXHold", trace=1):
        """迹线模式：`TRACe[1]|2|…|6:MODE WRITe|MAXHold|MINHold|VIEW|BLANk`。

        Args:
            mode: 兼容简写 MAXH/WRITE/MINH/VIEW/BLANK
            trace: trace 编号，默认 1
        """
        try:
            ks_mode = self._TRACE_MODE_MAP.get(str(mode).upper(), mode)
            self.instrument.write(f"TRAC{trace}:MODE {ks_mode}")
        except Exception as e:
            print(f"设置trace模式失败: {e}")

    def set_detector(self, detector="POSitive", trace=1):
        """检波器：`[:SENSe]:DETector:TRACe[<t>] <detector>`。

        例：`:DET:TRAC AVER` / `:DET:TRAC1 AVER`（手册 p.557）

        Args:
            detector: 兼容简写 POS/NEG/AVERAGE/SAMP/QPEAK/NORMAL
            trace: trace 编号，默认 1
        """
        try:
            ks_detector = self._DETECTOR_MAP.get(str(detector).upper(), detector)
            self.instrument.write(f"DET:TRAC{trace} {ks_detector}")
        except Exception as e:
            print(f"设置检波器失败: {e}")

    def set_detector_auto(self, state=True, trace=1):
        """检波器自动耦合：`[:SENSe]:DETector:TRACe[<t>]:AUTO ON|OFF`（手册 p.559）。"""
        try:
            self.instrument.write(f"DET:TRAC{trace}:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置检波器自动失败: {e}")

    def set_sweep_points(self, points):
        """扫描点数：`[:SENSe]:SWEep:POINts <integer>`，例 `:SWE:POIN 5001`（手册 p.397）。"""
        try:
            self.instrument.write(f"SWE:POIN {points}")
        except Exception as e:
            print(f"设置扫描点数失败: {e}")

    # ---------------------------------------------------------------- 读回校验
    def _read_extra_settings(self):
        """读回参考电平与输入衰减（与上面的下发路径一一对应）。"""
        return {
            "ref_level_dbm": self._query_float("DISP:WIND:TRAC:Y:RLEV?"),
            "input_att_db": self._query_float("SENS:POW:RF:ATT?"),
            # 预放状态：1=开 0=关。开预放会把底噪压低 10~30 dB，
            # 不读回就无法解释"实测底噪比模型好 10 dB"这类偏差。
            # 两种等价写法都试（不同固件可能只认一种）
            "preamp_on": self._query_float_first(
                "SENS:POW:RF:GAIN:STAT?", "SENS:POW:RF:GAIN?"),
            # Y 轴刻度 dB/div：与参考电平一起决定显示下限（ref − 刻度×10 格），
            # 是判断"底噪读数是否被显示范围截断"的依据。
            "scale_div_db": self._query_float_first(
                "DISP:WIND:TRAC:Y:PDIV?", "DISP:WIND:TRAC:Y:SCAL:PDIV?"),
        }

    # ================================================================ 模拟解调
    # 手册：X-Series Analog Demod Mode User's & Programmer's Reference
    # 测量：AM Demod（3.1 节）/ FM Demod（3.2 节）/ PM Demod（3.3 节）
    # 模式名 ADEMOD（`:INSTrument:CATalog?` 里是 `ADEMOD 234`），
    # 需选件 N9063EM0E；未装选件时整个命令树不存在。
    #
    # 与 SA 模式的关系：
    #   · **中心频率共用** `[:SENSe]:FREQuency:CENTer`（手册 p220）——
    #     直接用 `set_center_frequency()`，故此处不再重复实现。
    #   · **跨度不共用**：ADEMOD 的 Span 是**按测量分树**的
    #     `[:SENSe]:AM|FM|PM:FREQuency:SPAN`（手册 p221），
    #     与 SA 模式的 `[:SENSe]:FREQuency:SPAN` 是两个节点。
    #
    # 范围口径（用户 2026-09-18「不要考虑比较复杂的设置」）：
    #   每种测量只保留 一个主参数 + 一个带宽/范围 + 一个开关 的基础设置。
    #   以下一律不做，需要时按手册页码单独补，不要顺手加回来：
    #     · FM Stereo 测量（`CONFigure:FMSTereo:*`）—— 自带 MPX/MONO 子设置
    #     · 载波自动搜索（`:SENSe:<X>:CARRier:FREQuency|PHASe:AUTO`）
    #     · 显示视图与窗口刻度（`DISPlay:*`）—— 只影响看，不影响取值
    #     · SINAD/THD 与失真指标（`:CALCulate:<X>:SINad:*`、`...:METRics:DISTortion`）
    #     · 信令陷波（`:SENSe:FM:SIGNaling:NOTCh:*`）
    #     · 模拟/数字输出与回放（`:SENSe:<X>:ANALog:OUTPut`、`OUTPut:*`、
    #       `CALCulate:<X>:PLAY:*`）、保存与调回（`MMEMory:<X>:RSTate:MODE`）
    #     · 触发（`:TRIGger:AM|FM|PM:*`）
    #
    # 单位书写：频率带 Hz、时间带 s。`:UNIT:` 子系统能改全局默认单位
    #   （本文件另有 `:UNIT:AM/FM/PM:AFSPectrum`、`:UNIT:PM:DEMod`），
    #   裸数值的含义会随全局设置漂移；显式带单位与信号源驱动保持一致。
    #
    # 真机实测备注（N9030B / MY60089385 / 固件 A.36.22）：
    #   · **只读探测**：现场已装并激活 **N9063EM0E**
    #     （`:INSTrument:CATalog?` 含 `ADEMOD 234`，
    #     `:SYSTem:APPLication:CURRent:NAME?` 回 `"N9063EM0E"`）；
    #     本文件用到的节点逐个查询全部通过、错误队列干净。
    #   · **写入验收（用户授权）**：SA 模式下 `:INST:SEL ADEMOD` +
    #     `:CONF:{AM,FM,PM}:NDEF` 均成功；AM 13 项基础设置读回 17/17 一致；
    #     123 条指令驱动侧零错误；结束时已切回 SA 模式。
    #   · `*OPT?` **不列** N9063EM0E 这类测量应用，别用它判断有无解调能力。
    #   · **读回格式**（判"请求值是否落地"必须知道）：开关类回读 `1`/`0`
    #     而非 `ON`/`OFF`；单位回读**短写**（下 `DEGRee` 回 `DEGR`）；
    #     数值回读为科学计数法字符串。`read_demod_settings` 已统一 strip()。
    #   · 实测确认的两条仪器行为：① 后解调滤波器**互斥** —— 开 BPF 会把
    #     HPF/LPF 自动关成 OFF；② `:FM:PER:` **非法**（`-113 Undefined
    #     header`），FM 的周期性节点只能用 `PERIodic`（短写 `PERI`）。
    # ================================================================

    DEMOD_KINDS = ("AM", "FM", "PM")

    # 后解调滤波器取值（手册 p244 AM / p358 FM / p481 PM）
    _DEMOD_HPF = ("OFF", "HPF20", "HPF50", "HPF300", "HPF400", "MANual")
    # 手册 p246 AM / p359 FM / p483 PM
    _DEMOD_LPF = ("OFF", "LPF300", "LPF3K", "LPF15K", "LPF30K", "LPF80K",
                  "LPF300K", "LPF100K", "MANual")
    # 手册 p248 AM / p362 FM / p485 PM
    _DEMOD_BPF = ("OFF", "CCITT", "AWEighting", "CWEighting", "CMESsage",
                  "CCIR1k", "CCIR2k", "CUNWeighting")
    # AM 解调类型（手册 p240）
    _DEMOD_AM_GENRE = ("DSB", "SSB")
    # FM 去加重（手册 p365）
    _DEMOD_FM_DEEMPHASIS = ("OFF", "US25", "US50", "US75", "US750")

    #: 周期性节点的**手册写法按测量不同**，短写也随之不同：
    #:   AM `PERiodic`（短写 PER；手册另留向后兼容别名 PERIodic）
    #:   FM `PERIodic`（短写 PERI；手册里没有 PERiodic 这个写法）
    #:   PM `PERiodic`（短写 PER；另有别名 PERIodic）
    #: 手册示例也印证：`:AM:PER OFF` / `:PM:PER OFF`，但 FM 是 `:FM:PERI OFF`。
    #: 因此这里统一发**全写**：短写 `PER` 在 FM 上既非短写也非全写，
    #: 属可变行为，不赌固件宽容度。
    _DEMOD_PERIODIC_NODE = {"AM": "PERiodic", "FM": "PERIodic", "PM": "PERiodic"}

    #: 后解调滤波器节点名（`which` 入参 -> SCPI 节点 + 取值表）
    _DEMOD_FILTERS = {
        "HP": ("HPF", _DEMOD_HPF),
        "LP": ("LPF", _DEMOD_LPF),
        "BP": ("BPF", _DEMOD_BPF),
    }

    #: 滤波器取值的写法别名。
    #: `MANual` 的 SCPI 短写就是 `MAN`（手册示例直接写作 `:AM:HPF MAN`），
    #: 而 `MAN` 与 `MANual` 的字面不等，按长写逐一比对会把它误判成非法值。
    _DEMOD_FILTER_ALIASES = {"MAN": "MANual"}

    #: 单位简写 -> 手册长写。手册给的是 `RADian|DEGRee|DBRadian|DBDegree`
    #: 这类大小写混排写法，调用方按简写传更省事，下发时统一转手册写法。
    _DEMOD_UNIT_ALIASES = {
        "PERC": "PERCent", "PERCENT": "PERCent",
        "DBAM": "DBAM",
        "HZ": "HZ",
        "DBHZ": "DBHZ",
        "RAD": "RADian", "RADIAN": "RADian",
        "DEGR": "DEGRee", "DEGREE": "DEGRee",
        "DBR": "DBRadian", "DBRADIAN": "DBRadian",
        "DBD": "DBDegree", "DBDEGREE": "DBDegree",
    }

    #: (测量类型, 窗口) -> 允许的单位简写。
    #: 手册 p167 AM / p281 FM / p403 PM。
    #: AM 的第三个取值手册印成 `DBC_HZ`——SCPI 助记符不允许下划线，
    #: 这是手册排版错误，真名未验证，故**不纳入**允许集合；
    #: 需要 dBc/Hz 时先上机确认真名再补进这里。
    _DEMOD_UNITS = {
        ("AM", "AFSPectrum"): ("PERC", "PERCENT", "DBAM"),
        ("FM", "AFSPectrum"): ("HZ", "DBHZ"),
        ("PM", "AFSPectrum"): ("RAD", "RADIAN", "DEGR", "DEGREE",
                               "DBR", "DBRADIAN", "DBD", "DBDEGREE"),
        ("PM", "DEMod"): ("RAD", "RADIAN", "DEGR", "DEGREE"),
    }

    # ---------------------------------------------------------------- 解调工具
    def _demod_write(self, command):
        """下发一条解调指令；失败打印原因并返回 False。"""
        try:
            self.instrument.write(command)
            return True
        except Exception as e:
            print(f"解调指令下发失败: {command} -> {e}")
            return False

    @staticmethod
    def _demod_enum(value, allowed, name):
        """校验枚举取值；不在允许集合内则打印原因并返回 None（调用方不下发）。

        **不**替调用方"就近取整"、也不猜测替代写法：仪器对非法枚举要么报错、
        要么静默取整，两种结果都会让"设置成功"的假象写进记录。返回的是
        `allowed` 里的规范写法，故可同时用简写匹配、按手册长写下发。
        """
        if value is None:
            print(f"参数 {name} 为空，未下发")
            return None
        text = str(value).strip().upper()
        for candidate in allowed:
            if candidate.upper() == text:
                return candidate
        print(f"参数 {name}={value!r} 不在允许取值 {allowed} 内，未下发")
        return None

    def _resolve_demod_kind(self, kind=None):
        """解析本次要操作的解调测量类型（AM/FM/PM）。

        取值优先级：显式入参 > `select_demod_measurement()` 记住的类型 >
        问仪器 `:CONFigure?`。三者都拿不到就返回 None，调用方跳过下发。

        为什么必须解析：解调节点是**按测量分树**的（`:SENSe:AM:*` /
        `:SENSe:FM:*` / `:SENSe:PM:*`），发错树会得到 `-113 Undefined header`
        或悄悄改到别的测量上。
        """
        if kind is not None:
            return self._demod_enum(kind, self.DEMOD_KINDS, "kind")
        if self._demod_kind in self.DEMOD_KINDS:
            return self._demod_kind
        current = self.query(":CONFigure?")
        if current is not None:
            key = str(current).strip().strip('"').upper()
            if key in self.DEMOD_KINDS:
                self._demod_kind = key
                return key
        print(f"警告: 无法确定当前解调测量类型（:CONFigure? -> {current!r}）；"
              f"请先调用 select_demod_measurement()，或显式传 kind")
        return None

    # ---------------------------------------------------------------- 测量选择
    def select_demod_measurement(self, kind="AM", preset=False):
        """进入 ADEMOD 模式并选择 AM / FM / PM 解调测量。

        两条指令（手册 p152 + p156）：
            `:INSTrument:SELect ADEMOD`   切到模拟解调模式（等价 `:INST:NSEL 234`）
            `:CONFigure:AM`               = Meas Preset：换测量**并**复位该测量的设置
            `:CONFigure:AM:NDEFault`      只换测量，**不动**已有设置

        解调命令树只在本模式下存在，所以这一步必须在其它 `set_demod_*` 之前调用。

        Args:
            kind: "AM" / "FM" / "PM"
            preset: True 走 `:CONFigure:<kind>`（测量设置回到预设态）；
                    False 走 `:CONFigure:<kind>:NDEFault`（保留当前设置）

        Returns:
            bool: 是否下发成功
        """
        key = self._demod_enum(kind, self.DEMOD_KINDS, "kind")
        if key is None:
            return False
        if not self._demod_write("INST:SEL ADEMOD"):
            return False
        # 模式切换会重置 SCPI 状态寄存器（手册 p152），故先切模式再选测量
        ok = self._demod_write(f"CONF:{key}" if preset else f"CONF:{key}:NDEF")
        if ok:
            self._demod_kind = key
        return ok

    # ---------------------------------------------------------------- 范围与带宽
    def set_demod_span(self, span_hz):
        """解调测量的 RF 跨度：`[:SENSe]:AM|FM|PM:FREQuency:SPAN <freq>`。

        例 `:AM:FREQ:SPAN 10 MHz`（手册 p221 AM / p335 FM；预设 75 kHz）

        注意这是**按测量分树**的节点，不是 SA 模式的
        `[:SENSe]:FREQuency:SPAN`；两者互不影响。
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        return self._demod_write(f"SENS:{key}:FREQ:SPAN {span_hz} Hz")

    def set_demod_center_frequency(self, frequency_hz):
        """解调测量的**载波频率**（RF Spectrum 窗口中心）：`[:SENSe]:FREQuency:CENTer`。

        例 `:FREQ:CENT 1 GHz`（手册 p220 "Center Frequency"）

        ⚠ **节点归属不对称，别想当然**：载波频率走的是 **SA 模式的节点**
        （`[:SENSe]:FREQuency:CENTer`，**不在** `:AM|FM|PM` 分树里），
        而 Span 却在分树下（`[:SENSe]:AM:FREQuency:SPAN`，手册 p221）。
        手册另注明该值 "is retained as you go from measurement to measurement"，
        所以切测量会保留它 —— 换频点必须显式重发，否则解调的是上一个频点。

        为什么不直接复用 `set_center_frequency()`：两者下发的是同一条 SCPI，
        但语义不同（SA 扫描窗中心 / 解调载波）。单列出来，读代码时不会误以为
        "解调下面还有 SA 的 span 在生效"。
        """
        try:
            self.instrument.write(f"SENS:FREQ:CENT {frequency_hz} Hz")
        except Exception as e:
            print(f"设置解调载波频率失败: {e}")

    def read_demod_center_frequency(self):
        """读回解调载波频率（Hz）；读不到返回 None。用于确认真的调到了目标频点。"""
        return self._query_float("SENS:FREQ:CENT?")

    def read_demod_metric_display(self, kind=None):
        """读回「调制量度显示」设置：`:DISPlay:<K>:VIEW:METRics:MMAGnitude?`（手册 p206）。

        Returns:
            str: ALL / PPK / PNPK / RMS / RMSR；读不到 None

        ⚠ 为什么要读：该设置决定哪些调制量度被**计算**。手册 p206 明写：
        当它为 `PPK` / `PNPK` / `RMS` 时，**其余调制量度会被装入 "not a number"**
        （面板上显示 `---`）。若固件对 `:FETC:<K>?` 走同一套计算，那些位置就会
        回 NaN 或哨兵值 —— 典型的"不报错但结果错"。
        本方法**只读不写**：写它属 `:DISPlay:*` 子系统，是驱动明确不做的范围；
        流程侧用它判断本次读数是否可信（调用方默认走 Meas Preset，预设值为 ALL）。
        """
        key = self._resolve_demod_kind(kind)
        if key is None:
            return None
        raw = self.query(f"DISP:{key}:VIEW:METR:MMAG?")
        return None if raw is None else str(raw).strip().strip('"')

    def set_demod_rbw(self, bandwidth=None, auto=None):
        """解调测量的 RF 分辨率带宽：`[:SENSe]:AM|FM|PM:BANDwidth[:RESolution]`。

        例 `:AM:BAND:RES 5.1 kHz` / `:AM:BAND:RES:AUTO ON`（手册 p203-204）

        Args:
            bandwidth: 手动带宽（Hz）。只允许仪器支持的离散值，仪器会就近**向上**
                       取到可用的 RBW；自动耦合时约为 Span/106（不超过 3 MHz）。
            auto: True/False 切换自动耦合；None 表示不动。
                  只给 bandwidth 时下发数值即可自动解耦（与 `set_rbw` 同规则）。

        Returns:
            bool: 是否至少下发成功一条
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        done = False
        if bandwidth is not None:
            done |= self._demod_write(f"SENS:{key}:BAND:RES {bandwidth} Hz")
        if auto is not None:
            done |= self._demod_write(
                f"SENS:{key}:BAND:RES:AUTO {'ON' if auto else 'OFF'}")
        if not done:
            print("set_demod_rbw: bandwidth 与 auto 都为空，未下发")
        return done

    def set_demod_channel_bandwidth(self, bandwidth_hz):
        """解调通道带宽：`[:SENSe]:AM|FM|PM:BANDwidth:CHANnel <freq>`。

        例 `:AM:BAND:CHAN 200 kHz`（手册 p204 AM / p318 FM / p441 PM）

        这是解调本身的主参数：决定进入解调器的带宽，也决定送给扬声器的
        通路 RBW。带宽 > 8 MHz 时仪器会给 "Settings Alert; Analog Output"
        类告警（手册 p205），不报错。
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        return self._demod_write(f"SENS:{key}:BAND:CHAN {bandwidth_hz} Hz")

    # ---------------------------------------------------------------- AF 频谱
    def set_af_span(self, start_hz=None, stop_hz=None):
        """AF（音频）频谱显示范围：`[:SENSe]:AM|FM|PM:AFSPectrum:FREQuency:STARt|STOP`。

        例 `:AM:AFSP:FREQ:STAR 10 Hz` / `:AM:AFSP:FREQ:STOP 20 kHz`
        （手册 p223-224 AM / p337 FM；预设 0 Hz ~ 20 kHz）

        仪器约束（手册 p223）：Start 不能 ≥ Stop，且差值不得小于 10 Hz；
        违反时仪器会**自行改写另一端**以保持 10 Hz 间隔，不报错 —— 所以
        改完要读回确认，别假定两端都按请求生效。

        Args:
            start_hz: AF 起点（0 ~ 99.99999 MHz）；None 表示不动
            stop_hz: AF 终点（10 Hz ~ 100 MHz）；None 表示不动
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        done = False
        if start_hz is not None:
            done |= self._demod_write(f"SENS:{key}:AFSP:FREQ:STAR {start_hz} Hz")
        if stop_hz is not None:
            done |= self._demod_write(f"SENS:{key}:AFSP:FREQ:STOP {stop_hz} Hz")
        if not done:
            print("set_af_span: start_hz 与 stop_hz 都为空，未下发")
        return done

    def set_af_bandwidth(self, bandwidth=None, auto=None):
        """AF 频谱分辨率带宽：`[:SENSe]:AM|FM|PM:AFSPectrum:BANDwidth`。

        与后面的 `...:BANDwidth:AUTO ON|OFF|1|0` 是**两条独立指令**
        （AUTO 不是默认子节点，不像 `BANDwidth[:RESolution]` 那样可省）。
        例 `:AM:AFSP:BAND 1 kHz` / `:AM:AFSP:BAND:AUTO ON`（手册 p206）

        只接受离散值，数值会被就近向上取整到可用带宽；自动耦合约为
        Span/106 且不超过 3 MHz。范围 1 Hz ~ 8 MHz，预设 180 Hz。
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        done = False
        if bandwidth is not None:
            done |= self._demod_write(f"SENS:{key}:AFSP:BAND {bandwidth} Hz")
        if auto is not None:
            done |= self._demod_write(
                f"SENS:{key}:AFSP:BAND:AUTO {'ON' if auto else 'OFF'}")
        if not done:
            print("set_af_bandwidth: bandwidth 与 auto 都为空，未下发")
        return done

    # ---------------------------------------------------------------- 后解调滤波
    def set_post_demod_filter(self, which, value, manual_hz=None):
        """后解调滤波器（高通 / 低通 / 带通），三种测量同构。

        | which | 节点                          | 取值                                    | 手册页    |
        |-------|-------------------------------|-----------------------------------------|-----------|
        | "HP"  | `[:SENSe]:<X>:HPFilter`       | OFF/HPF20/HPF50/HPF300/HPF400/MANual    | 244/358/481 |
        | "LP"  | `[:SENSe]:<X>:LPFilter`       | OFF/LPF300/LPF3K/…/LPF100K/MANual       | 246/359/483 |
        | "BP"  | `[:SENSe]:<X>:BPFilter`       | OFF/CCITT/AWEighting/CWEighting/…       | 248/362/485 |

        例 `:AM:HPF HPF20` / `:AM:LPF LPF3K` / `:AM:BPF CCITT`

        **互斥副作用（手册 p362）**：开任何一种带通滤波会关掉高通与低通；
        反之开高通也会关掉带通。所以"设置完 HP 再设置 BP"的结果是只剩 BP ——
        需要组合时先看清这条，或设置后读回确认。

        Args:
            which: "HP" / "LP" / "BP"（兼容 "HPF"/"LPF"/"BPF"、"HIGH"/"LOW"/"BAND"）
            value: 上表取值；手动项写 `MANual` 或它的短写 `MAN` 都可以
            manual_hz: 选 MANual 时的 3 dB 截止频率（Hz）。
                       HP 预设 500 Hz（下限 20 Hz），LP 预设 300 Hz（下限 300 Hz）；
                       带通无手动项，传了会被忽略。

        Returns:
            bool: 是否下发成功
        """
        node, allowed = self._DEMOD_FILTERS.get(
            self._normalize_filter_alias(which), (None, None))
        if node is None:
            print(f"参数 which={which!r} 不在 {tuple(self._DEMOD_FILTERS)} 内，未下发")
            return False
        # 先把短写别名折算成长写，再走通用枚举校验
        text = None if value is None else str(value).strip().upper()
        resolved = self._demod_enum(
            self._DEMOD_FILTER_ALIASES.get(text, value), allowed, "filter")
        if resolved is None:
            return False
        key = self._resolve_demod_kind()
        if key is None:
            return False
        if not self._demod_write(f"SENS:{key}:{node} {resolved}"):
            return False
        # 手动截止频率：只在真的选了 MANual 时才下发，避免"设了值但没生效"
        if resolved.upper() == "MANUAL" and manual_hz is not None:
            if node == "BPF":
                print("带通滤波器无手动截止频率项，manual_hz 已忽略")
                return True
            return self._demod_write(f"SENS:{key}:{node}:MAN {manual_hz} Hz")
        return True

    @classmethod
    def _normalize_filter_alias(cls, which):
        """把 HP/HPF/HIGH 之类的写法统一成 HP/LP/BP。"""
        text = str(which).strip().upper()
        return {
            "HP": "HP", "HPF": "HP", "HIGH": "HP", "HIGHPASS": "HP",
            "LP": "LP", "LPF": "LP", "LOW": "LP", "LOWPASS": "LP",
            "BP": "BP", "BPF": "BP", "BAND": "BP", "BANDPASS": "BP",
        }.get(text, text)

    # ---------------------------------------------------------------- 采集与平均
    def set_demod_time(self, seconds=None, auto=None):
        """解调（测量）时间：`[:SENSe]:AM|FM|PM:DEMod:TIME[:AUTO]`。

        例 `:AM:DEM:TIME 50 ms` / `:AM:DEM:TIME:AUTO OFF`（手册 p256 AM / p379 FM / p494 PM）

        Auto 档按"解调波形显示两个周期"取时间；手动改会被自动解耦
        （面板上 Meas Time 前出现 `#`）。范围 1 us ~ 100 s，预设 72 ms。

        设置组合所需采集长度超过仪器容量（4 MSamples）时给出
        "Settings Alert; Acquisition truncated" 告警并**截断**——
        测量时间按请求生效了、实际采集却不够，属于必须读回+看告警的场景。
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        done = False
        if seconds is not None:
            done |= self._demod_write(f"SENS:{key}:DEM:TIME {seconds} s")
        if auto is not None:
            done |= self._demod_write(
                f"SENS:{key}:DEM:TIME:AUTO {'ON' if auto else 'OFF'}")
        if not done:
            print("set_demod_time: seconds 与 auto 都为空，未下发")
        return done

    def set_demod_periodic(self, state):
        """调制信号周期性：`[:SENSe]:AM|FM|PM:PERiodic|PERIodic[:STATe] ON|OFF|1|0`。

        手册示例：`:AM:PER OFF`（p252）/ `:FM:PERI OFF`（p366）/ `:PM:PER OFF`（p489）
        预设 ON。

        针对**周期性**调制信号时置 ON 取平均效果更好；语音、音乐或多个
        非谐波相关音这类非周期调制，手册建议置 OFF 结果更好。

        注意助记符按测量不同（AM/PM 为 `PERiodic`，FM 只有 `PERIodic`），
        本方法按测量发对应**全写**，见 `_DEMOD_PERIODIC_NODE`。
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        node = self._DEMOD_PERIODIC_NODE[key]
        return self._demod_write(
            f"SENS:{key}:{node}:STAT {'ON' if state else 'OFF'}")

    def set_demod_average(self, state=None, count=None):
        """平均开关与平均次数：`[:SENSe]:AM|FM|PM:AVERage[:STATe]|:COUNt`。

        例 `:AM:AVER:STAT ON` / `:AM:AVER:COUN 10`（手册 p238 AM / p352 FM / p476 PM）

        Average / MinHold / MaxHold 是耦合的：Average/Hold 打开时，
        RF 与 AF 频谱迹线走平均，解调波形窗同时给出瞬时/平均/最大/最小迹线。
        次数范围 1 ~ 9999，预设 10。

        Args:
            state: True/False 开关；None 表示不动
            count: 平均次数；None 表示不动
        """
        key = self._resolve_demod_kind()
        if key is None:
            return False
        done = False
        if state is not None:
            done |= self._demod_write(
                f"SENS:{key}:AVER:STAT {'ON' if state else 'OFF'}")
        if count is not None:
            done |= self._demod_write(f"SENS:{key}:AVER:COUN {count}")
        if not done:
            print("set_demod_average: state 与 count 都为空，未下发")
        return done

    # ---------------------------------------------------------------- 测量专属参数
    def set_am_genre(self, genre):
        """AM 解调类型：`[:SENSe]:AM:GENRe DSB|SSB`（手册 p240）。

        例 `:AM:GENR SSB`，预设 DSB。

        DSB = 双边带（含载波）；SSB = 抑制载波的单边带。老指令
        `[:SENSe]:AM:TYPE AMDSB|LSBSC|USBSC` 仍然可用且与新指令互相影响；
        A.25.00 起 LSB/USB 被合并成 SSB，按新写法发即可。
        """
        resolved = self._demod_enum(genre, self._DEMOD_AM_GENRE, "genre")
        if resolved is None:
            return False
        return self._demod_write(f"SENS:AM:GENR {resolved}")

    def set_fm_deemphasis(self, value):
        """FM 去加重：`[:SENSe]:FM:DEEMphasis OFF|US25|US50|US75|US750`（手册 p365）。

        例 `:FM:DEEM US75`，预设 OFF。

        去加重是调频接收端的固定时间常数网络，用于抵掉发射端的预加重。
        US75（75 µs）是美制商用 FM 的推荐值。关掉后数字滤波器被旁路。
        """
        resolved = self._demod_enum(
            value, self._DEMOD_FM_DEEMPHASIS, "fm_deemphasis")
        if resolved is None:
            return False
        return self._demod_write(f"SENS:FM:DEEM {resolved}")

    def set_speaker(self, state):
        """解调音频送扬声器：`[:SENSe]:SPEaker[:STATe] ON|OFF|1|0`（手册 p239）。

        例 `:SPE OFF`，预设 OFF。

        "tune and listen" 用；本模式下所有测量共用这一个开关，但模式之间
        不共享（手册 p239）。自动化测试里保持 OFF 即可 —— 它只影响声音，
        不影响读数。部分机型（EXM/VXT/UXM）无扬声器，该节点不存在。
        """
        return self._demod_write(f"SENS:SPE:STAT {'ON' if state else 'OFF'}")

    # ---------------------------------------------------------------- 单位
    def set_demod_unit(self, unit, kind=None, window="AFSPectrum"):
        """解调 Y 轴单位：`[:UNIT]:AM|FM|PM:AFSPectrum` / `:UNIT:PM:DEMod`。

        | 测量 | 窗口        | 允许取值                       | 预设 | 手册页 |
        |------|-------------|--------------------------------|------|--------|
        | AM   | AFSPectrum  | PERCent, DBAM                  | PERC | p167   |
        | FM   | AFSPectrum  | HZ, DBHZ                       | HZ   | p281   |
        | PM   | AFSPectrum  | RADian, DEGRee, DBRadian, DBDegree | RAD  | p403   |
        | PM   | DEMod       | RADian, DEGRee                 | RAD  | p403   |

        取简写（PERC/DBAM/HZ/DBHZ/RAD/DEGR/DBR/DBD）或手册长写都可以，
        下发时统一转成手册写法。

        改这个值会同时改 **Y 轴标注、marker 的 Y 读数与参考值标注**的显示
        （手册 p167 的 Notes）——marker 读数用哪个单位取决于它，读数前先定死。

        Args:
            unit: 上表的取值
            kind: 测量类型；None 则沿用当前测量
            window: "AFSPectrum"（默认）或 "DEMod"（仅 PM 有解调波形窗单位）

        Returns:
            bool: 是否下发成功
        """
        key = self._resolve_demod_kind(kind)
        if key is None:
            return False
        win_text = str(window).strip()
        win = "AFSPectrum" if win_text.upper().startswith("AF") else (
            "DEMod" if win_text.upper().startswith("DEM") else win_text)
        allowed = self._DEMOD_UNITS.get((key, win))
        if allowed is None:
            print(f"{key} 测量没有 {win} 窗口单位节点"
                  f"（允许: {sorted(self._DEMOD_UNITS)}），未下发")
            return False
        short = str(unit).strip().upper()
        if short not in allowed:
            print(f"参数 unit={unit!r} 对 {key}/{win} 不在允许取值 {allowed} 内，未下发")
            return False
        long_form = self._DEMOD_UNIT_ALIASES.get(short, short)
        node = "AFSP" if win == "AFSPectrum" else "DEM"
        return self._demod_write(f"UNIT:{key}:{node} {long_form}")

    # ---------------------------------------------------------------- 读回校验
    def read_demod_settings(self, kind=None):
        """读回解调测量当前的关键设置（只读，与上面的下发路径一一对应）。

        解调里有一批"仪器会自行改写另一端"或"自动解耦"的行为
        （AF Start/Stop 保 10 Hz 间隔、RBW 就近取整、MANual 只在选中时生效），
        只下发不读回，无法判断请求值是否真的落地。

        真机（N9030B / A.36.22）实测的读回格式，调用方判断"是否落地"必须知道：
        - 开关类（`...:AUTO?` / `:STAT?`）回读 **`1` / `0`**，不是 `ON` / `OFF`；
        - 单位类回读 **短写**（下 `DEGRee` 回 `DEGR`，下 `RADian` 回 `RAD`）；
        - 数值回读是科学计数法字符串（`1.000000000E+06`），带单位需自行换算。
        因此本方法对返回值统一 `strip()`：仪器回读串带尾随 `\\n`，不剥掉会让
        调用方的字符串比较与日志打印全部错位（曾在真机验收时把一行输出折成三行）。

        Returns:
            dict: 键为设置名，值为仪器原始回读字符串（已 strip）；读不到为 None。
                  AM 才有 `genre_am`，FM 才有 `fm_deemphasis`，
                  PM 才有 `pm_demod_unit`；测量类型解析失败时返回 {}。
        """
        key = self._resolve_demod_kind(kind)
        if key is None:
            return {}
        settings = {
            "measurement": self.query(":CONFigure?"),
            "mode": self.query(":INSTrument:SELect?"),
            "span_hz": self.query(f"SENS:{key}:FREQ:SPAN?"),
            "rbw_hz": self.query(f"SENS:{key}:BAND:RES?"),
            "rbw_auto": self.query(f"SENS:{key}:BAND:RES:AUTO?"),
            "channel_bw_hz": self.query(f"SENS:{key}:BAND:CHAN?"),
            "af_start_hz": self.query(f"SENS:{key}:AFSP:FREQ:STAR?"),
            "af_stop_hz": self.query(f"SENS:{key}:AFSP:FREQ:STOP?"),
            "af_bw_hz": self.query(f"SENS:{key}:AFSP:BAND?"),
            "af_bw_auto": self.query(f"SENS:{key}:AFSP:BAND:AUTO?"),
            "hpf": self.query(f"SENS:{key}:HPF?"),
            "lpf": self.query(f"SENS:{key}:LPF?"),
            "bpf": self.query(f"SENS:{key}:BPF?"),
            "demod_time_s": self.query(f"SENS:{key}:DEM:TIME?"),
            "demod_time_auto": self.query(f"SENS:{key}:DEM:TIME:AUTO?"),
            # 周期性节点按测量分树，不能写死 `PER`：FM 是 `PERIodic`（短写 PERI），
            # 发 `SENS:FM:PER:STAT?` 会得 -113 Undefined header 且读回静默为 None。
            "periodic": self.query(
                f"SENS:{key}:{self._DEMOD_PERIODIC_NODE[key]}:STAT?"),
            "average": self.query(f"SENS:{key}:AVER:STAT?"),
            "average_count": self.query(f"SENS:{key}:AVER:COUN?"),
            "speaker": self.query("SENS:SPE:STAT?"),
            "af_unit": self.query(f"UNIT:{key}:AFSP?"),
        }
        if key == "AM":
            settings["genre_am"] = self.query("SENS:AM:GENR?")
        if key == "FM":
            settings["fm_deemphasis"] = self.query("SENS:FM:DEEM?")
        if key == "PM":
            settings["pm_demod_unit"] = self.query("UNIT:PM:DEM?")
        return {k: (None if v is None else str(v).strip())
                for k, v in settings.items()}

    # ---------------------------------------------------------------- 结果读取
    #: `:FETC:<测量>?`（n 缺省或 1）返回的逗号分隔结果表 —— 手册「n / Return Value」表。
    #: 键 = (测量, AM Type 或 None)；值 = 按手册顺序排列的字段名。
    #:
    #: ⚠ AM 有**两个长度不同的变体**，由 `:SENSe:AM:GENRe`（DSB | SSB，手册 p240）决定：
    #:   DSB 18 项：#8~#11 = 调制深度 Peak+ / Peak- / (Pk-Pk)/2 / RMS，单位 %
    #:   SSB 17 项：#8~#11 = 解调波形幅度，单位 V；#3 恒为 0（占位）
    #: 同一索引含义完全不同 —— 不先读 `:SENS:AM:GENR?` 选表，就会把电压当成深度百分比。
    #: FM / PM 各 16 项。
    #: ⚠ PM 的偏移单位**不是**固定 rad：`[:UNIT]:PM:DEMod` 会连带把 `:FETC:PM?`
    #:   里 8 个角度量一起换单位。手册 p403 Notes 把它描述成 "changing the units of
    #:   the Y-axis annotation, marker Y, and reference value"，容易读成"只影响显示"，
    #:   但**真机实测**（N9030B / MY60089385 / A.36.22，2026-09-16）证明：
    #:     UNIT:PM:DEMod RAD → 第 8 项 0.167111437
    #:     UNIT:PM:DEMod DEGR → 第 8 项 9.582051469      比值 57.339291918 = 180/π
    #:   即面板/远程读到的是"度"时，通路上拿到的也是"度"。故本表字段以 `_rad` 结尾，
    #:   而 `read_demod_metrics()` 负责按当前单位换算回 rad（见 `_pm_angle_unit_factor`）。
    #:   曾按"单位只影响显示"实现过一版，会让调用方静默读到放大 57.3 倍的错值。
    _DEMOD_RESULT_FIELDS = {
        ("AM", "DSB"): (
            "rf_center_hz", "carrier_power_dbm", "carrier_freq_error_hz",
            "mod_rate_hz", "sinad_db", "distortion_pct", "thd_pct",
            "depth_peak_plus_pct", "depth_peak_minus_pct",
            "depth_half_pkpk_pct", "depth_rms_pct",
            "depth_peak_plus_maxhold_pct", "depth_peak_minus_maxhold_pct",
            "depth_half_pkpk_maxhold_pct", "depth_rms_maxhold_pct",
            "snr_db", "rms_power_dbm", "pep_dbm",
        ),
        ("AM", "SSB"): (
            "rf_center_hz", "rms_power_dbm", "reserved_zero",
            "mod_rate_hz", "sinad_db", "distortion_pct", "thd_pct",
            "wave_amp_peak_plus_v", "wave_amp_peak_minus_v",
            "wave_amp_half_pkpk_v", "wave_amp_rms_v",
            "wave_amp_peak_plus_maxhold_v", "wave_amp_peak_minus_maxhold_v",
            "wave_amp_half_pkpk_maxhold_v", "wave_amp_rms_maxhold_v",
            "snr_db", "pep_dbm",
        ),
        ("FM", None): (
            "rf_center_hz", "carrier_power_dbm", "carrier_freq_error_hz",
            "mod_rate_hz", "sinad_db", "distortion_pct", "thd_pct",
            "deviation_peak_plus_hz", "deviation_peak_minus_hz",
            "deviation_half_pkpk_hz", "deviation_rms_hz",
            "deviation_peak_plus_maxhold_hz", "deviation_peak_minus_maxhold_hz",
            "deviation_half_pkpk_maxhold_hz", "deviation_rms_maxhold_hz",
            "snr_db",
        ),
        ("PM", None): (
            "rf_center_hz", "carrier_power_dbm", "carrier_freq_error_hz",
            "mod_rate_hz", "sinad_db", "distortion_pct", "thd_pct",
            "deviation_peak_plus_rad", "deviation_peak_minus_rad",
            "deviation_half_pkpk_rad", "deviation_rms_rad",
            "deviation_peak_plus_maxhold_rad", "deviation_peak_minus_maxhold_rad",
            "deviation_half_pkpk_maxhold_rad", "deviation_rms_maxhold_rad",
            "snr_db",
        ),
    }

    #: 正负峰值不平衡：取哪两个字段相减、结果叫什么。
    #: 物理含义 = 正峰与负峰**幅度**之差，故两端都取 abs()：Peak- 在仪表里
    #: 可能以负值或幅度值出现，取 abs 后两种约定都得到同一个"不对称量"。
    _DEMOD_IMBALANCE = {
        ("AM", "DSB"): ("depth_peak_plus_pct", "depth_peak_minus_pct",
                        "depth_imbalance_pct"),
        ("AM", "SSB"): ("wave_amp_peak_plus_v", "wave_amp_peak_minus_v",
                        "wave_amp_imbalance_v"),
        ("FM", None): ("deviation_peak_plus_hz", "deviation_peak_minus_hz",
                       "deviation_imbalance_hz"),
        ("PM", None): ("deviation_peak_plus_rad", "deviation_peak_minus_rad",
                       "deviation_imbalance_rad"),
    }

    def _demod_result_variant(self, key):
        """选 AM 的结果表变体（DSB/SSB）；FM/PM 无变体，返回 None。

        问仪器而不是用 `self._demod_kind`：AM Type 可以被别的程序或面板改掉，
        缓存值是"我以为的状态"，仪器回读才是真相。
        """
        if key != "AM":
            return None
        genre = self.query("SENS:AM:GENR?")
        text = str(genre).strip().upper() if genre is not None else ""
        if text.startswith("DSB"):
            return "DSB"
        if text.startswith("SSB"):
            return "SSB"
        print(f"警告: :SENS:AM:GENR? 回读 {genre!r}，无法确定 AM 结果表变体（DSB/SSB）")
        return None

    #: PM 角度量（`_rad` 结尾的字段，含 MaxHold 组）的当前单位 -> rad 换算因子。
    #: 仪器 `:UNIT:PM:DEMod` 会连带换 `:FETC:PM?` 的角度量单位（真机证实，见类头注释）。
    #: 键取回读字符串的前缀，兼容 `RAD` / `RADian`、`DEG` / `DEGRee` 各种回读形态。
    _PM_ANGLE_UNIT_TO_RAD = {"RAD": 1.0, "DEG": math.pi / 180.0}

    def _pm_angle_unit_factor(self):
        """读 PM 角度量的当前单位，返回 `(因子, 回读文本)`；无法确定时因子为 None。

        问仪器而不是假定：`UNIT:PM:DEMod` 可被面板或别的程序改掉，且**真的会**改
        `:FETC:PM?` 的数值（不是只改标注）。拿不到单位就**拒绝换算**而不是默认 rad
        —— 默认 rad 在单位是度时错 57.3 倍，且没有任何迹象，属于本项目最忌讳的
        "不报错但结果错"。
        """
        raw = self.query("UNIT:PM:DEM?")
        text = str(raw).strip().upper() if raw is not None else ""
        for prefix, factor in self._PM_ANGLE_UNIT_TO_RAD.items():
            if text.startswith(prefix):
                return factor, text
        print(f"警告: :UNIT:PM:DEM? 回读 {raw!r}，无法确定 PM 角度单位，拒绝换算")
        return None, text

    def read_demod_metrics(self, kind=None, acquire=True):
        """读取解调**测量结果**（调制深度 / 频偏 / 相偏 / 调制速率 / 正负峰不平衡）。

        与 `read_demod_settings()` 的分工：那个读**设置**（确认下发是否被仪器接受），
        这个读**结果**（量化数据）。两者都只读，不改仪器状态。

        采集序列（手册 p256-258 Sweep/Measure、p613 Restart）：
            `:INIT:CONT OFF` → `:INIT:IMM` → `*OPC?` → `:FETC:<测量>?`

        ⚠ 为什么 `:INIT:IMM` 不能省：手册 p258 明说 "If the instrument is already
        in Single sweep, `:INIT:CONT OFF` has no effect"，而 "sending `:INIT:IMM`
        does reset it"。只发 `CONT OFF` 会读到**上一轮残留结果**——与 SA 模式那个
        "`INIT:CONT OFF` 后从不发 `INIT:IMM`" 的哨兵值缺陷同源（本项目已修过一次）。
        `:INIT:IMM` 是 overlapped 命令（手册 p258），所以必须用 `*OPC?` 等它跑完；
        单次模式下若开着平均，它会跑满 Average/Hold Num 次再停。

        Args:
            kind: "AM" / "FM" / "PM"；None 则沿用当前测量
            acquire: True（默认）先做一次确定性采集；
                     False 只 FETCh 当前结果（"一次采集多次取数"，或已自行
                     `acquire_once()` 过）

        Returns:
            dict: 手册表内字段名 -> float；解析不出为 None。另含：
                  `variant`（AM 的 DSB/SSB）、`count`/`expected_count`、
                  `raw`（仪器原始字符串列表，便于事后核对）；
                  以及正负峰不平衡 `depth_imbalance_pct` /
                  `wave_amp_imbalance_v` / `deviation_imbalance_hz|_rad`。
                  PM 另含 `pm_unit_readback`（仪器当前角度单位），若仪器单位是"度"
                  则额外有 `pm_unit_converted_from`，且全部 `_rad` 字段已换算成 rad。
                  任何一步失败都返回带 `error` 键的 dict，**不抛异常**，
                  以免一条读数把整个测试流程打断。

        单位说明（PM）：本方法**只读**，不写仪器状态。仪器 `:UNIT:PM:DEMod` 若为
            "度"，`:FETC:PM?` 的角度量就是度，此处按 π/180 换算回 rad，使 `_rad`
            字段含义恒定。若单位读不到，**不猜测**，返回 `error`。
        """
        key = self._resolve_demod_kind(kind)
        if key is None:
            return {"error": "无法确定解调测量类型（先 select_demod_measurement）"}

        variant = self._demod_result_variant(key)
        if key == "AM" and variant is None:
            return {"error": "AM 结果表变体未知（:SENS:AM:GENR? 非 DSB/SSB），拒绝解析"}

        if acquire and not self.acquire_once():
            return {"error": "采集失败：acquire_once() 返回 False"}

        raw_text = self.query(f"FETC:{key}?")
        if raw_text is None:
            return {"error": f":FETC:{key}? 查询失败"}

        parts = [p.strip() for p in str(raw_text).split(",")]
        fields = self._DEMOD_RESULT_FIELDS[(key, variant)]
        result = {"variant": variant, "count": len(parts),
                  "expected_count": len(fields), "raw": parts}

        if len(parts) != len(fields):
            # 长度不符 = 手册表与固件实际不一致。**不猜索引**，只把原始值交出去，
            # 否则错位的字段会被当成真实读数写进结果（本项目最忌讳的一类错）。
            result["error"] = (f":FETC:{key}? 返回 {len(parts)} 项，"
                               f"手册表为 {len(fields)} 项（{key}/{variant}）；"
                               f"字段未解析，请核对固件手册")
            return result

        for name, text in zip(fields, parts):
            result[name] = self._sanitize_raw(text)

        # PM 角度量单位归一化：字段名以 `_rad` 结尾就必须真的是 rad。仪器会把
        # `:FETC:PM?` 的角度量随 `:UNIT:PM:DEMod` 一起换单位（真机证实），故这里
        # 读一次单位再换算 —— 读到"度"就 ×π/180，读不到单位则**拒绝**给出 `_rad`
        # 字段（宁可报错，也不让调用方拿到静默放大 57.3 倍的错值）。
        # 放在算不平衡之前，`deviation_imbalance_rad` 才会跟着是 rad。
        if key == "PM":
            factor, unit_text = self._pm_angle_unit_factor()
            if factor is None:
                # 单位未知 -> 这批角度量"是度还是 rad"无从判断，两个标签都不成立。
                # 必须把已解析出的 `_rad` 字段**剔除**：留着就是"名字说 rad、值是度"
                # 的静默错值，调用方一个 `continue` 就把它写进结果了。
                for name in [n for n in fields if n.endswith("_rad")]:
                    result.pop(name, None)
                result["error"] = (f"PM 角度量单位未知（:UNIT:PM:DEM? = {unit_text!r}）；"
                                   f"无法保证 *_rad 字段含义，已剔除角度字段，"
                                   f"请核对仪器单位后重测")
                return result
            result["pm_unit_readback"] = unit_text
            if factor != 1.0:
                result["pm_unit_converted_from"] = unit_text
                for name in fields:
                    if name.endswith("_rad") and result.get(name) is not None:
                        result[name] = result[name] * factor

        plus, minus, imbalance_key = self._DEMOD_IMBALANCE[(key, variant)]
        p, m = result.get(plus), result.get(minus)
        result[imbalance_key] = (None if p is None or m is None
                                 else abs(p) - abs(m))
        return result
