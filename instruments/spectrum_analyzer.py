# -*- coding: utf-8 -*-
"""频谱仪门面类：品牌识别 + 到品牌后端的**透明转发**。

职责只有两件：
1. 读 `*IDN?` 判定仪器品牌（可用 `brand=` 参数显式覆盖）；
2. 按品牌装配 `instruments/backends/` 下的后端，并把所有驱动方法**原样转发**给它。

设计要点：**门面不重复声明后端的方法面。**
早期版本把每个驱动方法都在这里手写一遍（37 个 `return self.backend.xxx(...)`），
结果是"同一种仪器两套驱动代码"——方法名、签名、docstring 都要在门面和后端各维护
一份，两边迟早漂移；给后端加一个方法还得改三个文件。现在改为 `__getattr__` 动态
转发，门面只保留品牌识别这段真实逻辑，**方法面只有后端一份**。

代价（已知、有意接受）：静态分析工具与 IDE 自动补全看不到门面上的驱动方法
（`dir()` 已做弥补，见 `__dir__`）；查某个方法的实现与参数，直接看
`backends/sa_<品牌>.py`，或基类 `backends/sa_base.py`。

品牌策略：
- 自动识别：`Rohde&Schwarz` → rohde；`Keysight` / `Agilent` → keysight
- 识别失败或未支持的品牌 → 回退 `SpectrumAnalyzerBackend`（通用 SCPI 子集照发，
  品牌专有设置告警并跳过，不中断流程）
- 未知品牌也可在调用处显式指定，例如
      SpectrumAnalyzer(instrument, brand="keysight")

用法（与改造前完全一致，调用方无需改动）：
    sa = SpectrumAnalyzer(visa_instrument)
    sa.set_center_frequency(1e9)
    sa.select_demod_measurement("AM")     # 解调：先切 ADEMOD 模式
    sa.set_demod_span(1e6)
"""
import os
import sys

# 保证以「顶层模块」方式导入本文件时，同目录的 brand / backends 可被解析
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import brand as _brand  # noqa: E402
from backends.sa_base import SpectrumAnalyzerBackend  # noqa: E402
from backends.sa_rohde import RohdeSpectrumAnalyzer  # noqa: E402
from backends.sa_keysight import KeysightSpectrumAnalyzer  # noqa: E402

# 品牌 → 后端实现。未识别品牌回退到基类 —— 它本身就是通用回退驱动，
# 不再单独设一个 GenericSpectrumAnalyzer（同一角色不要两个类）。
_BACKENDS = {
    _brand.ROHDE: RohdeSpectrumAnalyzer,
    _brand.KEYSIGHT: KeysightSpectrumAnalyzer,
}
_DEFAULT_BACKEND = SpectrumAnalyzerBackend

_BRAND_ALIASES = {
    "rs": _brand.ROHDE,
    "r&s": _brand.ROHDE,
    "rohde": _brand.ROHDE,
    "rohde&schwarz": _brand.ROHDE,
    "keysight": _brand.KEYSIGHT,
    "agilent": _brand.KEYSIGHT,
}

#: 门面方法名 → 后端方法名。仅**名字不同**的才登记，其余同名直通。
#: `query_raw` 是历史命名，后端侧叫 `query`；改门面名字会波及调用方，故留别名。
_METHOD_ALIASES = {
    "query_raw": "query",
}


class SpectrumAnalyzer:
    """频谱仪控制门面：品牌识别 + 透明转发到品牌后端。

    除构造与品牌识别外，本类**不额外定义任何驱动方法**：对未定义属性的访问
    一律转发给 `self.backend`（见 `__getattr__`）。方法面以 `backends/` 为准。
    """

    def __init__(self, instrument, brand=None):
        """初始化频谱仪。

        Args:
            instrument: pyvisa 仪器对象
            brand: 显式指定品牌（"rohde" / "keysight"）；None 则读 *IDN? 自动识别
        """
        self.instrument = instrument
        self.idn = self._read_idn()
        self.brand = self._resolve_brand(brand)

        backend_cls = _BACKENDS.get(self.brand)
        if backend_cls is None:
            print(f"警告: 未识别频谱仪品牌(IDN={self.idn!r})，"
                  f"回退通用后端（品牌专有设置将告警并跳过）")
            backend_cls = _DEFAULT_BACKEND

        self.backend = backend_cls(instrument)
        print(f"频谱仪品牌: {self.brand}（后端 {backend_cls.__name__}）")

    # ------------------------------------------------------------------
    # 品牌识别（门面唯一的真实逻辑）
    # ------------------------------------------------------------------
    def _read_idn(self, retries=2):
        """读取 `*IDN?`；失败重试，仍失败返回 None。"""
        for attempt in range(retries + 1):
            try:
                return self.instrument.query("*IDN?")
            except Exception as e:
                if attempt >= retries:
                    print(f"读取仪器ID失败: {e}")
                    return None
        return None

    def _resolve_brand(self, brand):
        """确定使用的品牌：显式参数优先于 `*IDN?` 自动识别。"""
        if brand:
            key = str(brand).strip().lower()
            return _BRAND_ALIASES.get(key, key)
        return _brand.detect_brand(self.idn)

    # ------------------------------------------------------------------
    # 透明转发
    # ------------------------------------------------------------------
    def __getattr__(self, name):
        """把未定义的属性访问转发给后端。

        这样驱动方法面只存在于后端一处，给后端新增方法无需同步改门面。
        """
        # 下划线开头（含 dunder）一律不转发：
        # ① 避免 `__deepcopy__` / `__getstate__` / `__copy__` 一类探测被当成驱动方法；
        # ② 避免 __init__ 里 `self.backend` 尚未赋值时被递归拉进来。
        if name.startswith("_"):
            raise AttributeError(name)
        backend = self.__dict__.get("backend")
        if backend is None:
            raise AttributeError(name)

        target = _METHOD_ALIASES.get(name, name)
        try:
            return getattr(backend, target)
        except AttributeError:
            raise AttributeError(
                f"{type(self).__name__} 无 {name!r}，后端 "
                f"{type(backend).__name__} 也未提供 {target!r}") from None

    def __dir__(self):
        """让 `dir()` 与自动补全能看到后端的方法。

        动态转发牺牲了"看得到"的能力，这里补回来一部分。
        """
        names = set(super().__dir__())
        backend = self.__dict__.get("backend")
        if backend is not None:
            names |= {n for n in dir(backend) if not n.startswith("_")}
        return sorted(names)
