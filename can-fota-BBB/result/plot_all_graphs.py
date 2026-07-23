import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({'font.family': 'serif', 'font.size': 11})

# ── CSV 로드 ──────────────────────────────────────────────────
rows = []
with open('/Users/wh31028/repos/capston/can-fota-BBB/result/fota_results_new.csv') as f:
    for r in csv.DictReader(f):
        try:
            rows.append({
                'protocol': r['protocol'], 'loss': float(r['loss_rate_pct']),
                'size': int(r['fw_size_bytes']), 'time': float(r['total_time_sec']),
                'overhead': float(r['overhead_pct']), 'total': int(r['total_frames']),
            })
        except: pass

SIZES      = [65536, 131072, 262144, 524288]
SIZE_LABEL = {65536:'64KB', 131072:'128KB', 262144:'256KB', 524288:'512KB'}
LOSS_RATES = [0.0, 0.01, 0.05, 0.1]
LOSS_LABEL = ['0%', '0.01%', '0.05%', '0.1%']
x_pos = np.arange(len(LOSS_RATES))
C_COLOR = '#1f77b4'; I_COLOR = '#d62728'; ARR_COLOR = '#e07b00'
ARROW_MIN = 0.055   # gap/y_range 이 이 값보다 작으면 화살표 대신 % 텍스트만

def get_stats(proto, size, field='time'):
    means, stds = [], []
    for lr in LOSS_RATES:
        vals = [r[field] for r in rows
                if r['protocol']==proto and r['size']==size and abs(r['loss']-lr)<1e-6]
        means.append(np.mean(vals) if vals else 0)
        stds.append(np.std(vals, ddof=1) if len(vals)>1 else 0)
    return np.array(means), np.array(stds)


def annotate_points(ax, xi, cv, iv, cv_std, iv_std, y_range,
                    val_fmt="{:.1f}s", pct_fmt="+{:.1f}%", n_pts=4):
    """
    같은 x 위치(xi)에서:
    - Proposed 값: 에러바 아래
    - ISO-TP 값 : 에러바 위
    - 두 점 사이 수직 양방향 화살표 (gap 작으면 % 텍스트만)
    - % / 텍스트: 마지막 포인트면 왼쪽, 나머지는 오른쪽
    """
    pct   = (iv - cv) / cv * 100 if cv > 0 else 0
    gap   = iv - cv
    mid_y = (cv + iv) / 2

    # ── 값 텍스트 (선·에러바와 안 겹치게 에러바 끝 기준) ─────
    ax.text(xi, cv - cv_std - y_range*0.05, val_fmt.format(cv),
            ha='center', va='top', color=C_COLOR, fontsize=9, fontweight='bold')
    ax.text(xi, iv + iv_std + y_range*0.05, val_fmt.format(iv),
            ha='center', va='bottom', color=I_COLOR, fontsize=9, fontweight='bold')

    # ── 텍스트/화살표 방향 ────────────────────────────────────
    if xi < n_pts - 1:
        arr_x = xi + 0.06   # 마커 오른쪽 살짝
        txt_x = arr_x + 0.04
        ha = 'left'
    else:
        arr_x = xi - 0.06   # 마지막은 왼쪽
        txt_x = arr_x - 0.04
        ha = 'right'

    # ── gap 크기에 따라 화살표 vs 텍스트만 ───────────────────
    if gap / y_range >= ARROW_MIN:
        ax.annotate("",
                    xy=(arr_x, iv), xytext=(arr_x, cv),
                    arrowprops=dict(arrowstyle='<->', color=ARR_COLOR,
                                    lw=2.0, mutation_scale=14))
        ax.text(txt_x + (0.06 if ha=='left' else -0.06), mid_y,
                pct_fmt.format(pct),
                ha=ha, va='center', color=ARR_COLOR, fontsize=8.5, fontweight='bold')
    else:
        # gap 너무 작음 → 화살표 없이 % 만 표시
        ax.text(txt_x, mid_y, pct_fmt.format(pct),
                ha=ha, va='center', color=ARR_COLOR, fontsize=8, fontweight='bold')


