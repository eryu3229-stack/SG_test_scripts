# SG测试脚本项目说明文档

## 项目简介

本项目是一套用于信号源(Signal Generator, SG)自动化测试的Python脚本集合，主要用于测试信号源的各项性能指标，包括谐波、分谐波、最大功率等。项目使用PyVISA库控制各类测试仪器，实现自动化测试流程，并将测试结果保存为Excel文件。

## 目录结构

```
SG_test_scripts/
├── configs/                    # 测试配置文件目录
│   ├── harmonic_test_config.py      # 谐波测试配置
│   ├── low_freq_max_power_config.py # 低频段最大功率测试配置
│   ├── max_power_config.py          # 最大功率测试配置
│   ├── power_sweep_config.py        # 功率扫描测试配置
│   └── subharmonic_test_config.py   # 分谐波测试配置
├── instruments/               # 仪器控制类目录
│   ├── instrument_manager.py        # 仪器资源管理器
│   ├── power_meter.py               # 功率计控制类
│   ├── signal_generator.py          # 信号源控制类
│   └── spectrum_analyzer.py         # 频谱仪控制类
├── procedures/                # 测试流程类目录
│   ├── base_test_procedure.py       # 基础测试流程类
│   ├── harmonic_test_procedure.py   # 谐波测试流程类
│   ├── low_freq_max_power_procedure.py  # 低频段最大功率测试流程类
│   ├── max_power_procedure.py       # 最大功率测试流程类
│   ├── power_sweep_procedure.py     # 功率扫描测试流程类
│   └── subharmonic_test_procedure.py    # 分谐波测试流程类
├── run_scripts/               # 测试运行脚本目录
│   ├── harmonic_test.py            # 谐波测试运行脚本
│   ├── low_freq_max_power_test.py  # 低频段最大功率测试运行脚本
│   ├── max_power_test.py           # 最大功率测试运行脚本
│   ├── power_sweep.py              # 功率扫描测试运行脚本
│   ├── run_subharmonic_test.py     # 分谐波测试运行脚本
│   └── projects/                   # 项目配置保存目录
├── utils/                     # 工具类目录
│   └── project_manager.py          # 项目管理器
├── output/                    # 测试结果输出目录
├── wideband.py               # 宽带噪声曲线生成脚本
└── README.md                 # 本说明文档
```

## 系统要求

- Python 3.6或更高版本
- PyVISA库（用于仪器控制）
- Pandas库（用于数据处理）
- OpenPyXL库（用于Excel文件操作）
- NumPy和SciPy库（用于数据处理和曲线生成）
- Matplotlib库（用于绘图）

## 安装依赖

在项目根目录下运行以下命令安装所需依赖：

```bash
pip install pyvisa pandas openpyxl numpy scipy matplotlib
```

## 功能模块

### 1. 仪器控制模块 (instruments/)

#### 1.1 仪器管理器 (instrument_manager.py)
- 管理所有测试仪器的连接和断开
- 列出所有可用仪器资源
- 支持多种仪器类型的连接

#### 1.2 信号源控制 (signal_generator.py)
- 设置信号源频率
- 设置信号源功率
- 启用/禁用信号源输出
- 获取仪器ID信息

#### 1.3 频谱仪控制 (spectrum_analyzer.py)
- 设置中心频率
- 设置频率跨度
- 设置参考电平
- 测量功率
- 峰值搜索
- 设置标记器
- 测量标记器功率

#### 1.4 功率计控制 (power_meter.py)
- 设置测量频率
- 设置功率单位
- 执行归零操作
- 测量功率（支持多次测量取平均）
- 复位功率计

### 2. 测试流程模块 (procedures/)

#### 2.1 基础测试流程 (base_test_procedure.py)
- 提供测试流程的公共功能
- 信号源设置
- 频谱仪设置
- 频率格式化显示
- 测试结果保存

#### 2.2 谐波测试流程 (harmonic_test_procedure.py)
- 测量信号源的二次谐波性能
- 记录基波和二次谐波功率
- 计算谐波抑制比(dBc)
- 支持频率扫描测试

#### 2.3 低频段最大功率测试流程 (low_freq_max_power_procedure.py)
- 在低频段(3kHz-100kHz)测试信号源最大输出功率
- 使用频谱仪作为测量仪器
- 支持功率扫描以确定最大输出功率
- 自动检测饱和点和过载保护

#### 2.4 最大功率测试流程 (max_power_procedure.py)
- 测试信号源最大输出功率
- 使用功率计作为测量仪器
- 支持功率扫描以确定最大输出功率
- 自动检测饱和点和过载保护
- 支持衰减器补偿

