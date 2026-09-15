# -*- coding: utf-8 -*-
# 杂散测量配置
# 说明：仅保留"代码真正会读取"的参数。已删除死参数（project_name /
#       attenuator_step_db / stability_count）与未实现功能参数（cf_step_check、
#       cf_step_hz）；被架空的 min_spur_offset_hz 已重新定义并纳入 get_config()。

# 载波频率生成方式:
# "step" = 使用起始/结束/步进自动生成
# "list" = 使用 carrier_frequency_list 显式列表
carrier_frequency_mode = "step"

# 显式载波频率列表，仅 carrier_frequency_mode = "list" 时使用
carrier_frequency_list = []

# 步进式载波频率参数，单位 Hz
carrier_start_frequency_hz = 1e9
carrier_end_frequency_hz = 40e9
carrier_step_frequency_hz = 100e6

# 载波功率，单位 dBm
carrier_power_dbm = 10

# 频谱仪通用参数
reference_level_dbm = 10

# ============================================================
# 输入衰减（灵敏度第一主导项）
# ============================================================
# 物理关系：**显示底噪随输入衰减逐 dB 抬高**。衰减器在混频器之前，其损耗
#   直接加进系统噪声系数，所以 DANL(参考到输入) = DANL_mixer + 衰减 − 预放增益。
#   每多加 1 dB 衰减，显示底噪就高 1 dB。
# 约束关系：**混频器电平 = 输入信号电平 − 衰减**（预放另计）。载波 10 dBm 时：
#     衰减 40 dB -> 混频器 −30 dBm -> 底噪中位数约 −60 dBm -> 选峰门限 −54 dBm（旧值）
#     衰减 30 dB -> 混频器 −20 dBm -> 底噪中位数约 −70 dBm -> 选峰门限 −64 dBm
#     衰减 25 dB -> 混频器 −15 dBm -> 底噪中位数约 −75 dBm -> 选峰门限 −69 dBm（当前）
#     衰减 20 dB -> 混频器 −10 dBm -> 底噪中位数约 −80 dBm -> 选峰门限 −74 dBm
# 这里的 25 dB 是**全局缺省**；各段可用 input_att_db 覆盖（见下方近/远段注释）。
# 逐段取值的两条边界：
#   ① 混频器电平 = 载波 − 衰减，不宜高于 −10 dBm（过载 / 压缩风险）
#   ② 底噪要留在显示下限之上：参考电平 10 dBm + 10 dB/div × 10 div = −90 dBm，
#      底噪触及该值时迹线会触底，门限就退化成"屏幕下限"而非真实噪声
# 最终取值：near_10MHz 35 dB / near_100MHz 25 dB / far_1GHz 20 dB，
#   分段底噪都落在 −80 ~ −85 dBm 附近（旧值 40 dB 时是 −60 ~ −80 dBm）。
# 注意：预放本次不启用 —— 开预放会把混频器电平抬高预放增益，载波在段内时
#   必须把衰减相应加回，净收益（约 13 dB）不如直接降衰减。
# 注意：参考电平 10 dBm + 10 dB/div × 10 div -> 屏幕下限 −90 dBm。若继续下调
#   衰减使底噪逼近或越过 −90 dBm，会被显示范围截断（代码会打印"疑似触底"告警）。
attenuation_db = 25

input_coupling = "DC"
sa_settling_time_s = 0.5

# 内置预放（本次不启用）。
# 开启会把混频器电平抬高预放增益，载波在段内时必须同步提高输入衰减，
# 故净灵敏度收益有限（约 13 dB），不如直接把衰减降到 25 dB（+15 dB）。
# 段级可用 "preamp" 键覆盖。
preamp = False
preamp_band = None   # "LOW" / "FULL"；None 表示沿用仪器当前波段

# 频率边界（单一口径）：频谱仪可用频率范围的下限 / 上限。
# 主要用于远载波段裁剪（段下边缘 >= min、段上边缘 <= max）。
# 谐波不测绘，仅按 harmonic_exclusion 频率窗剔除候选。
# 载波最高测到 40 GHz，故上限取仪器上限 40 GHz。
min_frequency_hz = 9e3
max_frequency_hz = 40e9

