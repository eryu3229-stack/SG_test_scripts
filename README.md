# 信号源自动化测试脚本（SG Test Scripts）

本项目通过 PyVISA 控制信号源、频谱分析仪和功率计，自动完成谐波、分谐波、最大输出功率、功率扫描等测试，并把结果保存为 Excel（.xlsx）或 CSV 文件。

---

## 快速开始

### 1. 安装 Python 与依赖

需要 Python 3.8+，然后在命令行执行：

```bash
pip install pyvisa pyvisa-py pandas openpyxl numpy scipy matplotlib
```

还需要 VISA 驱动后端，二选一即可：NI-VISA（配合 NI MAX 管理仪器）或 pyvisa-py。

### 2. 连接仪器

将信号源、频谱分析仪或功率计开机，并通过网口（TCP/IP）、USB 或 GPIB 连接到电脑。不同测试需要连接的仪器如下：

| 测试 | 所需仪器 |
|------|----------|
| 谐波测试 / 分谐波测试 | 信号源 + 频谱分析仪 |
| 最大功率测试 / 功率扫描测试 | 信号源 + 功率计 |
| 低频段最大功率测试 | 信号源 + 频谱分析仪 |
| 单频点功率扫描 | 信号源 + 功率计 |

### 3. 修改配置（可选）

测试参数位于 `configs/` 目录，按测试类型选择对应文件修改。默认配置可以直接运行，首次上手建议先用较小的频率范围验证流程。

- 频率单位统一为 Hz，例如 `1e9` 表示 1 GHz
- 功率单位统一为 dBm
- 修改配置后重新运行入口脚本即可生效

### 4. 运行测试

在项目根目录执行入口脚本，例如谐波测试：

```bash
python run_scripts/harmonic_test.py
```

启动后脚本会列出当前可用的 VISA 仪器，并逐个询问资源地址。直接回车表示跳过该仪器，但测试要求相应仪器必须连接成功。

各测试的入口脚本见下文“测试类型速查表”。

### 5. 查看结果

测试完成后，结果保存在 `output/` 目录，文件名格式为 `测试类型_时间戳.xlsx`，例如 `harmonic_test_results_20260724_124936.xlsx`。

---

## VISA 资源地址示例

| 连接类型 | 示例 |
|----------|------|
| TCP/IP | `TCPIP::192.168.1.100::INSTR` |
| USB | `USB::0x0AAD::0x015F::101930::INSTR` |
| GPIB | `GPIB::10::INSTR` |

---

## 测试类型速查表

| 测试类型 | 作用 | 入口脚本 | 配置文件 |
|----------|------|----------|----------|
| 谐波测试 | 测量二次谐波抑制度（dBc） | `run_scripts/harmonic_test.py` | `configs/harmonic_test_config.py` |
| 分谐波测试 | 测量 1/2 分谐波抑制度（dBc） | `run_scripts/run_subharmonic_test.py` | `configs/subharmonic_test_config.py` |
| 最大功率测试 | 逐频点扫描功率，寻找最大输出功率与饱和点 | `run_scripts/max_power_test.py` | `configs/max_power_config.py` |
| 低频段最大功率测试 | 在 9 kHz 到 50 MHz 范围测量最大输出功率 | `run_scripts/low_freq_max_power_test.py` | `configs/low_freq_max_power_config.py` |
| 功率扫描测试 | 记录设定功率与实际测量功率的对应关系 | `run_scripts/power_sweep.py` | `configs/power_sweep_config.py` |
| 单频点功率扫描 | 在固定频点上扫描设定功率并记录实际功率 | `run_scripts/single_frequency_power_sweep.py` | `configs/single_frequency_power_sweep_config.py` |

---

## 目录结构

