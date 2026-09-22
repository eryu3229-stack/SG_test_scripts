# -*- coding: utf-8 -*-
"""信号源控制类

指令依据：R&S SMB100B 用户手册 (1178.3711.02 ─ 11)
    - SOURce:MODulation（一键关全部调制）................. 手册 p442
    - SOURce:LFOutput（内部调制源 LF1/LF2）................ p496-501
    - SOURce:AM   子系统（幅度调制）....................... p443-446
    - SOURce:FM   子系统（频率调制）....................... p448-450
    - SOURce:PM   子系统（相位调制）....................... p453-457
    - SOURce:PULM 子系统（脉冲调制）....................... p458-462
    - UNIT 子系统（改默认单位会改变指令含义）.............. p596

范围口径（用户 2026-09-18 明确要求"不要考虑比较复杂的设置"、"目前不需要 1 2 通道的设置"）：
    只保留**单通道（固定 1 号）、单值、内部源**的基础设置 —— 每种调制一个开关、
    一个源、一个主参数（深度/偏差/周期宽度）。**调制方法一律不设 channel 参数**，
    节点号写死 `LFO1` / `AM1` / `FM1` / `PM1`（脉冲调制 `PULM` 本身无通道号），
    与 `_MOD_STATE_QUERIES` 的写法保持一致。以下一律不做：
      · 通道选择（`AM/FM/PM<ch>`、`LFOutput<ch>` 的 2 号通道）与 channel 参数
      · 双通道组合（`AM/FM/PM:DEViation:MODE`、`DEPTh:SUM`、`RATio`）
      · 外部调制灵敏度（`AM/FM/PM:SENSitivity`）与外部调制输入（`INPut:MODext`）
      · 调制模式（`FM:MODE`、`PM:MODE`）—— 且实测 B 机特性，现场 A 机不认
      · 脉冲的双脉冲/脉冲串/触发模式/单次触发/延迟/极性/阻抗/跳变类型/同步输出
      · 脉冲发生器（`PGENerator`）与脉冲串文件（`TRAin:*`）
    需要其中任何一项时按手册页码单独补，不要顺手加回来。

单位书写约定（逐个说明理由，勿凭感觉改）：
    1) PM 偏差**必须**带 RAD 后缀。`UNIT:ANGLe`（p596）可把角度默认单位改成 DEG，
       裸数值 `PM:DEV 1` 届时是 1 度而非 1 rad，**静默**差 57.3 倍 → 相位调制校准
       会被整体带偏，而仪器不报错。
    2) 功率**带 DBM**。`UNIT:POWer`（p596）可切成 V/dBuV，裸数值含义随全局设置漂移。
    3) 脉冲时间**带 s**。手册在这些参数的页面上未印 `Default unit`（对比
       `LFOutput:PERiod` p498 就印了 `Default unit: s`）；加上后缀即与手册示例
       （`:SOURce:PULM:PERiod 10 us`）一致，也不依赖隐含默认值。
    4) 深度/比例/频率等无全局单位可改（`UNIT` 只管角度与功率），按手册示例发裸值。
    5) 关键字只写**短写**（手册里的大写字母）或**全写**，不得截到中间：
       `DEPTh` 的合法写法只有 `DEPT`（短写）或 `DEPTH`（全写），写 `DEPH` / `DEP` 都不合法。
       本文件统一取短写，**唯一例外是调幅深度**：手册通篇只写 `DEPTh`（示例全是长写），
       没出现过一次短写，故选**长写 `DEPTH`**——照有直接证据的写法走，不靠规则推。

真机实测备注（2026-09-18，只读查询，未改任何仪器状态）：
    现场连的是 **R&S SMB100A**（1406.6000k03/183880，固件 5.00.116.88，
    选件 SMB-B32 / SMB-B140N / SMB-K21 / SMB-K23），**不是**本文件依据的 SMB100B。
    本文件保留的节点在 A 机上**逐个查询全部通过、错误队列干净**
    （AM/FM/PM/PULM/LFOutput/MOD:ALL，另 `UNIT:ANGL?=RAD`、`UNIT:POW?=DBM`）。
    A 机 `K720`（AM/FM/PhiM 选件）不在 `*OPT?` 列表里，但调制节点照常可用
    → 模拟调制在 A 机上属基本配置。
"""