# ============================================================
# 分段扫描定义
# ============================================================
# 思路：速度不是核心，全面覆盖是核心。
# 近载波用窄 RBW 保证灵敏度；远载波用宽 RBW 覆盖范围。
# 每段独立配置 SPAN / RBW / VBW / MAXH 扫描次数。

# 近载波段：以载波为中心，两侧对称搜索
#
# 每段可选覆盖项（缺省/None 表示沿用上面的全局值）：
#   input_att_db   本段输入衰减（dB）—— 载波在段内时必须按"混频器电平 = 载波 − 衰减"定
#   ref_level_dbm  本段参考电平（dBm）
#   sweep_points   本段扫描点数 —— 不设则用仪器 Preset 默认（是德 X 系列 = 1001）
#                  必要时显式设置并读回校验，避免设置被静默拒绝
near_carrier_segments = [
    # 10 MHz SPAN：覆盖 ±5 MHz，RBW 100 Hz，用于捕捉近载波窄杂散
    {
        "name": "near_10MHz",
        "span_hz": 10e6,
        "rbw_hz": 100,
        "vbw_hz": 300,
        "sweep_count": 3,
        "trace_mode": "MAXH",
        "detector": "POS",
        "sweep_points": None,   # 1001 点 / 10 MHz => 10 kHz 频率量化，待需要时收紧
        # 门限基准（POS/MAXH 迹线中位数）∝ RBW：RBW 100 Hz 比 1 GHz 段的 10 kHz 低 20 dB。
        # 若沿用 25 dB 衰减，迹线中位数会落到约 −95 dBm —— 越过参考电平 10 dBm +
        # 10 dB/div × 10 div 给出的显示下限 −90 dBm，迹线触底，门限退化成"屏幕下限"
        # 而不是真实噪声。故本段取 35 dB：迹线中位数 ≈ −85 dBm（距显示下限 5 dB），
        # 混频器电平 = 10 − 35 = −25 dBm，余量充裕。
        # （真实平均底噪比它再低约 10 dB，即 −95 dBm —— 已低于常规显示下限，
        #   由 noise_floor_report 单独压低参考电平后用 AVER 迹线测。）
        "input_att_db": 35,
    },
    # 100 MHz SPAN：覆盖 ±50 MHz，RBW 1 kHz
    {
        "name": "near_100MHz",
        "span_hz": 100e6,
        "rbw_hz": 1e3,
        "vbw_hz": 3e3,
        "sweep_count": 3,
        "trace_mode": "MAXH",
        "detector": "POS",
        "sweep_points": None,
        "input_att_db": None,   # 用全局 25 dB；迹线中位数 ≈ −85 dBm（距显示下限 5 dB）
    },
]

# 远载波段：以载波为中心，向两侧各扩展 coverage_hz/2，按 span_hz 切分。
# 实际段数 = floor(coverage_hz / span_hz)：coverage=2e9、span=1e9 时为 2 段，
#   即覆盖 [CF-1GHz, CF] 与 [CF, CF+1GHz]。
# 越界段处理：段边缘超出 [min_frequency_hz, max_frequency_hz] 时**向内夹逼**段中心，
#   使其刚好贴住可用范围（如 1 GHz 载波的下半段会被移到 9 kHz~1 GHz）；
#   只有"可用范围比一段还窄"或"夹逼后与上一段重合"时才整段跳过，并打印告警。
#   故 40 GHz 载波时高端只覆盖到 40 GHz（不存在 40~41 GHz 段）。
far_carrier_segment = {
    "name": "far_1GHz",
    "span_hz": 1e9,
    "rbw_hz": 10e3,
    "vbw_hz": 30e3,
    "sweep_count": 3,
    "trace_mode": "MAXH",
    "detector": "POS",
    "coverage_hz": 2e9,   # 以 CF 为中心，总覆盖宽度
    # 扫频模式下扫时由 span/RBW 决定、与点数基本无关，故这里把点数拉满：
    #   1001 点 / 1 GHz => 每点 1 MHz，而 RBW 仅 10 kHz => 每点约 100 个分辨率单元，
    #   POS 检波取点内最大值，噪声被额外抬 ~7 dB；频率量化也粗到 1 MHz。
    #   20001 点 / 1 GHz => 每点 50 kHz = 5 个分辨率单元，偏差降到 ~3 dB。
    "sweep_points": 20001,
    # 本段 RBW 最宽（10 kHz），底噪天然最高，是灵敏度最差的一段；混频器电平
    # 10 − 20 = −10 dBm（是德 X 系列推荐的最优电平附近），底噪 ≈ −80 dBm。
    "input_att_db": 20,
    "ref_level_dbm": None,  # None => 用全局 reference_level_dbm
}