```
SG_test_scripts/
├── configs/                        # 测试参数配置
│   ├── harmonic_test_config.py
│   ├── subharmonic_test_config.py
│   ├── max_power_config.py
│   ├── low_freq_max_power_config.py
│   ├── power_sweep_config.py
│   └── single_frequency_power_sweep_config.py
├── instruments/                    # 仪器控制层（硬件抽象）
│   ├── instrument_manager.py       # VISA 连接管理
│   ├── signal_generator.py         # 信号源控制
│   ├── spectrum_analyzer.py        # 频谱分析仪控制
│   └── power_meter.py              # 功率计控制
├── procedures/                     # 测试流程实现
│   ├── base_test_procedure.py      # 公共方法
│   ├── harmonic_test_procedure.py
│   ├── subharmonic_test_procedure.py
│   ├── max_power_procedure.py
│   ├── low_freq_max_power_procedure.py
│   ├── power_sweep_procedure.py
│   └── single_frequency_power_sweep_procedure.py
├── run_scripts/                    # 可执行入口脚本
│   ├── harmonic_test.py
│   ├── run_subharmonic_test.py
│   ├── max_power_test.py
│   ├── low_freq_max_power_test.py
│   ├── power_sweep.py
│   └── single_frequency_power_sweep.py
├── utils/                          # 工具模块
│   └── project_manager.py
├── output/                         # 测试结果输出目录（.gitignore 排除）
├── wideband.py                     # 宽带噪声曲线生成工具（独立使用）
└── README.md
```

---

## 测试说明

### 谐波测试

流程：设置频率和功率 → 测量基波功率 → 测量 2×f 处谐波功率 → 计算 dBc。

关键配置块：`FREQUENCY_SWEEP_CONFIG`、`SPECTRUM_ANALYZER_CONFIG`、`HARMONIC_MEASUREMENT_CONFIG`。谐波阶数由 `harmonic_order` 控制，默认测量二次谐波。

### 分谐波测试

流程：设置频率和功率 → 测量基波功率 → 测量 f/2 处分谐波功率 → 计算 dBc。

关键配置块：`FREQUENCY_SWEEP_CONFIG`、`SPECTRUM_ANALYZER_CONFIG`、`SUBHARMONIC_MEASUREMENT_CONFIG`。分谐波阶数由 `subharmonic_orders` 控制，默认值为 `[2]`，即测量 1/2 次分谐波。

### 最大功率测试

从 `start_power` 开始逐步增加功率，直到检测到饱和、过载或达到 `max_set_power`。脚本运行时会先要求功率计断开输入并归零，归零完成后重新连接输入信号，按 Enter 继续。

关键参数：`frequency_ranges`、`start_power`、`power_step`、`max_set_power`、`max_measured_power`、`power_tolerance`、`max_power_drop`、`use_attenuator`、`attenuator_value`。

### 低频段最大功率测试

默认在 9 kHz 到 50 MHz 范围测量最大输出功率，频谱仪使用 DC 耦合和低 RBW，适合低频信号。

关键参数：`frequency_ranges`、`start_power`、`power_step`、`spectrum_analyzer_config`（含 `input_coupling`、`span`、`rbw`、`vbw`）。

### 功率扫描测试

对每个频点按多个设定功率值输出信号并测量实际功率，用于检查功率精度和线性度。

关键参数：`start_freq`、`end_freq`、`step_freq`、`power_settings`、`attenuator_enabled`、`attenuator_value`、`attenuator_freq_dependent`。

### 单频点功率扫描

在固定频点上按 `start_power` 到 `end_power` 扫描信号源设定功率，使用功率计逐点测量实际功率，并支持衰减器补偿。当前版本使用功率计测量；若后续需要低功率精确测量，可在此基础上扩展频谱分析仪测量模式。

关键参数：`frequency`、`start_power`、`end_power`、`power_step`、`settling_time`、`pm_settling_time`、`measurement_times`、`max_set_power`、`max_measured_power`、`attenuator_enabled`、`attenuator_value`。

---

## 配置文件说明

### 通用配置项

