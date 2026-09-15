# 项目长期记忆 — SG_test_scripts

## 项目性质
信号源 / 频谱仪 / 功率计自动化测试脚本集。目录：`instruments/`（驱动）、`procedures/`（流程）、`configs/`（配置）、`run_scripts/`（入口）、`utils/`、`output/`（结果）。

## 仪器驱动多品牌 SCPI 适配（2026-09-15 定案并落地）
- **架构**：门面类 + 品牌后端类。门面（`spectrum_analyzer.py`）方法签名保持不变，品牌差异下沉到 `instruments/backends/`。现有 `procedures/`、`run_scripts/` 零改动。
- **已实现文件**：`instruments/brand.py`（`*IDN?` 品牌识别）、`instruments/spectrum_analyzer.py`（门面，`brand=` 可显式覆盖）、`instruments/backends/{sa_base,sa_rohde,sa_keysight}.py`。
- **品牌判定**：`ROHDE`/`R&S` → rohde；`KEYSIGHT`/`AGILENT` → keysight；未知 → `GenericSpectrumAnalyzer` 通用子集 + 告警不中断。
- **关键指令差异**：参考电平 `DISP:TRAC:Y:RLEV`(R&S) vs `DISP:WIND:TRAC:Y:RLEV`(KS)；衰减 `INP:ATT` vs `POW:ATT`；预放 `INP:GAIN:VAL 15/30`(R&S) vs `POW:GAIN:BAND LOW/FULL`(KS)；峰值搜索 `CALC:MARK<n>:MAX:PEAK`(R&S) vs `CALC:MARK<n>:MAX`(KS)；迹线 `DISP:TRAC<n>:MODE` vs `TRAC<n>:MODE`；检波器 `SENS:DET<n>:FUNC`(R&S 无 NORMal) vs `DET:TRAC<n>`(KS 无 APEak)。
- **范围**：**只改"测量仪器"**。频谱仪已完成多品牌化；信号源是**被测件（DUT）**、现场只接自家机型，**明确不做**品牌后端拆分（2026-09-15 用户定案）；功率计按自备测量仪器处理。
- **理由**：品牌差异是流程级的（归零时序、扫描同步、预放取值、参考电平路径），纯命令字典处理不了。

## 输出规范：只出 CSV + 统一字段（2026-09-15 定案并落地）
- **只出 CSV，不再生成任何 xlsx**。理由：xlsx 是 zip 容器、尾部 EOCD 必须最后写 → 无法真流式、半成品打不开；CSV 可逐行 append+flush，断电安全。数据库（SQLite）留待后续，届时 CSV 退化为导出格式。
- **基类 `BaseTestProcedure` 已完全不依赖 pandas/openpyxl**。可用方法：`save_results_to_csv`、`save_results`（仅 CSV）、`start_csv_stream`、`finish_csv`、`derive_run_id`、`bool_str`、`print_summary`。**已删除**：`save_results_to_excel`、`finish_xlsx`、`CsvStreamer.to_xlsx`。
- **统一字段三段式**（列序固定）：
  1. A 区（所有源一致，前 7 列）：`run_id, test_type, carrier_hz, set_power_dbm, measured_power_dbm, delta_db, delta_ref`
  2. B 区（仅用频谱仪的源，`sa_` 前缀）：`sa_ref_level_dbm, sa_input_att_db, sa_att_mode, sa_span_hz, sa_rbw_hz, sa_vbw_hz, sa_noise_floor_dbm`
  3. C 区（源专有列）
  4. 末 3 列（所有源一致）：`status, note, timestamp`
- **语义铁律**：
  - `delta_db = (measured_power_dbm + ext_att_db) − 参考值`；`delta_ref` 指明参考值来源：`"set"`（相对设定功率）/ `"carrier"`（相对载波实测）/ `"fundamental"`（相对基波实测，谐波/分谐波用）。
  - `carrier_hz` = 主信号/测点频率（唯一口径，旧 `frequency`/`frequency_hz`/`carrier_frequency_hz` 全废）；`spurious_freq_hz` = 杂散频点。
  - `ext_att_db` = **外接物理衰减器标称值**，由人告知、**从不下发仪器**，仅用于折算读数；未使用则留空。`sa_input_att_db` = 频谱仪**内部**程控衰减（真下发仪器）。
  - 布尔列写小写 `true`/`false`（用 `bool_str`），None → 空串。
  - `status` 取值按流程自定：杂散 `OK/SUSPECT/SKIP`；功率类 `OK/SATURATED/OVERLOAD/LIMIT/MEAS_FAIL`。
  - utf-8-sig、无中文表头、缺失值留空、`timestamp` 末列。