# 谐波排除：杂散测试中不可避免地会遇到谐波分量，但谐波不是本测试的关心对象，
# 故将其从结果中**剔除**（落入任一阶谐波频率窗内的候选直接丢弃，不进入精测、不输出）。
# orders / tolerance_hz 即排除判据；不再做逐阶谐波测绘。
harmonic_exclusion = {
    "orders": [2, 3, 4, 5, 6],
    # |f - n*carrier| <= tolerance 判为谐波并剔除。
    # 注意：不宜设得过大，否则会误杀真实杂散。
    # 参考精测 span（refine_config.span_hz = 1e6），取半宽 0.5 MHz。
    "tolerance_hz": 5e5,
}

# 精测参数：对 candidate 用窄 SPAN + 窄 RBW 复测
refine_config = {
    "span_hz": 1e6,
    "rbw_hz": 100,
    "vbw_hz": 300,
    "sweep_count": 3,
    "trace_mode": "WRITE",
    "detector": "POS",
    "average_count": 3,   # 精测时重复读取次数（决定 std_db 的样本量）
}

# ============================================================
# 峰值检测参数
# ============================================================
# prominence 放低，尽量把可疑点都抓出来；后续精测和验证再过滤
peak_detection = {
    # 高于本地噪声底多少 dB 即视为"潜在杂散"。
    # 这是全流程唯一的噪声门限，两处共用：
    #   ① 段内选峰（_find_candidates）——入围门槛
    #   ② 精测后复核（_scan_segment）——保留门槛
    "noise_margin_db": 6.0,
    "peak_prominence_db": 3.0,       # 局部峰值相对于邻域的突出程度
    "min_peak_distance_hz": 1e3,     # 两个候选峰最小频率间隔（亦作全局去重容差）
    "max_peak_count_per_segment": 30,  # 每段最多保留候选，减少精测/验证负担
}

# ============================================================
# 载波附近排除（同一物理判据、两个执行时机）
# ============================================================
# 判据：距载波偏移 < 阈值的峰不视为杂散（属于载波主瓣 / 紧邻裙边 / 测量伪影）。
# 两个参数按"执行时机"分工，不互相覆盖：
#   carrier_guard_hz   —— 事前（选峰后、精测前），按候选频率剪枝，省下精测时间
#   min_spur_offset_hz —— 事后（精测后），按实测峰频终判，防止峰在精测窗口内
#                         迁移到载波附近后仍被输出
# 二者取同一数值即可保证判据一致；若规范只报"偏移 > X kHz 的杂散"，
# 把 min_spur_offset_hz 改大即可（届时它成为最终约束）。
carrier_guard_hz = 10e3
min_spur_offset_hz = 10e3

# ============================================================
# 候选杂散真伪验证
# ============================================================
validation = {
    "enable": True,

    # 源开关测试：关 RF 后若杂散仍在，判为仪器/环境杂散
    # 默认关闭，非常耗时（需要关源、重扫多个 segment）
    "source_off_check": False,

    # 源开关扫描到的杂散与候选的频率比对容差（仅 source_off_check 开启时使用）
    "ambient_freq_tolerance_hz": 100e3,

    # 衰减器阶跃测试：改衰减后 dBc 不变才是真杂散
    "attenuator_step_check": True,
    "attenuator_steps": [0, 2],   # 相对 attenuation_db 的阶跃量，只测当前值和 +2 dB
    "attenuator_dbc_tolerance_db": 2.0,

    # RBW 缩放测试：真 CW 杂散幅度不随 RBW 变化；噪声会涨
    "rbw_scaling_check": True,
    "rbw_scaling_ratios": [1, 2],
    "rbw_scaling_amplitude_tolerance_db": 2.0,

    # 重复性测试：精测阶段读取次数见 refine_config.average_count
    "stability_limit_db": 1.0,
}

