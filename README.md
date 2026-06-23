# SG Test Scripts / 信号源自动化测试脚本

## 项目简介

本项目是一套用于**信号源（Signal Generator）自动化测试**的 Python 脚本集合，通过 PyVISA 库控制矢量信号发生器、频谱分析仪、功率计等射频/微波仪器，实现对信号源多项关键性能指标的自动测量与数据记录。

覆盖的测试类型包括谐波测试、分谐波测试、最大输出功率测试、功率扫描测试等，频率范围从 **3 kHz 到 40 GHz**。

### 版本：streaming

当前分支特性：

- **CSV 流式写入**：测量一点即写入一点，中途中断不丢数据，测试完成后自动转为 XLSX
- **统一继承架构**：所有 Procedure 类继承自 `BaseTestProcedure`，消除 ~700 行冗余代码
- **双格式输出**：支持 CSV / Excel，含摘要 + 详细数据双工作表
- **进一步消除重复**：抽取 PowerSweepBaseProcedure 公共基类，减少 ~250 行重复代码
- **配置键名对齐**：SPECTRUM_ANALYZER_CONFIG 增加 sa_settling_time，配置与实际读取一致

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
│   ├── base_test_procedure.py            # ★ 基础测试流程（通用功能基类）
│   ├── harmonic_test_procedure.py        # 谐波测试 (extends BaseTestProcedure)
│   ├── subharmonic_test_procedure.py     # 分谐波测试 (extends BaseTestProcedure)
│   ├── power_sweep_base.py               # ★ 最大/低频功率测试公共基类（新增）
│   ├── max_power_procedure.py            # 最大功率测试 (extends PowerSweepBaseProcedure)
│   ├── low_freq_max_power_procedure.py   # 低频段最大功率 (extends PowerSweepBaseProcedure)
│   └── power_sweep_procedure.py          # 功率扫描 (extends BaseTestProcedure)
├── run_scripts/                     # 可执行入口脚本
│   ├── harmonic_test.py                 # 谐波测试入口
│   ├── run_subharmonic_test.py          # 分谐波测试入口
│   ├── max_power_test.py                # 最大功率测试入口
│   ├── low_freq_max_power_test.py       # 低频段最大功率测试入口
│   └── power_sweep.py                   # 功率扫描测试入口
├── utils/                           # 工具模块
│   └── csv_streamer.py                  # CSV 流式写入工具
├── output/                          # 测试结果输出目录（.gitignore 排除）
├── wideband.py                      # 宽带噪声曲线生成工具
└── README.md
```

---

## 架构

### 继承体系

```
BaseTestProcedure                ← 所有通用方法
├── HarmonicTestProcedure            ← measure_harmonic_power / run_harmonic_test
├── SubharmonicTestProcedure         ← measure_subharmonic_power / run_subharmonic_test
├── PowerSweepBaseProcedure          ← 最大/低频功率测试公共基类
│   ├── MaxPowerProcedure            ← 功率扫描循环 + 双工作表 Excel
│   └── LowFreqMaxPowerProcedure     ← DC 耦合频谱仪低频测量
└── TestProcedure                    ← 功率扫描（功率计 + 频率相关衰减器）
```

### 基类公共方法

| 方法 | 说明 |
|------|------|
| `format_frequency()` | 智能频率格式化（Hz/kHz/MHz/GHz 自动切换） |
| `setup_signal_generator()` | 统一信号源设置流程 |
| `setup_spectrum_analyzer()` | 统一频谱仪设置流程（span/rbw/vbw/reference/attenuation） |
| `measure_fundamental_power()` | 基波功率测量（峰值搜索 + 多次平均） |
| `save_results_to_csv()` | 保存为 CSV |
| `save_results_to_excel()` | 保存为 Excel（摘要 + 详细数据双工作表） |
| `start_csv_stream()` | 开启流式 CSV 写入 |
| `finish_xlsx()` | 关闭流式写入转为 XLSX |
| `print_summary()` | 打印测试摘要 |

### CSV 流式写入

```
┌─────────┐   每测一点   ┌──────────┐   测试完成   ┌──────────┐
│ TestPoint │ ────────→  │ CSV Stream │ ────────→  │ XLSX File │
│ (逐点测量) │  立刻追加   │ (实时持久化) │ finish_xlsx │ (最终输出) │
└─────────┘             └──────────┘            └──────────┘
```

优势：中途断电或异常退出不丢失已测数据。

---

## 系统要求

- Python 3.8+
- PyVISA — 仪器控制
- pandas — 数据处理与 Excel 输出
- openpyxl — Excel 文件读写
- NumPy + SciPy — 数值计算与曲线插值
- Matplotlib — 数据可视化（仅 `wideband.py` 使用）
- VISA 驱动后端（NI-VISA 或 pyvisa-py）

```bash
pip install pyvisa pyvisa-py pandas openpyxl numpy scipy matplotlib
```

---

## 测试类型

### 谐波测试

| 项目 | 说明 |
|------|------|
| 入口 | `run_scripts/harmonic_test.py` |
| 配置 | `configs/harmonic_test_config.py` |
| 仪器 | 信号源 + 频谱分析仪 |
| 流程 | 设置频率 → 测量基波 → 测量 f×2 谐波 → 计算 dBc |

### 分谐波测试

| 项目 | 说明 |
|------|------|
| 入口 | `run_scripts/run_subharmonic_test.py` |
| 配置 | `configs/subharmonic_test_config.py` |
| 仪器 | 信号源 + 频谱分析仪 |
| 流程 | 设置频率 → 测量基波 → 测量 f/2 分谐波 → 计算 dBc |

### 最大功率测试

| 项目 | 说明 |
|------|------|
| 入口 | `run_scripts/max_power_test.py` |
| 配置 | `configs/max_power_config.py` |
| 仪器 | 信号源 + 功率计 |
| 特性 | 自动检测饱和点 / 过载点，输出双工作表 Excel |

### 低频段最大功率测试

| 项目 | 说明 |
|------|------|
| 入口 | `run_scripts/low_freq_max_power_test.py` |
| 配置 | `configs/low_freq_max_power_config.py` |
| 仪器 | 信号源 + 频谱分析仪（DC 耦合） |
| 频段 | 3 kHz – 100 kHz |

### 功率扫描测试

| 项目 | 说明 |
|------|------|
| 入口 | `run_scripts/power_sweep.py` |
| 配置 | `configs/power_sweep_config.py` |
| 仪器 | 信号源 + 功率计 |
| 特性 | 支持固定衰减器 / 频率相关衰减器 |

---

## 使用流程

1. **连接仪器**：信号源和测量仪器已开机并连接至计算机
2. **修改配置**：编辑 `configs/` 下对应的配置文件
3. **运行脚本**：执行 `run_scripts/` 下对应的入口脚本
4. **输入地址**：在提示下输入仪器 VISA 资源地址
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

- **Excel**：包含"测试摘要"和"详细数据"两个工作表
- **CSV 流式**：测量过程中实时持久化，测试完成后自动转 XLSX

---

## 注意事项

- 高功率测试时注意不超过仪器最大输入功率
- 功率计使用前需执行归零操作（脚本中已包含）
- 确保电缆和连接器状态良好
- 全频段扫描会产生较大数据量，注意磁盘空间

---

## 变更记录

**v2.0（当前）**
- 重构：抽取 PowerSweepBaseProcedure，消除 max_power_procedure.py 和 low_freq_max_power_procedure.py 之间约 250 行重复代码
- 修复：harmonic_test_config.py 中 point['duration'] 键名错误导致的 KeyError
- 修复：4 个入口脚本中 CSV 文件时间戳格式从反人类的 %S%M%H 改为 %Y%m%d_%H%M%S
- 修复：谐波/分谐波配置中缺失 sa_settling_time 键，配置值此前未生效
- 清理：移除未使用的 utils/project_manager.py（死代码）
- 清理：移除 Windows 项目多余的 #!/usr/bin/env python3 shebang
- 清理：移除所有形同虚设的 __init__.py（项目使用 sys.path.append + 直接 import）
- 清理：删除残余 VISA 硬件地址注释

**streaming**
- 重构：Procedure 继承体系统一，消除 ~700 行重复代码
- 新增：CsvStreamer 流式写入，支持中断保护
- 改进：format_frequency 全局统一

**master**
- 所有 5 类测试完整实现
- 支持频谱仪和功率计双仪器
- Excel 双工作表输出