def make_line_subplot(axes, field, ylabel, title_main, val_fmt="{:.1f}s",
                      pct_fmt="+{:.1f}%", pad_lo=0.42, pad_hi=1.15):
    for ax, size in zip(axes.flat, SIZES):
        cm, cs = get_stats('Custom',     size, field)
        im, is_ = get_stats('RAW ISO-TP', size, field)
        ax.errorbar(x_pos, cm, yerr=cs, marker='o', color=C_COLOR,
                    label='Proposed (Selective NACK)', capsize=5, capthick=1.5,
                    linestyle='-', linewidth=2, markersize=7, zorder=3)
        ax.errorbar(x_pos, im, yerr=is_, marker='s', color=I_COLOR,
                    label='ISO-TP (Block Retransmission)', capsize=5, capthick=1.5,
                    linestyle='--', linewidth=2, markersize=7, zorder=3)
        pad = (max(im + is_) - min(cm - cs)) * 0.42
        ymin = min(cm - cs) - pad * pad_lo
        ymax = max(im + is_) + pad * pad_hi
        ax.set_ylim(ymin, ymax)
        yr = ymax - ymin
        for xi in range(len(LOSS_RATES)):
            annotate_points(ax, xi, cm[xi], im[xi], cs[xi], is_[xi], yr,
                            val_fmt=val_fmt, pct_fmt=pct_fmt, n_pts=len(LOSS_RATES))
        ax.set_xticks(x_pos); ax.set_xticklabels(LOSS_LABEL)
        ax.set_title(f"{SIZE_LABEL[size]} Firmware", fontsize=12, fontweight='bold')
        ax.set_xlabel("Packet Loss Rate", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.legend(fontsize=8, loc='upper left')
        ax.grid(True, linestyle='--', alpha=0.5)


# ═══════════════════════════════════════════════════════════════
# GRAPH 1 — Transfer Time 2×2
# ═══════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("CAN Firmware Protocol Comparison: Transfer Time vs Packet Loss Rate\n"
             "(n=30 trials, 1Mbps CAN, Error bars = ±1σ)", fontsize=14, fontweight='bold')
make_line_subplot(axes, 'time', 'Transfer Time (s)', '')
plt.tight_layout()
plt.savefig('/Users/wh31028/repos/capston/can-fota-BBB/result/graph1_transfer_time.png',
            dpi=150, bbox_inches='tight')
plt.close(); print("Saved graph1_transfer_time.png")


# ═══════════════════════════════════════════════════════════════
# GRAPH 2 — Retransmission Overhead 2×2  (배수 표기)
# ═══════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("CAN Firmware Protocol Comparison: Retransmission Overhead vs Packet Loss Rate\n"
             "(n=30 trials per condition)", fontsize=14, fontweight='bold')

for ax, size in zip(axes.flat, SIZES):
    cm, cs = get_stats('Custom',     size, 'overhead')
    im, is_ = get_stats('RAW ISO-TP', size, 'overhead')
    ax.errorbar(x_pos, cm, yerr=cs, marker='o', color=C_COLOR,
                label='Proposed (Selective NACK)', capsize=5, capthick=1.5,
                linestyle='-', linewidth=2, markersize=7, zorder=3)
    ax.errorbar(x_pos, im, yerr=is_, marker='s', color=I_COLOR,
                label='ISO-TP (Block Retransmission)', capsize=5, capthick=1.5,
                linestyle='--', linewidth=2, markersize=7, zorder=3)
    ymin = -(max(im + is_) * 0.22)
    ymax =  max(im + is_) * 1.60
    ax.set_ylim(ymin, ymax); yr = ymax - ymin

    for xi in range(len(LOSS_RATES)):
        cv, iv = cm[xi], im[xi]
        cstd, istd = cs[xi], is_[xi]
        # 값 텍스트
        ax.text(xi, cv - cstd - yr*0.04, f"{cv:.2f}%",
                ha='center', va='top', color=C_COLOR, fontsize=9, fontweight='bold')
        ax.text(xi, iv + istd + yr*0.04, f"{iv:.2f}%",
                ha='center', va='bottom', color=I_COLOR, fontsize=9, fontweight='bold')
        # 배수 화살표 (두 점 사이)
        gap = iv - cv
        mid_y = (cv + iv) / 2
        if xi < len(LOSS_RATES) - 1:
            arr_x = xi + 0.06
            ha    = 'left'
            txt_x = arr_x + 0.04
        else:
            arr_x = xi - 0.06
            ha    = 'right'
            txt_x = arr_x - 0.04
        if cv > 0.0005 and gap / yr >= ARROW_MIN:
            ax.annotate("", xy=(arr_x, iv), xytext=(arr_x, cv),
                        arrowprops=dict(arrowstyle='<->', color=ARR_COLOR,
                                        lw=2.0, mutation_scale=14))
            ax.text(txt_x, mid_y, f"{iv/cv:.1f}x",
                    ha=ha, va='center', color=ARR_COLOR, fontsize=8.5, fontweight='bold')
        elif cv > 0.0005:
            ax.text(txt_x, mid_y, f"{iv/cv:.1f}x",
                    ha=ha, va='center', color=ARR_COLOR, fontsize=8, fontweight='bold')

    ax.set_xticks(x_pos); ax.set_xticklabels(LOSS_LABEL)
    ax.set_title(f"{SIZE_LABEL[size]} Firmware", fontsize=12, fontweight='bold')
    ax.set_xlabel("Packet Loss Rate", fontsize=10)
    ax.set_ylabel("Retransmission Overhead (%)", fontsize=10)
    ax.legend(fontsize=8, loc='upper left'); ax.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('/Users/wh31028/repos/capston/can-fota-BBB/result/graph2_overhead.png',
            dpi=150, bbox_inches='tight')
