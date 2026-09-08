"""
谐波数据线损补偿
- 输入1: F:/SG_test_scripts/output/谐波_10MHz_20GHz.xlsx (谐波测试数据)
- 输入2: F:/工作文档/2252.csv (射频线 S21 参数)
- 输出: F:/SG_test_scripts/output/谐波_10MHz_20GHz_线损补偿.xlsx

补偿逻辑:
  信号路径: 信号源 → DUT → 射频线 → 频谱仪
  频谱仪读到的功率已被射频线衰减, 需补偿线损恢复到 DUT 端真实功率
  - 基波补偿: P_fund_corrected = P_fund_measured - S21(fund_freq)
  - 谐波补偿: P_harm_corrected = P_harm_measured - S21(harm_freq)
  - 抑制修正: Supp_corrected = P_harm_corrected - P_fund_corrected
  其中 S21(dB) 为负值, -S21 = 线损(正值), 补偿即加上线损

  谐波频率 = 基波频率 × 谐波阶数(此处=2)
  S参数覆盖 10MHz~26.5GHz, 谐波频率最高40GHz
  超出范围的频点用末段线性外推, 并标注 extrapolated=True
"""

import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from utils.formatting import format_frequency

# ---------- 1. 解析 S 参数 CSV ----------
s_freq = []
s_s21_db = []
with open('F:/工作文档/2252.csv', 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('!') or line.startswith('BEGIN') or line.startswith('END'):
            continue
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                freq = float(parts[0])
                s21 = float(parts[1])
                s_freq.append(freq)
                s_s21_db.append(s21)
            except ValueError:
                pass

s_freq = np.array(s_freq)
s_s21_db = np.array(s_s21_db)
print(f"S参数: {len(s_freq)} 个频点, {format_frequency(s_freq[0])} ~ {format_frequency(s_freq[-1])}")


def interp_s21(freq_hz):
    """
    线性插值获取 S21(dB), 超出范围则线性外推
    返回 (s21_db, extrapolated_flag)
    """
    if freq_hz < s_freq[0]:
        # 低于最低频点: 用前两点外推
        f0, f1 = s_freq[0], s_freq[1]
        s0, s1 = s_s21_db[0], s_s21_db[1]
        slope = (s1 - s0) / (f1 - f0)
        val = s0 + slope * (freq_hz - f0)
        return val, True
    elif freq_hz > s_freq[-1]:
        # 高于最高频点: 用末两点外推
        fn1, fn = s_freq[-2], s_freq[-1]
        sn1, sn = s_s21_db[-2], s_s21_db[-1]
        slope = (sn - sn1) / (fn - fn1)
        val = sn + slope * (freq_hz - fn)
        return val, True
    else:
        # 线性插值
        val = np.interp(freq_hz, s_freq, s_s21_db)
        return val, False


# ---------- 2. 读取谐波数据 ----------
wb_src = openpyxl.load_workbook('F:/SG_test_scripts/output/谐波_10MHz_20GHz.xlsx', data_only=True)
ws_src = wb_src['详细数据']
rows = list(ws_src.iter_rows(values_only=True))
header = list(rows[0])
data = rows[1:]
print(f"谐波数据: {len(data)} 行, 基波 {min(r[2] for r in data)}~{max(r[2] for r in data)} MHz")

# ---------- 3a. 异常点修复: 用相邻两个有效点的数据线性插值 ----------
def is_bad(v):
    return (not isinstance(v, (int, float))) or abs(v) > 100

def repair_column(data, col_idx, val_idx):
    """
    对 data 中 col_idx 列(时间戳)有效、val_idx 列异常的行,
    用频域上最近的左右两个有效点对 val_idx 做线性插值。
    返回 (repaired_data, repairs) repairs 为 (row_idx, val_idx, old, new) 列表
    """
    data = [list(r) for r in data]
    repairs = []
    bad_idx = [i for i, r in enumerate(data) if is_bad(r[val_idx])]
    for i in bad_idx:
        # 向左找最近有效点
        li = i - 1
        while li >= 0 and is_bad(data[li][val_idx]):
            li -= 1
        # 向右找最近有效点
        ri = i + 1
        while ri < len(data) and is_bad(data[ri][val_idx]):
            ri += 1
        if li < 0 or ri >= len(data):
            raise ValueError(f'频点 {data[i][2]} MHz 异常值无有效邻点可插值')
        f0, v0 = data[li][2], data[li][val_idx]
        f1, v1 = data[ri][2], data[ri][val_idx]
        fi = data[i][2]
        new_val = v0 + (v1 - v0) * (fi - f0) / (f1 - f0)
        repairs.append((i + 2, data[i][2], val_idx, data[i][val_idx], new_val))
        data[i][val_idx] = new_val
    return data, repairs

data, repairs_fund = repair_column(data, 0, 4)   # fundamental_power_dbm
data, repairs_harm = repair_column(data, 0, 5)   # harmonic_power_dbm
all_repairs = repairs_fund + repairs_harm
print(f"异常点修复(邻点线性插值): {len(all_repairs)} 处")
for r in all_repairs:
    field = 'fundamental_power' if r[2] == 4 else 'harmonic_power'
    print(f"  行{r[0]} {r[1]}MHz {field}: {r[3]!r} -> {r[4]:.4f}")

interpolated_rows = set(r[0] - 2 for r in all_repairs)  # 0-based data index

# ---------- 3b. 线损补偿 ----------
results = []
extrapolated_count = 0

for idx, r in enumerate(data):
    (timestamp, freq_hz, freq_mhz, set_power, fund_power, harm_power,
     harm_supp, harm_order, sa_atten, sa_ref, sa_span, sa_rbw, sa_vbw) = r

    # 基波频率(Hz) 和 谐波频率(Hz)
    fund_freq_hz = freq_hz
    harm_freq_hz = freq_hz * harm_order

    # 插值获取 S21
    s21_fund, extrap_fund = interp_s21(fund_freq_hz)
    s21_harm, extrap_harm = interp_s21(harm_freq_hz)

    # 线损 = -S21 (正值)
    loss_fund = -s21_fund
    loss_harm = -s21_harm

    # 补偿后功率 = 测量值 + 线损 = 测量值 - S21
    fund_corrected = round(fund_power + loss_fund, 4)
    harm_corrected = round(harm_power + loss_harm, 4)
    supp_corrected = round(harm_corrected - fund_corrected, 4)
    supp_original = round(harm_power - fund_power, 4)
    supp_correction = round(loss_harm - loss_fund, 4)

    extrap_flag = extrap_fund or extrap_harm
    if extrap_flag:
        extrapolated_count += 1

    results.append({
        'timestamp': timestamp,
        'frequency_mhz': freq_mhz,
        'frequency_hz': freq_hz,
        'harmonic_order': harm_order,
        'set_power_dbm': set_power,
        'fundamental_power_measured': round(fund_power, 4) if idx in interpolated_rows else fund_power,
        'fundamental_power_corrected': fund_corrected,
        'cable_loss_fundamental_db': round(loss_fund, 4),
        'harmonic_power_measured': round(harm_power, 4) if idx in interpolated_rows else harm_power,
        'harmonic_power_corrected': harm_corrected,
        'cable_loss_harmonic_db': round(loss_harm, 4),
        'harmonic_freq_mhz': harm_freq_hz / 1e6,
        'suppression_measured_dbc': supp_original,
        'suppression_corrected_dbc': supp_corrected,
        'suppression_correction_db': supp_correction,
        'extrapolated': extrap_flag,
        'interpolated': idx in interpolated_rows,
    })

print(f"外推频点: {extrapolated_count}/{len(results)} (谐波频率超出S参数范围26.5GHz)")
print(f"插值修复频点: {len(interpolated_rows)}/{len(results)}")

# ---------- 4. 写入新 xlsx ----------
out_path = 'F:/SG_test_scripts/output/谐波_10MHz_20GHz_线损补偿.xlsx'
wb_out = openpyxl.Workbook()

# Sheet 1: 补偿后详细数据
ws1 = wb_out.active
ws1.title = '线损补偿'

headers = [
    'timestamp', 'frequency_mhz', 'frequency_hz', 'harmonic_order',
    'set_power_dbm',
    'fundamental_power_measured', 'fundamental_power_corrected', 'cable_loss_fundamental_db',
    'harmonic_power_measured', 'harmonic_power_corrected', 'cable_loss_harmonic_db',
    'harmonic_freq_mhz',
    'suppression_measured_dbc', 'suppression_corrected_dbc', 'suppression_correction_db',
    'extrapolated', 'interpolated',
]
ws1.append(headers)

# 表头样式
header_font = Font(bold=True, color='FFFFFF')
header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)
for col in range(1, len(headers) + 1):
    cell = ws1.cell(row=1, column=col)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center')
    cell.border = thin_border

