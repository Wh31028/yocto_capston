import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({'font.family': 'serif', 'font.size': 12})

# ── CSV 로드 ──────────────────────────────────────────────────
rows = []
with open('/Users/wh31028/repos/capston/can-fota-BBB/fota_result_STmin5.csv') as f:
    for r in csv.DictReader(f):
        try:
            rows.append({
                'protocol': r['protocol'], 'loss': float(r['loss_rate_pct']),
                'size': int(r['fw_size_bytes']), 'time': float(r['total_time_sec']),
                'overhead': float(r['overhead_pct']), 'total': int(r['total_frames']),
            })
        except: pass

SIZE = 65536
SIZE_LABEL = "64KB (STmin=5ms)"
LOSS_RATES = [0.0, 0.01, 0.05, 0.1]
LOSS_LABEL = ['0%', '0.01%', '0.05%', '0.1%']
x_pos = np.arange(len(LOSS_RATES))
C_COLOR = '#1f77b4'; I_COLOR = '#d62728'; ARR_COLOR = '#e07b00'
ARROW_MIN = 0.055

def get_stats(proto, field='time'):
    means, stds = [], []
    for lr in LOSS_RATES:
        vals = [r[field] for r in rows
                if r['protocol']==proto and r['size']==SIZE and abs(r['loss']-lr)<1e-6]
        means.append(np.mean(vals) if vals else 0)
        stds.append(np.std(vals, ddof=1) if len(vals)>1 else 0)
    return np.array(means), np.array(stds)

def annotate_points(ax, xi, cv, iv, cv_std, iv_std, y_range,
                    val_fmt="{:.1f}s", pct_fmt="+{:.1f}%"):
    pct   = (iv - cv) / cv * 100 if cv > 0 else 0
    gap   = iv - cv
    mid_y = (cv + iv) / 2

    # 값 텍스트
    ax.text(xi, cv - cv_std - y_range*0.05, val_fmt.format(cv),
            ha='center', va='top', color=C_COLOR, fontsize=10, fontweight='bold')
    ax.text(xi, iv + iv_std + y_range*0.05, val_fmt.format(iv),
            ha='center', va='bottom', color=I_COLOR, fontsize=10, fontweight='bold')

    if xi < len(LOSS_RATES) - 1:
        arr_x = xi + 0.1
        txt_x = arr_x + 0.05
        ha = 'left'
    else:
        arr_x = xi - 0.1
        txt_x = arr_x - 0.05
        ha = 'right'

    if gap / y_range >= ARROW_MIN:
        ax.annotate("", xy=(arr_x, iv), xytext=(arr_x, cv),
                    arrowprops=dict(arrowstyle='<->', color=ARR_COLOR, lw=2.5, mutation_scale=16))
        ax.text(txt_x + (0.05 if ha=='left' else -0.05), mid_y, pct_fmt.format(pct),
                ha=ha, va='center', color=ARR_COLOR, fontsize=10, fontweight='bold')
    else:
        ax.text(txt_x, mid_y, pct_fmt.format(pct),
                ha=ha, va='center', color=ARR_COLOR, fontsize=9, fontweight='bold')

def plot_graph(field, ylabel, val_fmt, pct_fmt, filename, title):
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle(title + f"\n({SIZE_LABEL} Firmware, 500kbps CAN, n=10 trials, ±1σ)", fontsize=14, fontweight='bold')
    
    cm, cs = get_stats('Custom', field)
    im, is_ = get_stats('RAW ISO-TP', field)
    
    ax.errorbar(x_pos, cm, yerr=cs, marker='o', color=C_COLOR,
                label='Proposed (Selective NACK)', capsize=6, capthick=2,
                linestyle='-', linewidth=2.5, markersize=9, zorder=3)
    ax.errorbar(x_pos, im, yerr=is_, marker='s', color=I_COLOR,
                label='ISO-TP (Block Retransmission)', capsize=6, capthick=2,
                linestyle='--', linewidth=2.5, markersize=9, zorder=3)
    
    pad = (max(im + is_) - min(cm - cs)) * 0.45
    ymin = min(cm - cs) - pad * 0.85
    ymax = max(im + is_) + pad * 1.15
    # For overhead, min y should be below 0
    if field == 'overhead':
        ymin = -(max(im + is_) * 0.15)
        ymax = max(im + is_) * 1.6
        
    ax.set_ylim(ymin, ymax)
    yr = ymax - ymin
    
    for xi in range(len(LOSS_RATES)):
        # For overhead, we show 'x' (times) multiplier instead of % if preferred, but let's stick to user's style
        if field == 'overhead':
            cv, iv = cm[xi], im[xi]
            cstd, istd = cs[xi], is_[xi]
            gap = iv - cv
            mid_y = (cv + iv) / 2
            ax.text(xi, cv - cstd - yr*0.04, f"{cv:.2f}%", ha='center', va='top', color=C_COLOR, fontsize=10, fontweight='bold')
            ax.text(xi, iv + istd + yr*0.04, f"{iv:.2f}%", ha='center', va='bottom', color=I_COLOR, fontsize=10, fontweight='bold')
            
            if xi < len(LOSS_RATES) - 1: arr_x = xi + 0.1; ha = 'left'; txt_x = arr_x + 0.05
            else: arr_x = xi - 0.1; ha = 'right'; txt_x = arr_x - 0.05
            
            if cv > 0.0005 and gap / yr >= ARROW_MIN:
                ax.annotate("", xy=(arr_x, iv), xytext=(arr_x, cv), arrowprops=dict(arrowstyle='<->', color=ARR_COLOR, lw=2.5, mutation_scale=16))
                ax.text(txt_x, mid_y, f"{iv/cv:.1f}x", ha=ha, va='center', color=ARR_COLOR, fontsize=10, fontweight='bold')
            elif cv > 0.0005:
                ax.text(txt_x, mid_y, f"{iv/cv:.1f}x", ha=ha, va='center', color=ARR_COLOR, fontsize=9, fontweight='bold')
        else:
            annotate_points(ax, xi, cm[xi], im[xi], cs[xi], is_[xi], yr, val_fmt=val_fmt, pct_fmt=pct_fmt)
            
    ax.set_xticks(x_pos); ax.set_xticklabels(LOSS_LABEL)
    ax.set_xlabel("Packet Loss Rate", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(f'/Users/wh31028/repos/capston/can-fota-BBB/{filename}', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved {filename}")

plot_graph('time', 'Transfer Time (s)', "{:.1f}s", "+{:.1f}%", "graph1_transfer_time_STmin5.png", "CAN Firmware Protocol Comparison: Transfer Time vs Packet Loss Rate")
plot_graph('overhead', 'Retransmission Overhead (%)', "{:.2f}%", "", "graph2_overhead_STmin5.png", "CAN Firmware Protocol Comparison: Retransmission Overhead vs Packet Loss Rate")
plot_graph('total', 'Total Frames (Count)', "{:,.0f}", "+{:.1f}%", "graph3_total_frames_STmin5.png", "CAN Firmware Protocol Comparison: Total Bus Traffic (TX+RX) vs Loss Rate")

print("\n✅ 모든 STmin5 그래프(graph1~3) 생성 완료!")