class SignalGenerator:
    """信号源控制类（SMB100B 手册指令集，现场机型 SMB100A，见模块头）"""

    #: RF 输出路径编号。手册写作 SOURce<hw>，单路径机型固定 1。
    PATH = 1
    #: 是否在前面加 `SOUR<n>:` 前缀。
    #: 用户现场信号源不接受 `SOUR1:`，故默认 False；命令直接用 `AM1:` / `LFO1:` / `SOUR:MOD:ALL:STAT`。
    USE_PATH = False

    #: 调制信号源 <Source>（AM/FM/PM 同用，手册 p445/p450/p455）
    MOD_SOURCES = ("LF1", "LF2", "EXT1", "NOISE", "INTERNAL", "EXTERNAL")
    #: 内部 LF 波形（手册 p501）
    LF_SHAPES = ("SINE", "SQUARE", "PULSE", "TRIANGLE", "TRAPEZE")
    #: 脉冲调制源（手册 p461）
    PULM_SOURCES = ("INTERNAL", "EXTERNAL")
    #: AM 类型（手册 p443/444）
    AM_TYPES = ("LIN", "EXP", "LINEAR", "EXPONENTIAL")

    #: 调制种类 -> 开关状态回读指令（手册 p445/p450/p454/p461）
    _MOD_STATE_QUERIES = {
        "AM": "AM1:STAT?",
        "FM": "FM1:STAT?",
        "PM": "PM1:STAT?",
        "PULM": "PULM:STAT?",
    }

    def __init__(self, instrument):
        """初始化信号源

        Args:
            instrument: pyvisa仪器对象
        """
        self.instrument = instrument

    # ==================== 私有工具 ====================

    def _write(self, command, description=None):
        """下发一条 SCPI 指令

        Args:
            command: 完整 SCPI 指令
            description: 中文说明，仅用于打印

        Returns:
            bool: 下发是否成功
        """
        try:
            self.instrument.write(command)
            if description:
                print(f"{description}  [{command}]")
            return True
        except Exception as e:
            print(f"指令下发失败: {command} -> {e}")
            return False

    def _query(self, command, description=None):
        """查询一条 SCPI 指令

        Returns:
            str | None: 仪器回读字符串（已 strip），失败为 None
        """
        try:
            value = self.instrument.query(command)
            value = value.strip() if isinstance(value, str) else value
            if description:
                print(f"{description}: {value}  [{command}]")
            return value
        except Exception as e:
            print(f"指令查询失败: {command} -> {e}")
            return None

    @classmethod
    def _enum(cls, value, allowed, name):
        """校验枚举参数

        越界时打印告警并返回 None（调用方据此**不下发**）——
        仪器对非法枚举多会报错或自行取整，两种都不该让它悄悄发生。

        Args:
            value: 用户传入值
            allowed: 允许的取值元组（大写短写形式）
            name: 参数名，用于打印

        Returns:
            str | None: 规范化为大写的取值
        """
        if value is None:
            print(f"参数 {name} 为空，未下发")
            return None
        text = str(value).strip().upper()
        if text not in allowed:
            print(f"参数 {name}={value!r} 不在允许取值 {allowed} 内，未下发")
            return None
        return text

    def _onoff(self, enable):
        """布尔转 SCPI 的 1/0"""
        return "1" if enable else "0"

    def _source_prefix(self):
        """AM/FM/PM/LF/PULM 等子系统的前缀。

        用户现场仪器不接受 `SOUR1:`，故默认空；保留 `USE_PATH=True` 可恢复
        `SOUR1:AM1:` 写法。
        """
        return f"SOUR{self.PATH}:" if self.USE_PATH else ""

    def _mod_all_prefix(self):
        """`SOUR:MOD:ALL:STAT` 的前缀。

        无路径号时仍需要 `SOUR:`；有路径号时为 `SOUR1:`。
        """
        return f"SOUR{self.PATH}:" if self.USE_PATH else "SOUR:"

    # ==================== 基础指令（原有） ====================

    def set_frequency(self, frequency):
        """设置信号源频率

        Args:
            frequency: 频率值，单位Hz

        Returns:
            bool: 是否成功
        """
        return self._write(f"FREQ {frequency}", f"设置信号源频率为: {frequency} Hz")

    def set_power(self, power):
        """设置信号源功率

        显式带 `DBM`：`UNIT:POWer`（手册 p596）可以把功率默认单位改成 V / dBuV，
        此时裸数值会被按伏特解释。默认设置下与不带单位完全等价。

        Args:
            power: 功率值，单位dBm

        Returns:
            bool: 是否成功
        """
        return self._write(f"POW {power}", f"设置信号源功率为: {power} dBm")

    def enable_output(self, enable=True):
        """启用或禁用信号源输出

        Args:
            enable: True为启用，False为禁用

        Returns:
            bool: 是否成功
        """
        state = self._onoff(enable)
        text = "启用信号源输出" if enable else "禁用信号源输出"
        return self._write(f"OUTP:STATe {state}", text)

    def get_idn(self):
        """获取仪器ID信息"""
        return self._query("*IDN?")

    # ==================== 通用调制开关 ====================

    def set_all_modulation(self, enable):
        """一次性关闭 / 恢复全部调制（手册 p442）

        `[:SOURce<hw>]:MODulation[:ALL][:STATe]`。
        置 0 关掉当前所有激活的调制；再置 1 恢复**上次置 0 之前**那些调制，
        不是"全开"。切换载波 / 改频点前想清干净状态就用它。

        Args:
            enable: True 恢复、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "恢复上次的调制" if enable else "关闭全部调制"
        return self._write(f"{self._mod_all_prefix()}MOD:ALL:STAT {self._onoff(enable)}", text)

    def get_modulation_state(self, kinds=None, verbose=False):
        """回读调制开关状态（手册 p445/450/454/461）

        下发后回读是唯一能发现"设置被仪器静默拒绝"的手段。

        Args:
            kinds: 要回读的种类，如 ``("AM",)``。
                **调用方应按需传** —— 查询本身也是一次仪器交互：测 AM 时
                没有任何理由去问 PM，而且无关节点一旦返回哨兵值，
                那一行就会直接出现在终端里、与本次测量毫无关系。
                ``None`` = 四种全查（只在确有全局意图时用）。
            verbose: 是否逐条打印（默认关闭）。由调用方决定要不要显示，
                避免"每设一次调制就刷四行状态"。

        Returns:
            dict: ``{'AM': str|None, ...}``，**只含 `kinds` 点名的种类**。
        """
        wanted = tuple(self._MOD_STATE_QUERIES) if kinds is None else tuple(kinds)
        state = {}
        for kind in wanted:
            key = str(kind).strip().upper()
            query = self._MOD_STATE_QUERIES.get(key)
            if query is None:
                raise ValueError(
                    f"未知调制种类 {kind!r}，可选 {tuple(self._MOD_STATE_QUERIES)}")
            state[key] = self._query(f"{self._source_prefix()}{query}",
                                     f"{key} 状态" if verbose else None)
        return state

    # ==================== 内部调制源 LF1（固定 1 号，无通道参数） ====================

    def set_lf_shape(self, shape):
        """设置内部 LF 调制源波形（手册 p501）

        Args:
            shape: SINE / SQUare / PULSe / TRIangle / TRAPeze

        Returns:
            bool: 是否成功
        """
        value = self._enum(shape, self.LF_SHAPES, "lf_shape")
        if value is None:
            return False
        return self._write(f"{self._source_prefix()}LFO1:SHAP {value}",
                           f"LF1 波形: {value}")

    def set_lf_frequency(self, frequency):
        """设置内部 LF 调制源的频率（手册 p497）

        内部源做 AM/FM/PhiM/PM 时，**调制频率就是这个值**。

        Args:
            frequency: 频率，单位 Hz（*RST 默认 1000）

        Returns:
            bool: 是否成功
        """
        return self._write(f"{self._source_prefix()}LFO1:FREQ {frequency}",
                           f"LF1 调制频率: {frequency} Hz")

    def enable_lf_output(self, enable=True):
        """开启 / 关闭 LF 输出（手册 p499）

        手册的 FM / PM 示例都在使能调制前发这条（AM 示例未发）。

        Args:
            enable: True 开启、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "开启 LF1 输出" if enable else "关闭 LF1 输出"
        return self._write(f"{self._source_prefix()}LFO1:STAT {self._onoff(enable)}", text)

    # ==================== 幅度调制 AM（手册 p443-446） ====================

    def enable_am(self, enable=True):
        """开启 / 关闭幅度调制（手册 p445）

        选件：R&S SMBB-K720

        Args:
            enable: True 开启、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "开启 AM1（幅度调制）" if enable else "关闭 AM1"
        return self._write(f"{self._source_prefix()}AM1:STAT {self._onoff(enable)}", text)

    def set_am_source(self, source):
        """选择幅度调制的信号源（手册 p446）

        Args:
            source: LF1|LF2 内部 LF；EXT1|EXTernal 外部输入；
                    NOISe 内部噪声；INTernal = LF1

        Returns:
            bool: 是否成功
        """
        value = self._enum(source, self.MOD_SOURCES, "am_source")
        if value is None:
            return False
        return self._write(f"{self._source_prefix()}AM1:SOUR {value}",
                           f"AM1 调制源: {value}")

    def set_am_depth(self, depth):
        """设置调幅深度，单位 %（手册 p446）

        Args:
            depth: 0 ~ 100（%）

        Returns:
            bool: 是否成功
        """
        if depth is None or not (0 <= depth <= 100):
            print(f"参数 am_depth={depth} 超出范围 [0, 100] %，未下发")
            return False
        return self._write(f"{self._source_prefix()}AM1:DEPTH {depth}",
                           f"AM1 调幅深度: {depth} %")

    def set_am_type(self, am_type):
        """设置 AM 类型为线性 / 指数（手册 p443/444）

        用户参考流程固定发 `AM:TYPE LIN`，故提供显式接口，不再依赖默认值。

        Args:
            am_type: LIN|LINEAR / EXP|EXPONENTIAL

        Returns:
            bool: 是否成功
        """
        value = self._enum(am_type, self.AM_TYPES, "am_type")
        if value is None:
            return False
        # 下发用短写（与 SMB100B 示例一致）
        scpi_value = "LIN" if value in ("LIN", "LINEAR") else "EXP"
        return self._write(f"{self._source_prefix()}AM:TYPE {scpi_value}",
                           f"AM 类型: {scpi_value}")

    def set_am_depth_lin(self, depth):
        """以线性方式设置调幅深度，单位 %（手册 p446）

        对应用户参考流程中的 `AM1:DEPT:LIN 30`。

        Args:
            depth: 0 ~ 100（%）

        Returns:
            bool: 是否成功
        """
        if depth is None or not (0 <= depth <= 100):
            print(f"参数 am_depth_lin={depth} 超出范围 [0, 100] %，未下发")
            return False
        return self._write(f"{self._source_prefix()}AM1:DEPT:LIN {depth}",
                           f"AM1 线性调幅深度: {depth} %")

    def get_am_type(self):
        """回读 AM 类型（`AM:TYPE?`）"""
        return self._query(f"{self._source_prefix()}AM:TYPE?", "AM 类型回读")

    def get_am_depth_lin(self):
        """回读线性调幅深度（`AM1:DEPT:LIN?`）"""
        return self._query(f"{self._source_prefix()}AM1:DEPT:LIN?",
                           "AM1 线性深度回读")

    def get_lf_shape(self):
        """回读 LF1 波形（`LFO1:SHAP?`）"""
        return self._query(f"{self._source_prefix()}LFO1:SHAP?", "LF1 波形回读")

    def get_lf_frequency(self):
        """回读 LF1 频率（`LFO1:FREQ?`）"""
        return self._query(f"{self._source_prefix()}LFO1:FREQ?", "LF1 频率回读")

    # ==================== 频率调制 FM（手册 p448-450） ====================

    def enable_fm(self, enable=True):
        """开启 / 关闭频率调制（手册 p450）

        选件：R&S SMBB-K720

        Args:
            enable: True 开启、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "开启 FM1（频率调制）" if enable else "关闭 FM1"
        return self._write(f"{self._source_prefix()}FM1:STAT {self._onoff(enable)}", text)

    def set_fm_source(self, source):
        """选择频率调制的信号源（手册 p450）

        Args:
            source: 取值同 AM，见 set_am_source（*RST 默认 FM1→LF1）

        Returns:
            bool: 是否成功
        """
        value = self._enum(source, self.MOD_SOURCES, "fm_source")
        if value is None:
            return False
        return self._write(f"{self._source_prefix()}FM1:SOUR {value}",
                           f"FM1 调制源: {value}")

    def set_fm_deviation(self, deviation):
        """设置调频偏差，单位 Hz（手册 p450）

        Args:
            deviation: 0 ~ 最大值（*RST 默认 1E3；上限随 RF 频率与机型变化）

        Returns:
            bool: 是否成功
        """
        if deviation is None or deviation < 0:
            print(f"参数 fm_deviation={deviation} 非法，未下发")
            return False
        return self._write(f"{self._source_prefix()}FM1:DEV {deviation}",
                           f"FM1 调频偏差: {deviation} Hz")

    # ==================== 相位调制 PM / PhiM（手册 p453-457） ====================

    def enable_pm(self, enable=True):
        """开启 / 关闭相位调制（手册 p454）

        选件：R&S SMBB-K720

        **注意**：手册明确写着"激活相位调制会关闭频率调制"——
        FM 与 PM 不能同时开，这是单向副作用，关 PM 不会自动把 FM 开回来。

        Args:
            enable: True 开启、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "开启 PM1（相位调制）" if enable else "关闭 PM1"
        return self._write(f"{self._source_prefix()}PM1:STAT {self._onoff(enable)}", text)

    def set_pm_source(self, source):
        """选择相位调制的信号源（手册 p455）

        Args:
            source: 取值同 AM，见 set_am_source

        Returns:
            bool: 是否成功
        """
        value = self._enum(source, self.MOD_SOURCES, "pm_source")
        if value is None:
            return False
        return self._write(f"{self._source_prefix()}PM1:SOUR {value}",
                           f"PM1 调制源: {value}")

    def set_pm_deviation(self, deviation):
        """设置相位调制偏差，单位 rad（手册 p457）

        指令**显式带 RAD**：`UNIT:ANGLe`（手册 p596）能把角度默认单位改成度，
        届时裸数值 `PM:DEV 1` 会被当成 1°（= 0.0175 rad），仪器不报错，
        相位调制校准结果整体错 57.3 倍。

        Args:
            deviation: 0 ~ 最大值（rad；*RST 默认 1；上限随 RF 频率变化）

        Returns:
            bool: 是否成功
        """
        if deviation is None or deviation < 0:
            print(f"参数 pm_deviation={deviation} 非法，未下发")
            return False
        return self._write(f"{self._source_prefix()}PM1:DEV {deviation} RAD",
                           f"PM1 相位偏差: {deviation} rad")

    # ==================== 脉冲调制 PULM（手册 p458-462） ====================

    def enable_pulse_modulation(self, enable=True):
        """开启 / 关闭脉冲调制（手册 p461）

        Args:
            enable: True 开启、False 关闭

        Returns:
            bool: 是否成功
        """
        text = "开启脉冲调制" if enable else "关闭脉冲调制"
        return self._write(f"{self._source_prefix()}PULM:STAT {self._onoff(enable)}", text)

    def set_pulse_source(self, source):
        """选择脉冲调制源（手册 p461）

        Args:
            source: INTernal 内部脉冲发生器 / EXTernal 外部输入

        Returns:
            bool: 是否成功
        """
        value = self._enum(source, self.PULM_SOURCES, "pulse_source")
        if value is None:
            return False
        return self._write(f"{self._source_prefix()}PULM:SOUR {value}",
                           f"脉冲调制源: {value}")

    def set_pulse_period(self, period):
        """设置脉冲周期（= 内部调制信号重复频率的倒数）（手册 p460）

        Args:
            period: 20e-9 ~ 100（s；*RST 默认 10e-6）

        Returns:
            bool: 是否成功
        """
        if period is None or not (20e-9 <= period <= 100):
            print(f"参数 pulse_period={period} 超出范围 [2e-08, 100] s，未下发")
            return False
        return self._write(f"{self._source_prefix()}PULM:PER {period} s",
                           f"脉冲周期: {period} s")

    def set_pulse_width(self, width):
        """设置脉冲宽度（手册 p460）

        手册约束：必须至少比已设脉冲周期小 20 ns。

        Args:
            width: 20e-9 ~ 100（s；*RST 默认 2e-6）

        Returns:
            bool: 是否成功
        """
        if width is None or not (20e-9 <= width <= 100):
            print(f"参数 pulse_width={width} 超出范围 [2e-08, 100] s，未下发")
            return False
        return self._write(f"{self._source_prefix()}PULM:WIDT {width} s",
                           f"脉冲宽度: {width} s")