# 数据行
extrap_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
interp_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
for i, r in enumerate(results, start=2):
    row_data = [
        r['timestamp'], r['frequency_mhz'], r['frequency_hz'], r['harmonic_order'],
        r['set_power_dbm'],
        r['fundamental_power_measured'], r['fundamental_power_corrected'], r['cable_loss_fundamental_db'],
        r['harmonic_power_measured'], r['harmonic_power_corrected'], r['cable_loss_harmonic_db'],
        r['harmonic_freq_mhz'],
        r['suppression_measured_dbc'], r['suppression_corrected_dbc'], r['suppression_correction_db'],
        'YES' if r['extrapolated'] else '',
        'INTERP' if r['interpolated'] else '',
    ]
    for col, val in enumerate(row_data, start=1):
        cell = ws1.cell(row=i, column=col, value=val)
        cell.border = thin_border
        if col > 1:
            cell.alignment = Alignment(horizontal='center')
        if r['interpolated']:
            cell.fill = interp_fill
        elif r['extrapolated']:
            cell.fill = extrap_fill

# 列宽
col_widths = [20, 14, 16, 10, 10, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 12, 10]
for i, w in enumerate(col_widths, start=1):
    ws1.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

# 冻结首行
ws1.freeze_panes = 'A2'

# ---------- Sheet 2: 汇总统计 ----------
ws2 = wb_out.create_sheet('汇总统计')

