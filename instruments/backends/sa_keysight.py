# -*- coding: utf-8 -*-
"""是德 Keysight 频谱仪后端（X 系列 SA：N9000B/N9010B/N9020B/N9030B 等）。

指令来源：X-Series Signal Analyzers
          Spectrum Analyzer Mode User's & Programmer's Reference
          Manual Part Number N9060-90041, Edition 19 (2025-12)

均取 Swept SA 测量下的指令；手册页面引用为文档页脚页码。
"""
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

        例：`:POW:ATT 20`（手册 p.226）
        注意：手动下发会自动把衰减从参考电平解耦。
        """
        try:
            self.instrument.write(f"POW:ATT {attenuation}")
        except Exception as e:
            print(f"设置衰减失败: {e}")

    def set_attenuation_auto(self, state=True):
        """衰减自动耦合：`[:SENSe]:POWer[:RF]:ATTenuation:AUTO OFF|ON|0|1`。

        例：`:POW:ATT:AUTO ON`（手册 p.227）
        """
        try:
            self.instrument.write(f"POW:ATT:AUTO {'ON' if state else 'OFF'}")
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
                    self.instrument.write(f"POW:GAIN:BAND {resolved_band}")
                self.instrument.write("POW:GAIN:STAT ON")
            else:
                self.instrument.write("POW:GAIN:STAT OFF")
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
        """
        try:
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
            "input_att_db": self._query_float("POW:ATT?"),
        }
