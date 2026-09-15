# 版本更新文档 — SG_test_scripts

> 本文件按版本记录**实质性**变更（架构、接口、输出契约、测量参数、缺陷修复）。
> 纯格式调整、注释微调不单列。日期以仓库提交记录与项目工作日志为准。

---

## 版本一览

| 版本 | 日期 | 对应提交 | 主题 |
|------|------|----------|------|
| v1.0 | 2026-03-28 | `e39194f` | Initial commit：5 类测试完整实现，频谱仪 + 功率计双仪器 |
| v2.0 | 2026-06-23 | `c354595` | 抽取 `PowerSweepBaseProcedure`，消除约 250 行重复；多项指令/键名修复 |
| streaming | 2026-09-08 ~ 09-14 | `c6c2b64` … `21a3779` | 流式 CSV 落地；杂散流程缺陷修复；低频段最大功率 |
| **v2.1** | **2026-09-15** | `c8e36e0` + 未提交工作区 | **多品牌频谱仪 / 只出 CSV + 统一字段 / 杂散修复 / 灵敏度改造** |

---

## v2.1（2026-09-15）

本版为一次「大更新」，四个主题。前三个主题在提交 `c8e36e0`「大更新」中落地；
第四个主题（灵敏度改造）在提交之后的工作区中完成，**尚未提交**。

### 一、频谱仪多品牌 SCPI 适配

**问题**：原 `spectrum_analyzer.py` 把罗德 R&S 与是德 Keysight 的 SCPI 指令混在一处，
部分指令在另一品牌上报 `undefined header`（如 `POW:ATT` 在 N9030B 上）。

**方案**：门面 + 品牌后端。品牌差异全部下沉到 `instruments/backends/`，
门面方法签名保持与原单品牌版**完全一致**，`procedures/`、`run_scripts/` 零改动。

- 新增 `instruments/brand.py`：解析 `*IDN?` 判定品牌。
- 新增 `instruments/backends/`：
  - `sa_base.py` — 公共基类 + 未知品牌通用回退（`GenericSpectrumAnalyzer`）
  - `sa_rohde.py` — 罗德 R&S（FSWP / FSW）
  - `sa_keysight.py` — 是德 Keysight（X 系列 SA）
- `instruments/spectrum_analyzer.py` 改为门面，构造参数 `brand=` 可显式覆盖自动识别。
- 品牌判定：`ROHDE` / `R&S` → rohde；`KEYSIGHT` / `AGILENT` → keysight；
  未知 → 通用子集 + 告警，**不中断流程**。

**关键指令差异**（依据 R&S FSWP-B1 User Manual 1177.5656.02 ─ 11 与
Keysight N9060-90041 Ed.19）：

| 动作 | 罗德（FSWP/FSW） | 是德（X 系列 SA） |
|------|------------------|-------------------|
| 参考电平 | `DISP:TRAC:Y:RLEV` | `DISP:WIND:TRAC:Y:RLEV` |
| 衰减 / 自动 | `INP:ATT` / `INP:ATT:AUTO` | `POW:ATT` / `POW:ATT:AUTO` |
| 预放 | `INP:GAIN:STAT` + `INP:GAIN:VAL`(15/30 dB) | `POW:GAIN:STAT` + `POW:GAIN:BAND`(LOW/FULL) |
| 峰值搜索 | `CALC:MARK<n>:MAX:PEAK` | `CALC:MARK<n>:MAX` |
| 迹线模式 | `DISP:TRAC<n>:MODE MAXHold` | `TRAC<n>:MODE MAXHold` |
| 检波器 | `SENS:DET<n>:FUNC POSitive` | `DET:TRAC<n> POSitive` |

**适配范围（用户定案）**：**只适配「测量仪器」**。
信号源是**被测件（DUT）**、现场只接自家机型，**明确不做**品牌后端拆分；
功率计按自备测量仪器处理。

### 二、输出格式统一：只出 CSV + 统一字段