# ============================================================
# 迹线初始化（防御性：隔离上一段对 MAXHold 的污染）
# ============================================================
# 切段只改 SPAN / 中心频率与 RBW，代码无法确认仪器是否顺带清掉旧迹线；而
# MAXHold 只升不降 => 一旦旧迹线被保留（例如近段含 +10 dBm 载波的那几个点），
# 就会被一路带进下一段。故每段在累积 MAXHold 之前，先用 WRITE 模式跑一次
# 覆盖旧迹线。这是"消掉不确定性"的防御性动作，成本 = 每段多一次扫描。
trace_init = {
    "prime_with_write": True,
}

# ============================================================
# 噪声底报告（真实平均底噪，与"选峰门限基准"区分）
# ============================================================
# 两个口径必须分开，否则灵敏度结论不可信：
#   ① 选峰门限基准 = POS/MAXH 迹线的中位数（即峰值噪声包络），与 POS 选峰自洽，
#      用于 _find_candidates 的入围高度（median + noise_margin_db）。
#   ② 真实平均底噪 = 独立 AVER 检波迹线的中位数，才是可以对外引用的灵敏度证据。
#      归一化到 1 Hz（dBm/Hz）后各段、各 RBW 之间才可比：
#          dBm/Hz = 底噪(dBm) − 10·log10(RBW)
noise_floor_report = {
    "enable": True,
    "detector": "AVER",        # 平均检波；POS 会把噪声峰值包络抬高若干 dB
    "sweep_count": 1,          # AVER 迹线不需要 MAXH 累积
    "normalize_to_hz": True,   # 输出 dBm/Hz 归一列
    # 测这一条 AVER 迹线时临时把参考电平压到这里，把显示下限从 −90 dBm 推到
    # −120 dBm —— 否则平均底噪（比 POS/MAXH 迹线中位数低约 10 dB）会落在屏幕外，
    # 读到的只是显示下限而不是真实噪声。
    # 安全性：此时跨度只有 1 MHz 且中心在候选杂散上，载波在跨度之外、被 RBW 滤掉，
    # 带内只有噪声，不会造成 IF/ADC 过载；且衰减已被显式置为手动（见 _configure_sa），
    # 降低参考电平不会反过来改写衰减。None = 不改参考电平。
    "ref_level_dbm": -20,
}

# 输出控制
output = {
    # **每段**保留多少个候选参与最终验证（None 表示保留全部）。
    # 注意语义：按段（每个 SPAN 一段）截断，**不是全局**。全频段扫描时若做成
    # 全局 top-N，远段的真实杂散会被近段高幅度候选整体挤掉。截断点在
    # SpuriousProcedure._scan_segment（精测之后）。
    "max_candidates_per_segment": 15,
    # 是否输出验证失败的 suspected/noise/artifact 条目
    "include_unconfirmed": True,
}


def get_config():
    """返回完整配置字典"""
    return {
        "reference_level_dbm": reference_level_dbm,
        "attenuation_db": attenuation_db,
        "input_coupling": input_coupling,
        "sa_settling_time_s": sa_settling_time_s,
        "preamp": preamp,
        "preamp_band": preamp_band,
        "min_frequency_hz": min_frequency_hz,
        "max_frequency_hz": max_frequency_hz,
        "near_carrier_segments": near_carrier_segments,
        "far_carrier_segment": far_carrier_segment,
        "harmonic_exclusion": harmonic_exclusion,
        "refine_config": refine_config,
        "peak_detection": peak_detection,
        "carrier_guard_hz": carrier_guard_hz,
        "min_spur_offset_hz": min_spur_offset_hz,
        "validation": validation,
        "trace_init": trace_init,
        "noise_floor_report": noise_floor_report,
        "output": output,
    }


def get_carrier_frequency_list():
    """生成载波频率列表"""
    if carrier_frequency_mode == "list" and carrier_frequency_list:
        return list(carrier_frequency_list)

    frequencies = []
    current = carrier_start_frequency_hz
    while current <= carrier_end_frequency_hz:
        frequencies.append(current)
        current += carrier_step_frequency_hz

    if frequencies and frequencies[-1] != carrier_end_frequency_hz:
        frequencies.append(carrier_end_frequency_hz)

    return frequencies
