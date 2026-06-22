# SG Test Scripts / 信号源自动化测试脚本

## 项目简介

本项目是一套用于**信号源（Signal Generator）自动化测试**的 Python 脚本集合，通过 PyVISA 库控制矢量信号发生器、频谱分析仪、功率计等射频/微波仪器，实现对信号源多项关键性能指标的自动测量与数据记录。

覆盖的测试类型包括谐波测试、分谐波测试、最大输出功率测试、功率扫描测试等，频率范围从 **3 kHz 到 40 GHz**，测试结果导出为 Excel（.xlsx）或 CSV 格式。

---

## 目录结构

```
SG_test_scripts/
├── configs/                          # 测试配置文件
│   ├── harmonic_test_config.py           # 谐波测试配置
│   ├── subharmonic_test_config.py        # 分谐波测试配置
│   ├── max_power_config.py               # 最大功率测试配置
│   ├── low_freq_max_power_config.py      # 低频段最大功率测试配置
│   └── power_sweep_config.py             # 功率扫描测试配置
├── instruments/                     # 仪器控制模块（硬件抽象层）
│   ├── instrument_manager.py             # 仪器资源管理器（VISA 连接管理）
│   ├── signal_generator.py               # 信号源控制类
│   ├── spectrum_analyzer.py              # 频谱分析仪控制类
│   └── power_meter.py                    # 功率计控制类
├── procedures/                      # 测试流程模块
│   ├── base_test_procedure.py            # 基础测试流程（公共方法）
│   ├── harmonic_test_procedure.py        # 谐波测试流程
│   ├── subharmonic_test_procedure.py     # 分谐波测试流程
│   ├── max_power_procedure.py            # 最大功率测试流程
│   ├── low_freq_max_power_procedure.py   # 低频段最大功率测试流程
│   └── power_sweep_procedure.py          # 功率扫描测试流程
├── run_scripts/                     # 可执行入口脚本
│   ├── harmonic_test.py                 # 谐波测试入口
│   ├── run_subharmonic_test.py          # 分谐波测试入口
│   ├── max_power_test.py                # 最大功率测试入口
│   ├── low_freq_max_power_test.py       # 低频段最大功率测试入口
│   └── power_sweep.py                   # 功率扫描测试入口
├── utils/                           # 工具模块
│   └── project_manager.py               # 项目配置管理
├── output/                          # 测试结果输出目录（.gitignore 排除）
├── wideband.py                      # 宽带噪声曲线生成工具（独立使用）
└── README.md
```

---

## 系统要求