**背景**：原项目输出列名三套并存、互不兼容，同名列语义还相反 ——
`frequency_hz` 在杂散里指「杂散频点」，在小信号/谐波/分谐波里指「测点频率」，
直接合并分析会得出错误结论。

**决定 1：只出 CSV，不再生成任何 xlsx。**
理由：xlsx 是 zip 容器、尾部 EOCD 必须最后写 → 无法真流式、半成品打不开；
CSV 可逐行 append + flush，断电安全。数据库（SQLite）留待后续。

**决定 2：统一字段规范（列序固定，三段式）**

| 区 | 内容 | 列 |
|----|------|----|
| A 区 | 所有源一致，前 7 列 | `run_id, test_type, carrier_hz, set_power_dbm, measured_power_dbm, delta_db, delta_ref` |
| B 区 | 仅用频谱仪的源，`sa_` 前缀 | `sa_ref_level_dbm, sa_input_att_db, sa_att_mode, sa_span_hz, sa_rbw_hz, sa_vbw_hz, sa_noise_floor_dbm`（杂散另加两列底噪口径，见第四节） |
| C 区 | 源专有列 | 各源不同 |
| 末 3 列 | 所有源一致 | `status, note, timestamp` |

**语义铁律**

- `delta_db = (measured_power_dbm + ext_att_db) − 参考值`；
  `delta_ref` 指明参考值来源：`"set"`（设定功率）/ `"carrier"`（载波实测）/
  `"fundamental"`（基波实测，谐波/分谐波用）。
- `carrier_hz` = 主信号/测点频率，**唯一口径**；旧 `frequency` / `frequency_hz` /
  `carrier_frequency_hz` 全部废弃。`spurious_freq_hz` = 杂散频点。
- `ext_att_db` = **外接物理衰减器标称值**，由人告知、**从不下发仪器**，仅用于折算读数，
  未使用则留空。`sa_input_att_db` = 频谱仪**内部**程控衰减（真下发仪器）。
- 布尔列写小写 `true` / `false`（`bool_str`）；`None` → 空串。
- `status` 取值按流程自定：杂散 `OK / SUSPECT / SKIP`；
  功率类 `OK / SATURATED / OVERLOAD / LIMIT / MEAS_FAIL`。
- 编码 `utf-8-sig`、无中文表头、缺失值留空、`timestamp` 末列。

**各源列数与关键变化**

| 源 | 列数 | 输出文件 | 说明 |
|----|------|----------|------|
| 杂散 `spurious` | **24** | `<tag>_stream_<ts>.csv` | B 区多两列底噪口径 |
| 小信号 `small_signal` | 19 | `<tag>_stream_<ts>.csv` | 删 `average_count`，增 `sa_att_mode`、`sa_preamp_on` |
| 谐波 `harmonic` | 21 | `<tag>_stream_<ts>.csv` | 改**长表**：加 `harmonic_order` 单列 |
| 分谐波 `subharmonic` | 20 | `<tag>_stream_<ts>.csv` | 改**长表**：加 `subharmonic_order` 单列 |
| 功率扫描 `power_sweep` | 12 | `<tag>_<ts>.csv` | 增 `ext_att_db`、`compensated_power_dbm` |
| 最大功率 `max_power` | SUMMARY 13 + DETAIL 12 | `<tag>_summary_<ts>.csv` + `<tag>_detail_<ts>.csv` | 双 CSV |
| 低频最大功率 `low_freq_max_power` | SUMMARY 13 + DETAIL 12（另加 6 个 `sa_*`） | 同上 | 继承 `PowerSweepBaseProcedure`，覆写字段加 `sa_*` |

**涉及的实现改动**

- `procedures/base_test_procedure.py`：删 `save_results_to_excel` / `finish_xlsx`；
  新增 `derive_run_id`（**此前被引用但根本不存在**，潜伏缺陷已补）、`finish_csv`、`bool_str`；
  `save_results` 收敛为仅 CSV；`print_summary` 去 pandas 化 → **基类已完全不依赖 pandas/openpyxl**。