- **各源列数**：杂散 22 / 小信号 19 / 谐波 21 / 分谐波 20 / 功率扫描 12 / 最大功率 & 低频最大功率 `SUMMARY 13 + DETAIL 12`（低频版另加 6 个 `sa_*`）。
- **`power_sweep_base` 双 CSV**：`<tag>_detail_<ts>.csv`（逐点流式）+ `<tag>_summary_<ts>.csv`（结束时一次写）。子类通过 `self.sa_context` 字典把 `sa_*` 条件合并进每行；覆写 `SUMMARY_FIELDNAMES`/`DETAIL_FIELDNAMES` 即可加列。
- **杂散不做谐波标记/测绘**：落入 `harmonic_exclusion`（`orders` + `tolerance_hz=5e5`）频率窗的候选在精测前直接剔除，不输出（用户明确不关心谐波）。
- 不改动：`harmonic_cable_loss_compensation.py`（按列位置读旧谐波输出、硬编码固定 xlsx，一次性历史脚本）、`wideband.py`（独立绘图脚本）。

## 环境：正式运行环境（2026-09-15 探明）
- **正式解释器**：`F:\miniconda\envs\SG_TEST\python.exe`（conda env `SG_TEST`）。含 **pyvisa 1.16.2 / pyvisa-py / numpy 2.4.6 / pandas 3.0.3 / openpyxl**；无 scipy / matplotlib / pyserial。
- **NI-VISA 已安装**：`C:\Windows\system32\visa32.dll` → `pyvisa.ResourceManager()` 默认走 NI-VISA，可真实枚举并连仪器。
- **验证/真实运行一律用上述解释器**；托管 Python（`.workbuddy/binaries/python`）、`F:\miniconda\python.exe`(base)、`F:\python\python.exe` **都没有任何依赖**，只能做零依赖的 AST 语法检查。
- **仪器资源（2026-09-15 枚举，共 7 个）**：
  - `TCPIP0::K-N9030B-89385.local::hislip0::INSTR` / `::inst0::INSTR` / `TCPIP0::169.254.212.36::hislip0::INSTR` —— **同一台 Keysight N9030B（MY60089385, A.36.22）的三条别名路由，在线可查**。
  - `TCPIP0::FSW67-101914::inst0::INSTR`（R&S FSW67）与 `TCPIP0::169.254.1.45::inst0::INSTR` —— 枚举得到但 `*IDN?` **无响应**（大概率未开机/不在网）。
  - `ASRL4::INSTR` / `ASRL7::INSTR` —— 串口，波特率未知，**未探测**（可能是功率计/信号源）。
- **安全红线**：涉及仪器状态变更（`enable_output`、`set_power`、RF 开断、衰减切换）的操作属高风险，**必须用户明确确认后才能执行**。只读查询（`*IDN?`、`list_resources`）一般可执行，**但用户正在跑测量时一律不许碰**（第二会话与在跑脚本争抢 VISA 会话，会导致超时、报错甚至干扰采集）—— 需用户明确说"跑完了"再动。`run_scripts/*.py` 含 `input()` 交互，非交互 shell 无法直接驱动，需 wrapper 或用户自己跑。
- **真实环境已验证通过（2026-09-15）**：23 个模块真实 import 零失败；杂散端到端（真实 numpy）输出无谐波/无载波保护带内频点；功率类双 CSV 正常；运行时逐行键集合 == FIELDNAMES（无差异）。

## 环境注意事项
- Bash 工具在本机是 Git Bash 精简版：无 `ls`/`tail`/`wc`/`find`/`dirname`，请用 Read/Glob/Grep 工具替代；`python -c` 直接调用绝对路径即可。
- 本机 Python 时间戳与提示的 current_time 可能不一致（以脚本输出为准）。
- 查找本机解释器可用 `py -0p` 与 `F:/miniconda/Scripts/conda.exe env list`。

## 手册获取经验
- R&S 手册可直接从厂商 CDN 下载：`https://scdn.rohde-schwarz.com/ur/pws/dl_downloads/pdm/cl_manuals/user_manual/<docid>/<文件名>.pdf`。
- WorkBuddy 资料库（`/space/d/{id}`，kind=drive）的预签名下载链接可能返回 403，此时改从厂商官网找同文档更可靠。