# 统计指标 (全部频点, 异常值已插值修复)
measured_supp = [r['suppression_measured_dbc'] for r in results]
corrected_supp = [r['suppression_corrected_dbc'] for r in results]
loss_fund_vals = [r['cable_loss_fundamental_db'] for r in results]
loss_harm_vals = [r['cable_loss_harmonic_db'] for r in results]

stats = [
    ['指标', '补偿前', '补偿后', '变化量'],
    ['基波线损范围(dB)', '', f'{min(loss_fund_vals):.4f} ~ {max(loss_fund_vals):.4f}', ''],
    ['谐波线损范围(dB)', '', f'{min(loss_harm_vals):.4f} ~ {max(loss_harm_vals):.4f}', ''],
    ['抑制最大值(dBc)', f'{max(measured_supp):.4f}', f'{max(corrected_supp):.4f}',
     f'{max(corrected_supp) - max(measured_supp):.4f}'],
    ['抑制最小值(dBc)', f'{min(measured_supp):.4f}', f'{min(corrected_supp):.4f}',
     f'{min(corrected_supp) - min(measured_supp):.4f}'],
    ['抑制平均值(dBc)', f'{np.mean(measured_supp):.4f}', f'{np.mean(corrected_supp):.4f}',
     f'{np.mean(corrected_supp) - np.mean(measured_supp):.4f}'],
    ['抑制中位数(dBc)', f'{np.median(measured_supp):.4f}', f'{np.median(corrected_supp):.4f}',
     f'{np.median(corrected_supp) - np.median(measured_supp):.4f}'],
    ['抑制标准差(dB)', f'{np.std(measured_supp):.4f}', f'{np.std(corrected_supp):.4f}', ''],
    ['', '', '', ''],
    ['总频点数', str(len(results)), '', ''],
    [f'插值修复频点数(原始溢出)', str(len(interpolated_rows)), '', ''],
    ['外推频点数(谐波>26.5GHz)', str(extrapolated_count), '', ''],
    ['S参数覆盖范围', '10MHz ~ 26500MHz', '', ''],
    ['基波频率范围', '10MHz ~ 20000MHz', '', ''],
    ['谐波频率范围', '20MHz ~ 40000MHz', '', ''],
    ['补偿说明', '补偿后功率 = 测量功率 + 线损; 抑制修正 = 谐波线损 - 基波线损', '', ''],
    ['插值说明', '原始功率溢出频点已用相邻两个有效频点线性插值修复, 绿色行已标注', '', ''],
    ['外推说明', '谐波频率>26.5GHz时S21线性外推, 标黄行已标注', '', ''],
]

for row_data in stats:
    ws2.append(row_data)

for col in range(1, 5):
    cell = ws2.cell(row=1, column=col)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center')

ws2.column_dimensions['A'].width = 28
ws2.column_dimensions['B'].width = 24
ws2.column_dimensions['C'].width = 24
ws2.column_dimensions['D'].width = 20

wb_out.save(out_path)
print(f"\n输出文件: {out_path}")
print(f"\n=== 补偿前后对比 (前5行 + 后5行) ===")
print(f"{'Freq(MHz)':>10} | {'Fund_meas':>12} | {'Fund_corr':>12} | {'Loss_f':>8} | "
      f"{'Harm_meas':>12} | {'Harm_corr':>12} | {'Loss_h':>8} | "
      f"{'Supp_meas':>12} | {'Supp_corr':>12} | {'Flags':>10}")
print("-" * 130)
for r in results[:5] + ['...'] + results[-5:]:
    if r == '...':
        print('  ...')
        continue
    fm = f"{r['fundamental_power_measured']:.4f}" if isinstance(r['fundamental_power_measured'], (int, float)) else str(r['fundamental_power_measured'])
    fc = f"{r['fundamental_power_corrected']:.4f}" if r['fundamental_power_corrected'] is not None else 'N/A'
    hm = f"{r['harmonic_power_measured']:.4f}" if isinstance(r['harmonic_power_measured'], (int, float)) else str(r['harmonic_power_measured'])
    hc = f"{r['harmonic_power_corrected']:.4f}" if r['harmonic_power_corrected'] is not None else 'N/A'
    sm = f"{r['suppression_measured_dbc']:.4f}" if r['suppression_measured_dbc'] is not None else 'N/A'
    sc = f"{r['suppression_corrected_dbc']:.4f}" if r['suppression_corrected_dbc'] is not None else 'N/A'
    flags = []
    if r['interpolated']:
        flags.append('INTERP')
    if r['extrapolated']:
        flags.append('EXTRAP')
    print(f"{r['frequency_mhz']:>10} | {fm:>12} | {fc:>12} | {r['cable_loss_fundamental_db']:>8.4f} | "
          f"{hm:>12} | {hc:>12} | {r['cable_loss_harmonic_db']:>8.4f} | "
          f"{sm:>12} | {sc:>12} | {','.join(flags):>10}")