plt.close(); print("Saved graph2_overhead.png")


# ═══════════════════════════════════════════════════════════════
# GRAPH 3 — Baseline Bar Chart (P=0%)
# ═══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 7))
fig.suptitle("Baseline Transfer Time (P=0%, No Packet Loss)\n1Mbps CAN, n=30 trials per size",
             fontsize=14, fontweight='bold')
bar_x = np.arange(len(SIZES)); bar_w = 0.35
c_m0, c_s0, i_m0, i_s0 = [], [], [], []
for size in SIZES:
    cm, cs = get_stats('Custom', size, 'time')
    im, is_ = get_stats('RAW ISO-TP', size, 'time')
    c_m0.append(cm[0]); c_s0.append(cs[0]); i_m0.append(im[0]); i_s0.append(is_[0])
c_m0=np.array(c_m0); c_s0=np.array(c_s0); i_m0=np.array(i_m0); i_s0=np.array(i_s0)

ax.bar(bar_x-bar_w/2, c_m0, bar_w, color=C_COLOR, label='Proposed (Selective NACK)',
       alpha=0.87, yerr=c_s0, capsize=5, error_kw={'capthick':1.5})
ax.bar(bar_x+bar_w/2, i_m0, bar_w, color=I_COLOR, label='RAW ISO-TP (Go-Back-N)',
       alpha=0.87, yerr=i_s0, capsize=5, error_kw={'capthick':1.5})
y_top = max(i_m0+i_s0)*1.42; ax.set_ylim(0, y_top)

for xi, (cv, iv, cs, is_) in enumerate(zip(c_m0, i_m0, c_s0, i_s0)):
    pct = (iv-cv)/cv*100
    ax.text(bar_x[xi]-bar_w/2, cv+cs+y_top*0.010, f"{cv:.2f}s",
            ha='center', va='bottom', color=C_COLOR, fontsize=10, fontweight='bold')
    ax.text(bar_x[xi]+bar_w/2, iv+is_+y_top*0.010, f"{iv:.2f}s",
            ha='center', va='bottom', color=I_COLOR, fontsize=10, fontweight='bold')
    arrow_y = max(iv+is_, cv+cs) + y_top*0.06
    ax.annotate("", xy=(bar_x[xi]+bar_w/2-0.04, arrow_y),
                xytext=(bar_x[xi]-bar_w/2+0.04, arrow_y),
                arrowprops=dict(arrowstyle='<->', color=ARR_COLOR, lw=1.8, mutation_scale=12))
    ax.text(bar_x[xi], arrow_y+y_top*0.015, f"+{pct:.1f}%\nslower",
            ha='center', va='bottom', color=ARR_COLOR, fontsize=9.5, fontweight='bold')

ax.set_xticks(bar_x); ax.set_xticklabels([SIZE_LABEL[s] for s in SIZES])
ax.set_xlabel("Firmware Size", fontsize=12); ax.set_ylabel("Transfer Time (s)", fontsize=12)
ax.legend(fontsize=10); ax.grid(axis='y', linestyle='--', alpha=0.5)
plt.tight_layout()
plt.savefig('/Users/wh31028/repos/capston/can-fota-BBB/result/graph3_baseline.png',
            dpi=150, bbox_inches='tight')
plt.close(); print("Saved graph3_baseline.png")


# ═══════════════════════════════════════════════════════════════
# GRAPH 4 — 256KB Detailed
# ═══════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 6))
fig.suptitle("Transfer Time vs Packet Loss Rate — 256KB Detailed\n"
             "(n=30 trials, 1Mbps CAN, Error bars = ±1σ)", fontsize=13, fontweight='bold')
size = 262144
cm, cs = get_stats('Custom', size, 'time'); im, is_ = get_stats('RAW ISO-TP', size, 'time')
ax.errorbar(x_pos, cm, yerr=cs, marker='o', color=C_COLOR,
            label='Proposed (Selective NACK)', capsize=5, capthick=1.5,
            linestyle='-', linewidth=2.5, markersize=8, zorder=3)