| 类别 | 参数 | 说明 |
|------|------|------|
| 频率 | `start_frequency` / `end_frequency` / `step_frequency`，或 `frequency_ranges` | 扫描范围与步进，单位 Hz |
| 功率 | `fixed_power` / `start_power` / `power_step` / `power_settings` | 固定功率或扫描功率，单位 dBm |
| 保护上限 | `max_set_power` / `max_measured_power` | 信号源最大设定功率、测量仪器最大输入功率 |
| 稳定时间 | `settling_time` / `sa_settling_time` / `pm_settling_time` | 频率或功率切换后的等待时间，单位秒 |
| 测量次数 | `measurement_times` / `measurement_average` | 多次测量取平均的次数 |
| 衰减器 | `use_attenuator` / `attenuator_value` / `attenuator_freq_dependent` | 外接衰减器补偿，单位 dB |
| 饱和判定 | `power_tolerance` / `max_power_drop` | 功率饱和与过载判定阈值，单位 dB |

### 各配置文件的主要配置块

| 配置文件 | 主要配置块 |
|----------|------------|
| `harmonic_test_config.py` | `FREQUENCY_SWEEP_CONFIG`、`SPECTRUM_ANALYZER_CONFIG`、`HARMONIC_MEASUREMENT_CONFIG`、`OUTPUT_CONFIG` |
| `subharmonic_test_config.py` | `FREQUENCY_SWEEP_CONFIG`、`SPECTRUM_ANALYZER_CONFIG`、`SUBHARMONIC_MEASUREMENT_CONFIG`、`OUTPUT_CONFIG` |
| `max_power_config.py` | `frequency_ranges`、`start_power`、`power_step`、`max_set_power`、`max_measured_power`、衰减器参数 |
| `low_freq_max_power_config.py` | `frequency_ranges`、`start_power`、`power_step`、`spectrum_analyzer_config`、衰减器参数 |
| `power_sweep_config.py` | `start_freq` / `end_freq` / `step_freq`、`power_settings`、衰减器参数 |
| `single_frequency_power_sweep_config.py` | `frequency`、`start_power` / `end_power` / `power_step`、衰减器参数 |

---

## 输出文件

- 输出目录：`output/`，已被 `.gitignore` 排除，不会上传到 Git
- 命名格式：`测试类型_时间戳.xlsx`，不会覆盖已有文件
- Excel 文件通常包含测试摘要和详细数据；部分流程也会输出 CSV

---

## 注意事项

### 仪器安全

- 测试功率不要超过频谱仪或功率计的最大输入功率
- `max_set_power` 和 `max_measured_power` 是保护参数，不要随意调大
- 功率计使用前必须归零，归零前脚本会要求断开输入并确认开路状态，无输入信号时才可执行归零
- 测试前确认电缆和连接器状态良好

### 配置管理

- 频率参数统一使用 Hz，功率参数统一使用 dBm
- 修改配置后直接运行入口脚本即可生效
- 重要测试前建议备份原配置文件

### 运行提示

- 建议在项目根目录运行 `python run_scripts/xxx.py`
- 脚本会打印当前测试的配置摘要和测试点数量，运行前请核对
- 信号源输出会在测试结束后自动关闭，异常退出时也会尝试关闭

---

## 故障排查

### 仪器连接失败

1. 检查仪器电源、通信线缆和 VISA 资源地址
2. 验证 VISA 是否识别仪器：`python -c "import pyvisa; rm = pyvisa.ResourceManager(); print(rm.list_resources())"`
3. TCP/IP 连接先 ping 测试网络连通性
4. 使用 NI-VISA 的用户可通过 NI MAX 确认仪器是否被识别

### 测量结果异常

1. 用功率计直连信号源，确认信号源输出是否正常
2. 检查频谱仪或功率计的衰减、参考电平、输入耦合设置
3. 确认电缆损耗和衰减器补偿值是否正确
4. 查看控制台输出的 SCPI 错误信息

---

## 许可

仅限内部使用，未经授权不得外传或用于商业用途。