- `utils/csv_streamer.py`：删 `to_xlsx`，保留逐行 append + flush。
- `procedures/power_sweep_base.py`：整文件重写为双 CSV（`DETAIL_FIELDNAMES` 流式逐点 +
  `SUMMARY_FIELDNAMES` 结束时一次写）；新增 `sa_context` 机制让子类把 `sa_*` 条件合并进每行；
  `_finite()` 过滤 `None / -inf / nan`；删 openpyxl / pandas 全部路径。
- 7 个入口 `run_scripts/*.py`：输出路径改 `.csv`，结尾统一 `finish_csv()`；
  `power_sweep.py` 补上此前**从未调用**的 `start_csv_stream`。
- `run_scripts/gui.py`：`_save_results` 改 CSV（去 pandas），新增 `_open_csv` 并接入 5 处 `_exec_*`。

### 三、杂散流程缺陷修复

针对 `configs/spurious_config.py` 与 `procedures/spurious_procedure.py` 的通盘清点：

1. **删除死参数**：`project_name`、`validation.attenuator_step_db`、`validation.stability_count`
   （写了但代码从不读），以及未实现的功能参数 `validation.cf_step_check` / `cf_step_hz`。
2. **修复「被架空」参数**：`min_spur_offset_hz` 此前**根本没被 `get_config()` 导出**，
   代码永远走 `.get(..., 5e3)` 默认值。已导出，并重新定义为**事后**按实测峰频的终判；
   `carrier_guard_hz` 保留为**事前**按候选频率剪枝 —— 两者分工，不互相覆盖，值统一 10 kHz。
3. **语义漂移修正**：`cf_step_freq_tolerance_hz` → `ambient_freq_tolerance_hz`。
4. **噪声门限统一为唯一一个 6 dB**（`peak_detection.noise_margin_db`），
   删除重复的 `validation.noise_floor_reliable_margin_db`（原 10 dB）。
5. **频率口径统一**：`max_frequency_hz` 20 GHz → **40 GHz**（载波最高测 40 GHz），
   同时作为远段上限与谐波上限。
6. **`_build_far_segment_centers` 重写**：边界校验由「段中心」改为「**段上下边缘**」，
   且越界段**向内夹逼**（而非整段丢弃）+ 重合去重。
   原因：只校验中心时 `center > 0` 仅等价于「下边缘 > −span/2」；
   且 40 GHz 载波原会生成 40–41 GHz 越界段。修复后 1 GHz 载波的下半段仍能覆盖 9 kHz–1 GHz。
7. **`max_candidates_per_segment` 名实不符修复**：原实现是**全局 top-N**
   （`all_candidates.sort()[:15]`），不是每段 N 个。全频段扫描时远段真实杂散会被
   近段高幅度候选整体挤掉。改为 `_scan_segment` **精测后按段截断**，主循环全局截断删除。
   连带修复：粗扫分辨率（1 GHz / 1001 点 ≈ 1 MHz）远宽于 `carrier_guard_hz`(10 kHz)，
   载波所在 bin 必然走到精测后才被丢弃 → 会白占一个「每段 top-N」名额；
   已加「精测后按实测峰频复审 guard」。
8. **修 `_scan_ambient` 的 `NameError`**：引用未定义变量 `segment_name`（函数内只有 `segment`）。
   当前 `source_off_check=False` 未触发。
9. **谐波不再测绘**：`harmonic_config` → `harmonic_exclusion`（`orders` + `tolerance_hz=5e5`）；
   删 `output.include_harmonics`；落入任一阶谐波频率窗的候选在**精测前直接剔除、不输出**
   （用户明确不关心谐波）。`_measure_harmonics` 整块删除，
   `_classify_harmonic` → `_is_harmonic_spur`（布尔过滤器）。

### 四、灵敏度改造（工作区，未提交）

**触发**：用户提出「1 GHz 远段底噪 −60 dBm 是鸡肋，测试结论几乎不可信」。

**根因（定量）**：`−60 dBm = 物理 DANL(RBW 10 kHz) ≈ −110 dBm + 输入衰减 40 dB + POS/MAXH 峰值包络偏置 ≈ +10 dB`。
**衰减占 40 dB，是第一主导项** —— 衰减器在混频器之前，其损耗直接加进系统噪声系数，
显示底噪**随输入衰减逐 dB 抬高**。