#### 2.5 功率扫描测试流程 (power_sweep_procedure.py)
- 在指定频率点进行功率扫描测试
- 记录设定功率和实际测量功率
- 计算功率误差
- 支持衰减器补偿

#### 2.6 分谐波测试流程 (subharmonic_test_procedure.py)
- 测试信号源的分谐波性能
- 记录基波和分谐波功率
- 计算分谐波抑制比(dBc)
- 支持频率扫描测试

### 3. 配置模块 (configs/)

每个测试类型都有对应的配置文件，包含以下主要配置项：

- 频率扫描配置：起始频率、结束频率、频率步进、固定功率等
- 仪器配置：频谱仪/功率计的测量参数
- 测试参数：测量次数、稳定时间、容差等
- 输出配置：输出格式、是否包含时间戳等

### 4. 运行脚本模块 (run_scripts/)

每个测试类型都有对应的运行脚本，用于执行测试：

- `harmonic_test.py` - 运行谐波测试
- `low_freq_max_power_test.py` - 运行低频段最大功率测试
- `max_power_test.py` - 运行最大功率测试
- `power_sweep.py` - 运行功率扫描测试
- `run_subharmonic_test.py` - 运行分谐波测试

### 5. 工具模块 (utils/)

#### 5.1 项目管理器 (project_manager.py)
- 管理测试项目的创建、保存和加载
- 支持项目配置的持久化存储
- 列出所有已保存的项目

### 6. 宽带噪声曲线生成 (wideband.py)

- 生成宽带噪声曲线
- 支持自定义频率范围和噪声规范
- 生成平滑的高斯噪声曲线
- 支持不同频段的噪声幅度调整
- 生成可视化图表

## 使用方法

### 1. 基本使用流程

1. 确保所有测试仪器已正确连接到计算机
2. 根据需要修改相应的配置文件
3. 运行对应的测试脚本
4. 查看测试结果（保存在output目录）

### 2. 运行谐波测试

```bash
cd run_scripts
python harmonic_test.py
```

按照提示输入信号源和频谱仪的资源地址，测试将自动进行。

### 3. 运行最大功率测试

```bash
cd run_scripts
python max_power_test.py
```

按照提示输入信号源和功率计的资源地址，测试将自动进行。

### 4. 运行功率扫描测试

```bash
cd run_scripts
python power_sweep.py
```

按照提示输入信号源和功率计的资源地址，测试将自动进行。

### 5. 运行分谐波测试

```bash
cd run_scripts
python run_subharmonic_test.py
```

按照提示输入信号源和频谱仪的资源地址，测试将自动进行。

### 6. 运行低频段最大功率测试

```bash
cd run_scripts
python low_freq_max_power_test.py
```

按照提示输入信号源和频谱仪的资源地址，测试将自动进行。

### 7. 生成宽带噪声曲线

```bash
python wideband.py
```

脚本将生成噪声曲线图表并保存为PNG文件。

## 测试结果

所有测试结果保存在`output`目录中，文件格式为Excel(.xlsx)或CSV。文件名包含测试类型和时间戳，便于识别和管理。

## 配置说明

### 修改测试参数

编辑`configs`目录下对应的配置文件，修改以下参数：

- 频率范围（起始频率、结束频率、频率步进）
- 功率参数（固定功率、功率扫描范围）
- 仪器稳定时间
- 测量次数
- 衰减器设置

### 仪器连接地址

常见的仪器连接地址格式：

- TCPIP连接：`TCPIP::192.168.1.100::INSTR`
- USB连接：`USB::0x0AAD::0x015F::101930::INSTR`
- GPIB连接：`GPIB::10::INSTR`

## 注意事项

1. 确保所有仪器已正确连接并上电
2. 功率计测试前需要进行归零操作
3. 修改配置文件时注意参数单位的统一（Hz, dBm等）
4. 高功率测试时注意仪器安全，不要超过最大输入功率
5. 测试过程中不要断开仪器连接
6. 测试结果文件会覆盖同名文件，请注意备份

## 故障排除

### 仪器连接失败

1. 检查仪器电源是否开启
2. 检查网络连接（对于TCPIP连接）
3. 检查VISA驱动是否正确安装
4. 使用NI MAX工具测试仪器连接

### 测试结果异常

1. 检查仪器连接线是否良好
2. 检查仪器设置是否正确
3. 确认测试参数配置是否合理
4. 查看控制台输出的错误信息

## 许可证

本项目仅供内部使用，未经授权不得外传或用于商业用途。

## 联系方式

如有问题或建议，请联系项目维护者。