ax.errorbar(x_pos, im, yerr=is_, marker='s', color=I_COLOR,
            label='ISO-TP (Block Retransmission)', capsize=5, capthick=1.5,
            linestyle='--', linewidth=2.5, markersize=8, zorder=3)
pad = (max(im+is_)-min(cm-cs))*0.42
ymin=min(cm-cs)-pad*0.85; ymax=max(im+is_)+pad*1.15
ax.set_ylim(ymin, ymax); yr=ymax-ymin
for xi in range(len(LOSS_RATES)):
    annotate_points(ax, xi, cm[xi], im[xi], cs[xi], is_[xi], yr, n_pts=len(LOSS_RATES))
ax.set_xticks(x_pos); ax.set_xticklabels(LOSS_LABEL)
ax.set_xlabel("Packet Loss Rate", fontsize=11); ax.set_ylabel("Transfer Time (s)", fontsize=11)
ax.legend(fontsize=9, loc='upper left'); ax.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.savefig('/Users/wh31028/repos/capston/can-fota-BBB/result/graph4_256kb_detail.png',
            dpi=150, bbox_inches='tight')
plt.close(); print("Saved graph4_256kb_detail.png")


# ═══════════════════════════════════════════════════════════════
# GRAPH 5 — Total Bus Traffic 2×2
# ═══════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("CAN Firmware Protocol Comparison: Total Bus Traffic (TX+RX) vs Loss Rate\n"
             "(n=30 trials per condition)", fontsize=14, fontweight='bold')

for ax, size in zip(axes.flat, SIZES):
    cm, cs = get_stats('Custom',     size, 'total')
    im, is_ = get_stats('RAW ISO-TP', size, 'total')
    ax.errorbar(x_pos, cm, yerr=cs, marker='o', color=C_COLOR,
                label='Proposed (Selective NACK)', capsize=5, capthick=1.5,
                linestyle='-', linewidth=2, markersize=7, zorder=3)
    ax.errorbar(x_pos, im, yerr=is_, marker='s', color=I_COLOR,
                label='ISO-TP (Block Retransmission)', capsize=5, capthick=1.5,
                linestyle='--', linewidth=2, markersize=7, zorder=3)
    pad = (max(im+is_)-min(cm-cs))*0.48
    ymin=min(cm-cs)-pad*0.50; ymax=max(im+is_)+pad*1.20
    ax.set_ylim(ymin, ymax); yr=ymax-ymin

    for xi in range(len(LOSS_RATES)):
        cv, iv = cm[xi], im[xi]; cstd, istd = cs[xi], is_[xi]
        gap = iv - cv; mid_y = (cv+iv)/2
        # 값 텍스트
        ax.text(xi, cv-cstd-yr*0.032, f"{int(round(cv)):,} frames",
                ha='center', va='top', color=C_COLOR, fontsize=8.5, fontweight='bold')
        ax.text(xi, iv+istd+yr*0.032, f"{int(round(iv)):,} frames",
                ha='center', va='bottom', color=I_COLOR, fontsize=8.5, fontweight='bold')
        # 화살표 / % 텍스트
        if xi < len(LOSS_RATES) - 1:
            arr_x = xi + 0.06
            ha    = 'left'
            txt_x = arr_x + 0.04
        else:
            arr_x = xi - 0.06
            ha    = 'right'
            txt_x = arr_x - 0.04
        pct   = gap/cv*100 if cv>0 else 0
        if gap/yr >= ARROW_MIN:
            ax.annotate("", xy=(arr_x, iv), xytext=(arr_x, cv),
                        arrowprops=dict(arrowstyle='<->', color=ARR_COLOR,
                                        lw=2.0, mutation_scale=14))
            ax.text(txt_x, mid_y, f"+{pct:.1f}%",
                    ha=ha, va='center', color=ARR_COLOR, fontsize=7.5, fontweight='bold')
        else:
            ax.text(txt_x, mid_y,
                    f"+{pct:.1f}%",
                    ha=ha, va='center', color=ARR_COLOR, fontsize=7.5, fontweight='bold')

    ax.set_xticks(x_pos); ax.set_xticklabels(LOSS_LABEL)
    ax.set_title(f"{SIZE_LABEL[size]} Firmware", fontsize=12, fontweight='bold')
    ax.set_xlabel("Packet Loss Rate", fontsize=10)
    ax.set_ylabel("Total Frames (Count)", fontsize=10)
    ax.legend(fontsize=8, loc='upper left'); ax.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('/Users/wh31028/repos/capston/can-fota-BBB/result/graph5_total_frames.png',
            dpi=150, bbox_inches='tight')
plt.close(); print("Saved graph5_total_frames.png")
print("\n✅ 모든 그래프(graph1~5) 생성 완료!")