**两条取值边界**（决定每段衰减）

1. 混频器电平 = 载波 − 衰减，不宜高于 **−10 dBm**（过载 / 压缩风险）；
2. 底噪必须留在**显示下限之上**：参考电平 10 dBm + 10 dB/div × 10 div = **−90 dBm**，
   触底时迹线被截断，门限退化成「屏幕下限」而非真实噪声。

⇒ 最优衰减 ≈ 让该段底噪刚好落在 −85 dBm 附近。

**分段衰减最终取值**（旧值一律 40 dB）

| 段 | 负载波 RBW | 输入衰减 | 混频器电平 | 灵敏度净增 |
|----|-----------|----------|-----------|-----------|
| `near_10MHz`（±5 MHz） | 100 Hz | **35 dB** | −25 dBm | 0（受显示下限限制） |
| `near_100MHz`（±50 MHz） | 1 kHz | **25 dB**（全局缺省） | −15 dBm | +10 dB |
| `far_1GHz`（±1 GHz） | 10 kHz | **20 dB** | −10 dBm | +20 dB |

**两个底噪口径必须分开**（这是「结论是否可信」的关键）

- `sa_noise_floor_dbm` = POS/MAXH 迹线中位数 = **峰值噪声包络 → 选峰门限基准**
  （与 POS 选峰自洽），**不是灵敏度结论**；
- `sa_noise_floor_avg_dbm` / `sa_noise_floor_dbm_per_hz` = 独立 **AVER** 检波迹线中位数
  = **真实平均底噪**，dBm/Hz 归一（`− 10·log10(RBW)`）后才跨段可比。两者差约 +10 dB。

测 AVER 那条迹线时**临时把参考电平压到 −20 dBm**（`noise_floor_report.ref_level_dbm`），
否则平均底噪会掉到 −90 dBm 显示下限之外、读到的只是屏幕下限。
安全前提：此时跨度仅 1 MHz 且中心在候选杂散上，载波被 RBW 滤掉，带内只有噪声。

**配套机制**

- **迹线初始化**（`trace_init.prime_with_write`）：每段在累积 MAXHold 之前先用 WRITE
  覆盖一次旧迹线。原因：切段只改 SPAN / 中心频率与 RBW，代码无法确认仪器是否顺带清迹线；
  而 MAXHold **只升不降** → 近段含 +10 dBm 载波的那几个点会被一路带进下一段。
- **下发后读回校验**（`read_key_settings`）：`BAND:RES?` / `BAND:VID?` / `SWE:POIN?`
  + 参考电平 + 输入衰减。控制台此前打印的**一直是请求值**，仪器静默拒绝
  （耦合冲突、越界、命令路径不对）时无从发现。不一致只告警、不中断。
  - `sa_base.query()` / `_query_float()` / `read_key_settings()`；`sa_keysight` 覆写
    返回 `DISP:WIND:TRAC:Y:RLEV?` + `POW:ATT?`；`sa_rohde` 返回 `DISP:TRAC:Y:RLEV?` + `INP:ATT?`。
  - 门面暴露 `query_raw()` / `read_key_settings()`。
- **显式断开衰减自动耦合**（`_configure_sa` 调 `set_attenuation_auto(False)`）：
  否则改参考电平时仪器可能按 Auto 规则回写衰减。
- **扫描点数**：驱动此前**从未**调用 `set_sweep_points` → 停在是德 X 系列 Preset 默认 **1001** 点。
  1 GHz span 下每点 1 MHz，而 RBW 10 kHz → 每点约 100 个分辨率单元，POS 取点内最大，
  噪声额外抬约 +7 dB。扫频模式扫时由 span/RBW 决定、**点数几乎不增加耗时**，
  故 far 段显式设 `sweep_points=20001`。（R&S 后端无 `set_sweep_points`，门面会跳过并提示。）