- Python 3.8+
- [PyVISA](https://pyvisa.readthedocs.io/) — 仪器控制（VISA 通信）
- [pandas](https://pandas.pydata.org/) — 数据处理与 Excel 输出
- [openpyxl](https://openpyxl.readthedocs.io/) — Excel 文件读写
- [NumPy](https://numpy.org/) + [SciPy](https://scipy.org/) — 数值计算与曲线插值
- [Matplotlib](https://matplotlib.org/) — 数据可视化（仅 `wideband.py` 使用）
- VISA 驱动后端（NI-VISA 或 pyvisa-py）

### 安装依赖

```bash
pip install pyvisa pyvisa-py pandas openpyxl numpy scipy matplotlib
```

---

## 功能模块详解

### 仪器控制层 — 硬件抽象 (`instruments/`)

通过 PyVISA 与物理仪器通信，每条 SCPI 命令封装为独立的 Python 方法。

#### 仪器资源管理器 — `InstrumentManager`
- 封装 `pyvisa.ResourceManager`，管理所有仪器的连接生命周期
- `list_instruments()` — 枚举可用 VISA 资源
- `connect_instrument(resource_name, instrument_type)` — 按类型连接指定仪器
- `disconnect_all()` — 断开所有连接

#### 信号源控制 — `SignalGenerator`
- `set_frequency(freq_hz)` / `set_power(power_dbm)` — 设置频率和功率
- `enable_output(bool)` — 开启/关闭 RF 输出
- `get_idn()` — 查询仪器标识

#### 频谱分析仪控制 — `SpectrumAnalyzer`
- 频率设置：`set_center_frequency()` / `set_span()`
- 分辨率设置：`set_rbw()` / `set_vbw()`
- 参考电平与衰减：`set_reference_level()` / `set_attenuation()`
- 输入耦合：`set_input_coupling(AC|DC)`
- 峰值搜索与标记测量：`peak_search()` / `measure_marker_power()` / `get_marker_frequency()`
- 通用功率测量：`measure_power()`（MAX HOLD 模式）

#### 功率计控制 — `PowerMeter`
- 频率设置与单位控制：`set_frequency()` / `set_power_unit(WATT|DBM)`
- 归零：`zero()` — 同步阻塞操作，测量前必须执行
- 多测量平均：`measure_power(times=N)` — 返回 N 次测量的平均值
- 复位与错误检查：`reset()` / `check_errors()`

---

## 测试类型说明

### 谐波测试 — `HarmonicTestProcedure`

测量信号源的二次谐波（2nd Harmonic）抑制度。

| 项目 | 说明 |
|------|------|
| 配置 | `configs/harmonic_test_config.py` |
| 入口 | `run_scripts/harmonic_test.py` |
| 仪器 | 信号源 + 频谱分析仪 |
| 流程 | 设置频率 → 测量基波功率 → 测量 f×2 处谐波功率 → 计算 dBc |

### 分谐波测试 — `SubharmonicTestProcedure`

测量信号源的分谐波（1/2 次）抑制度。

| 项目 | 说明 |
|------|------|
| 配置 | `configs/subharmonic_test_config.py` |
| 入口 | `run_scripts/run_subharmonic_test.py` |
| 仪器 | 信号源 + 频谱分析仪 |
| 流程 | 设置频率 → 测量基波功率 → 测量 f/2 处分谐波功率 → 计算 dBc |

### 最大功率测试 — `MaxPowerProcedure`

测量信号源在每个频点的最大可用输出功率。从起始功率逐步增加，自动检测饱和点、过载点和限幅点。

| 项目 | 说明 |
|------|------|
| 配置 | `configs/max_power_config.py` |
| 入口 | `run_scripts/max_power_test.py` |
| 仪器 | 信号源 + 功率计 |
| 特性 | 支持外接衰减器补偿，输出双工作表 Excel（摘要 + 详细扫描数据） |

### 低频段最大功率测试 — `LowFreqMaxPowerProcedure`

在低频段（3 kHz – 100 kHz）测量最大输出功率，使用频谱仪的 DC 耦合和低 RBW。

| 项目 | 说明 |
|------|------|
| 配置 | `configs/low_freq_max_power_config.py` |
| 入口 | `run_scripts/low_freq_max_power_test.py` |
| 仪器 | 信号源 + 频谱分析仪（DC 耦合） |

### 功率扫描测试 — `TestProcedure`

在指定频点进行功率扫描，记录设定功率与实际测量功率的对应关系，验证功率精度和线性度。

| 项目 | 说明 |
|------|------|
| 配置 | `configs/power_sweep_config.py` |
| 入口 | `run_scripts/power_sweep.py` |
| 仪器 | 信号源 + 功率计 |
| 特性 | 支持固定衰减器和频率相关衰减器 |

---

## 使用流程

1. **连接仪器**：确保信号源和测量仪器（频谱仪/功率计）已开机并连接至计算机
2. **修改配置**：编辑 `configs/` 下对应的配置文件（频率范围、功率、仪器参数等）
3. **运行脚本**：执行 `run_scripts/` 下对应的入口脚本
4. **输入地址**：在提示下输入仪器 VISA 资源地址（直接回车可跳过）
5. **查看结果**：测试结果输出至 `output/` 目录

### VISA 资源格式

| 连接类型 | 示例 |
|----------|------|
| TCP/IP | `TCPIP::192.168.1.100::INSTR` |
| USB | `USB::0x0AAD::0x015F::101930::INSTR` |
| GPIB | `GPIB::10::INSTR` |

---

## 输出文件

输出文件命名格式：`测试类型_时间戳.xlsx`，存放于 `output/` 目录（`.gitignore` 排除）。

- **Excel**：使用 pandas + openpyxl 输出，含测试摘要和详细数据
- **CSV**：标准 csv 模块输出

---

## 配置说明

### 通用配置项

| 类别 | 参数 | 说明 |
|------|------|------|
| 频率扫描 | `start_frequency` / `end_frequency` / `step_frequency` | 扫描范围与步进，单位 Hz |
| 功率 | `fixed_power` / `start_power` / `power_step` | 固定功率或扫描起止 |
| 稳定时间 | `settling_time` / `sa_settling_time` / `pm_settling_time` | 频率/功率切换后的等待时间（秒） |
| 测量次数 | `measurement_times` / `measurement_average` | 多次测量取平均的次数 |
| 衰减器 | `attenuator_value` / `use_attenuator` | 外接衰减器补偿设置 |
| 饱和检测 | `power_tolerance` / `max_power_drop` | 功率饱和与过载判定阈值 |

---

## 注意事项

### 仪器安全
- 高功率测试时注意不超过仪器的最大输入功率
- 功率计使用前需执行归零操作（脚本中已包含）
- 确保电缆和连接器状态良好

### 配置管理
- 频率参数全部使用 Hz 为单位（如 `1e9` 表示 1 GHz）
- 功率参数使用 dBm 为单位
- 修改配置后直接覆盖原文件，建议重要测试前备份

### 文件管理
- 输出文件按 `测试类型_时间戳.xlsx` 命名，不会自动覆盖
- `output/` 目录已在 `.gitignore` 中排除
- 全频段扫描会产生较大数据量，注意磁盘空间

---

## 故障排查

### 仪器连接失败
1. 检查仪器电源与通信线缆
2. 测试 VISA 通信：`python -c "import pyvisa; rm = pyvisa.ResourceManager(); print(rm.list_resources())"`
3. TCP/IP 连接先 ping 测试网络连通性
4. NI-VISA 用户可用 NI MAX 确认仪器是否被识别

### 测量结果异常
1. 检查信号源输出是否正常（可用功率计直连验证）
2. 检查频谱仪/功率计的衰减器、参考电平设置
3. 确认电缆损耗、衰减器补偿值
4. 查看控制台输出的 SCPI 错误信息

---

## 许可

仅限内部使用，未经授权不得外传或用于商业用途。