# -*- coding: utf-8 -*-
"""罗德 R&S 频谱仪后端（FSWP / FSW）。

指令来源：R&S FSWP-B1 User Manual, 1177.5656.02 ─ 11
- 频率/扫宽：6.8.2 (p.714)
- 幅度/衰减/预放：6.8.3 (p.721)
- 滤波器 RBW/VBW：6.8.5 (p.727)
- 迹线/检波器：6.9.2.2 (p.758)
- 标记点：6.9.3 (p.779)
"""
from backends.sa_base import SpectrumAnalyzerBackend


class RohdeSpectrumAnalyzer(SpectrumAnalyzerBackend):
    """R&S FSWP/FSW 后端。"""

    BRAND = "rohde"

    # ---------------------------------------------------------------- 幅度
    def set_reference_level(self, level):
        """参考电平：`DISPlay[:WINDow<n>][:SUBWindow<w>]:TRACe<t>:Y[:SCALe]:RLEVel`。

        例：`DISP:TRAC:Y:RLEV -60dBm`（手册 p.722）
        """
        try:
            self.instrument.write(f"DISP:TRAC:Y:RLEV {level}")
        except Exception as e:
            print(f"设置参考电平失败: {e}")

    def set_attenuation(self, attenuation):
        """输入衰减：`INPut:ATTenuation <Attenuation>`，例 `INP:ATT 10dB`（手册 p.723）。"""
        try:
            self.instrument.write(f"INP:ATT {attenuation}")
        except Exception as e:
            print(f"设置衰减失败: {e}")

    def set_attenuation_auto(self, state=True):
        """衰减自动耦合：`INPut:ATTenuation:AUTO OFF|ON|0|1`（手册 p.724）。"""
        try:
            self.instrument.write(f"INP:ATT:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置自动衰减失败: {e}")

    def set_preamp(self, state=True, band=None):
        """内置预放：`INPut:GAIN:STATe` + `INPut:GAIN[:VALue]`（手册 p.724）。

        FSWP 预放以增益值(dB)配置，而非波段：
        - K08/K09/K27/K51 支持 15 dB / 30 dB
        - K26/K50 仅 30 dB

        Args:
            state: True 开预放，False 关
            band: 兼容写法 "LOW"→15 dB、"FULL"→30 dB；也可直接传整数 dB
        """
        try:
            if state:
                gain = self._resolve_preamp_gain(band)
                if gain is not None:
                    self.instrument.write(f"INP:GAIN:VAL {gain}")
                self.instrument.write("INP:GAIN:STAT ON")
            else:
                self.instrument.write("INP:GAIN:STAT OFF")
        except Exception as e:
            print(f"设置预放失败: {e}")

    @staticmethod
    def _resolve_preamp_gain(band):
        """把兼容参数解析为 FSWP 预放增益值(dB)。"""
        if band is None:
            return None
        if isinstance(band, (int, float)):
            return int(band)
        mapping = {"LOW": 15, "FULL": 30}
        key = str(band).upper().strip()
        if key in mapping:
            return mapping[key]
        try:
            return int(key)
        except ValueError:
            return None

    # ---------------------------------------------------------------- 标记点
    def peak_search(self, marker_num=1):
        """峰值搜索：`CALCulate<n>:MARKer<m>:MAXimum[:PEAK]`（手册 p.797）。

        例：`CALC:MARK1:MAX:PEAK`
        """
        try:
            self.instrument.write(f"CALC:MARK{marker_num}:MAX:PEAK")
            print("执行峰值搜索")
        except Exception as e:
            print(f"峰值搜索失败: {e}")

    def measure_power(self, marker_num=1):
        """峰值搜索后读取标记点功率 (`CALC:MARK<m>:Y?`)。"""
        try:
            self.peak_search(marker_num)
            return float(self.instrument.query(self.CMD_MARKER_YQ.format(m=marker_num)))
        except Exception as e:
            print(f"测量功率失败: {e}")
            return None

    # ---------------------------------------------------------------- 带宽
    def set_rbw_auto(self, state=True):
        """RBW 自动耦合：`BANDwidth[:RESolution]:AUTO ON|OFF`（手册 p.728）。"""
        try:
            self.instrument.write(f"BAND:RES:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置RBW自动失败: {e}")

    def set_vbw_auto(self, state=True):
        """VBW 自动耦合：`BANDwidth:VIDeo:AUTO ON|OFF`（手册 p.729）。"""
        try:
            self.instrument.write(f"BAND:VID:AUTO {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"设置VBW自动失败: {e}")

    # ---------------------------------------------------------------- 迹线/检波器
    # 手册 p.760：DISPlay[:WINDow<n>][:SUBWindow<w>]:TRACe<t>:MODE
    _TRACE_MODE_MAP = {
        "WRITE": "WRITe", "WRIT": "WRITe", "WRITe": "WRITe",
        "MAXH": "MAXHold", "MAXHold": "MAXHold",
        "MINH": "MINHold", "MINHold": "MINHold",
        "VIEW": "VIEW",
        "BLANK": "BLANk", "BLANk": "BLANk",
        "AVERAGE": "AVERage", "AVER": "AVERage", "AVERage": "AVERage",
    }

    # 手册 p.759：[SENSe:][WINDow<n>:]DETector<t>[:FUNCtion]
    #   APEak | NEGative | POSitive | QPEak | SAMPle | RMS | AVERage
    _DETECTOR_MAP = {
        "APEAK": "APEak", "APE": "APEak", "APEak": "APEak", "AUTOPEAK": "APEak",
        "NEG": "NEGative", "NEGative": "NEGative",
        "POS": "POSitive", "POSitive": "POSitive",
        "QPEAK": "QPEak", "QPE": "QPEak", "QPEak": "QPEak",
        "SAMP": "SAMPle", "SAMPLE": "SAMPle", "SAMPle": "SAMPle",
        "RMS": "RMS",
        "AVERAGE": "AVERage", "AVER": "AVERage", "AVERage": "AVERage",
    }

    def set_trace_mode(self, mode="MAXHold", trace=1):
        """迹线模式：`DISPlay[:WINDow]:TRACe<t>:MODE WRITe|MAXHold|MINHold|VIEW|BLANk`。

        Args:
            mode: 兼容简写 MAXH/WRITE/AVERAGE/MINH/VIEW/BLANK
            trace: trace 编号，默认 1
        """
        try:
            fswp_mode = self._TRACE_MODE_MAP.get(str(mode).upper(), mode)
            self.instrument.write(f"DISP:TRAC{trace}:MODE {fswp_mode}")
        except Exception as e:
            print(f"设置trace模式失败: {e}")

    def set_detector(self, detector="POSitive", trace=1):
        """检波器：`[SENSe:]DETector<t>:FUNCtion`，例 `DET POS`（手册 p.759）。

        Args:
            detector: 兼容简写 POS/NEG/APE/RMS/SAMP/AVERAGE
            trace: trace 编号，默认 1
        """
        try:
            fswp_detector = self._DETECTOR_MAP.get(str(detector).upper(), detector)
            self.instrument.write(f"SENS:DET{trace}:FUNC {fswp_detector}")
        except Exception as e:
            print(f"设置检波器失败: {e}")

    # ---------------------------------------------------------------- 读回校验
    def _read_extra_settings(self):
        """读回参考电平与输入衰减（与上面的下发路径一一对应）。"""
        return {
            "ref_level_dbm": self._query_float("DISP:TRAC:Y:RLEV?"),
            "input_att_db": self._query_float("INP:ATT?"),
        }