- **触底检测**（`_detect_floor_clipping`）：迹线触及显示下限时打印
  「⚠ 底噪疑似被显示范围截断」—— 把「仪器灵敏度差」与「显示屏截断」区分开。
- **预放本次不启用**：开预放会把混频器电平抬高预放增益，载波在段内时必须同步提高衰减，
  净收益约 13 dB < 直接降衰减的 15–20 dB。

**新增配置项**（`configs/spurious_config.py`）

- `preamp = False` / `preamp_band = None`
- `trace_init = {"prime_with_write": True}`
- `noise_floor_report = {enable, detector:"AVER", sweep_count:1, normalize_to_hz:True, ref_level_dbm:-20}`
- 段级可选覆盖：`input_att_db` / `ref_level_dbm` / `sweep_points` / `preamp` / `preamp_band`

**字段变化**：杂散 `FIELDNAMES` 22 → **24**，新增 `sa_noise_floor_avg_dbm`、`sa_noise_floor_dbm_per_hz`。

---

## 验证与测试基线

| 验证项 | 工具 | 结果 |
|--------|------|------|
| 全项目语法 | `ast.parse` / `compileall` | 通过 |
| 6 个流程的行字典键 == 各自 FIELDNAMES | AST 静态比对 | 完全相等 |
| 多品牌冒烟（R&S / Keysight / Agilent / 未知 / 显式覆盖） | 桩测试 | 5/5 通过 |
| 杂散灵敏度自检（字段 24 列、配置阶梯算术、触底检测、段级合并） | `wb_sensitivity_check.py` | ALL PASS |
| 杂散灵敏度端到端（假仪器：段级衰减真下发、读回、迹线初始化、双底噪口径） | `wb_spurious_sensitivity_e2e.py` | ALL PASS |
| 正式环境真实 import + 端到端 | `F:\miniconda\envs\SG_TEST\python.exe` | 23 模块 0 失败；无谐波/无保护带内频点 |
| 真机品牌识别 | 在线 Keysight N9030B（MY60089385, A.36.22） | 判定 `keysight` → `KeysightSpectrumAnalyzer` |

---

## 已知限制与遗留

1. **灵敏度数值来自解析模型 + 假仪器，尚未在真实 N9030B 上跑过**；
   读回查询路径 `DISP:WIND:TRAC:Y:RLEV?` / `POW:ATT?` 未在硬件上验证。
2. **结构性天花板仍在**：选峰门限坐在真实平均底噪之上约 16 dB（POS 峰值包络约 +6 dB +
   门限余量 6 dB）。降衰减只能降低绝对门限，改不了这个相对关系。
3. **全频段覆盖未决**：`far_carrier_segment.coverage_hz` 仍为 2e9 = 只覆盖 CF ±1 GHz，
   约占仪器可用频段（9 kHz–40 GHz）**5%**。
   关键推论：载波 > 2 GHz 时**次谐波 CF/2 落在扫描范围之外**，杂散流程抓不到次谐波，
   只能靠独立的 `subharmonic_test_procedure`。
4. **预放未启用**（见第四节）。
5. **R&S 后端无 `set_sweep_points`**，该段的显式点数设置在罗德仪器上会被跳过。
6. 未改动：`harmonic_cable_loss_compensation.py`（按列位置读旧谐波输出、硬编码固定 xlsx，
   一次性历史脚本）、`wideband.py`（独立绘图脚本）。

---

## 环境说明

- **正式运行环境**：`F:\miniconda\envs\SG_TEST\python.exe`（conda env `SG_TEST`）。
  含 pyvisa 1.16.2 / pyvisa-py / numpy 2.4.6 / pandas 3.0.3 / openpyxl；无 scipy / matplotlib。
  NI-VISA 已安装（`C:\Windows\system32\visa32.dll`）。
- 托管 Python（`.workbuddy/binaries/python`）、`F:\miniconda\python.exe`(base)、
  `F:\python\python.exe` **均无任何依赖**，只能做零依赖的 AST 语法检查。
- 依赖安装：`pip install pyvisa pyvisa-py pandas openpyxl numpy scipy matplotlib`
