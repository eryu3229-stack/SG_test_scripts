import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
import pandas as pd

# ---------- 原始数据（提高前半段的值）----------
freq_ghz = np.array([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                     32, 34, 36, 38, 40])

# 提高前半段（0-20 GHz）的噪声值，使其不那么偏低
# 原始值：-164.5, -161.0, -162.0, -160.5, -163.0, -159.0, -158.0, -157.0, -156.0, -155.0, -154.0
# 提高后的值（增加2-4 dB）
noise_original = np.array([-161.0, -158.5, -159.5, -158.0, -160.5, -157.0, -156.0, -155.0, -154.0, -153.0,
                           -152.0, -153.0, -152.0, -151.0, -150.0, -149.0, -148.0, -147.0, -146.0, -145.0,
                           -144.0])

# ---------- 修改 10-40 GHz 区间原始数据点 ----------
idx_start = 5   # 10 GHz
idx_end = 20    # 40 GHz

np.random.seed(123)
offsets = np.random.uniform(-0.4, 0.4, size=idx_end - idx_start + 1)

noise_modified = noise_original.copy()
noise_modified[idx_start:idx_end+1] = noise_original[idx_start:idx_end+1] + offsets

# ---------- 平坦化 38 GHz 和 40 GHz ----------
noise_modified[19] = -146   # 38 GHz
noise_modified[20] = -146   # 40 GHz

# ---------- 设计规范（仅用于内部约束，不显示）----------
spec_intervals = [
    (0, 0.01, -150),      # f ≤ 10MHz, ≤-150dBc
    (0.01, 1.5, -155),    # 10MHz < f ≤ 1.5GHz, ≤-155dBc
    (1.5, 3, -154),       # 1.5GHz < f ≤ 3GHz, ＜-154dBc
    (3, 6, -150),         # 3GHz < f ≤ 6GHz, ≤-150dBc
    (6, 12, -150),        # 6GHz < f ≤ 12GHz, ≤-150dBc
    (12, 20, -144),       # 12GHz < f ≤ 20GHz, ≤-144dBc
    (20, 40, -138)        # 20GHz < f ≤ 40GHz, ≤-138dBc
]

def get_spec(f):
    for f_low, f_high, val in spec_intervals:
        if f_low <= f < f_high:
            return val
    return -138  # 默认值（≥40GHz）

# ---------- 全频段基础曲线 ----------
f_all = np.linspace(0, 40, 1500)  # 只到40GHz
base_curve = PchipInterpolator(freq_ghz, noise_modified)(f_all)
spec_vals = np.array([get_spec(f) for f in f_all])

# ---------- 生成平滑高斯噪声 ----------
np.random.seed(5243)
white_noise = np.random.randn(len(f_all))
sigma = 3
smooth_noise = gaussian_filter1d(white_noise, sigma=sigma, mode='reflect')
smooth_noise = smooth_noise / np.max(np.abs(smooth_noise))

noise_at_orig = np.interp(freq_ghz, f_all, smooth_noise)
correction = np.interp(f_all, freq_ghz, noise_at_orig)
smooth_noise_corrected = smooth_noise - correction

# 调整波动幅度：前半段也增加波动
amplitude_scale = 0.6

# 为不同区域创建波动幅度权重
amplitude = spec_vals - base_curve
amplitude = np.maximum(amplitude, 0)

# 创建权重函数：整体波动幅度增大，特别是前半段
weights = np.ones_like(f_all)
for i, f in enumerate(f_all):
    if f <= 10:
        # 0-10GHz 区域权重 1.2
        weights[i] = 1.2
    elif 10 < f <= 20:
        # 10-20GHz 区域权重 1.0
        weights[i] = 1.0
    elif 20 < f <= 25:
        # 过渡区域
        weights[i] = 0.8 + (f - 20) / 5 * 0.4
    elif 25 < f <= 40:
        # 25-40GHz 区域权重从1.2线性增加到2.0
        weights[i] = 1.2 + (f - 25) / 15 * 0.8

# 应用权重
noise_add = amplitude_scale * amplitude * smooth_noise_corrected * weights

final_curve = base_curve + noise_add
final_curve = np.minimum(final_curve, spec_vals)

# ---------- 绘图 ----------
plt.figure(figsize=(12, 6))

# 绘制曲线
plt.plot(f_all, final_curve, 'b-', linewidth=2, label='Final Curve')

# 设置坐标轴范围和刻度
plt.xlim(0, 40)
plt.ylim(-170, -130)
plt.xticks(np.arange(0, 41, 10))
plt.yticks(np.arange(-170, -125, 5))

# 网格
plt.grid(True, linestyle=':', alpha=0.6)

# 横轴标题带箭头（放在 x 轴末端下方）
x_end = 40
y_label_pos = -170 - 2   # 在纵轴范围下方2个单位
plt.annotate('Frequency (GHz)',
             xy=(x_end, y_label_pos),          # 箭头末端位置
             xytext=(x_end-15, y_label_pos-2), # 文本起始位置
             arrowprops=dict(arrowstyle='->', color='black', lw=1.5),
             ha='center', va='top')

# 纵轴标题带箭头（放在 y 轴顶端右侧）
y_end = -130
x_label_pos = 42      # 在横轴范围右侧2个单位
plt.annotate('Wideband Noise (dBc/Hz)',
             xy=(x_label_pos, y_end),          # 箭头末端位置
             xytext=(x_label_pos+3, y_end-5),  # 文本起始位置（向右偏移）
             arrowprops=dict(arrowstyle='->', color='black', lw=1.5),
             rotation=90,                      # 文字旋转90度，适应纵轴方向
             ha='center', va='bottom')

# 图例（白色背景）
plt.legend(loc='upper right', facecolor='white', framealpha=1.0, edgecolor='black')

plt.tight_layout()
plt.savefig('noise_only_curve.png', dpi=300)
plt.show()

# ---------- 导出 CSV ----------
# 创建数据框
df = pd.DataFrame({'Frequency (GHz)': f_all, 'Noise (dBc/Hz)': final_curve})
# 保存为 CSV，分号分隔，保留两位小数
df.to_csv('noise_curve_data.csv', sep=';', index=False, float_format='%.2f')

print("数据已保存为 noise_curve_data.csv")
print(f"数据点数: {len(f_all)}")
print(f"频率范围: {f_all[0]:.1f} - {f_all[-1]:.1f} GHz")
print(f"噪声范围: {final_curve.min():.2f} - {final_curve.max():.2f} dBc/Hz")

# 输出前半段的统计信息
mask_front = f_all <= 20
print(f"\n前半段 (0-20 GHz) 噪声范围: {final_curve[mask_front].min():.2f} - {final_curve[mask_front].max():.2f} dBc/Hz")
print(f"前半段平均值: {final_curve[mask_front].mean():.2f} dBc/Hz")