"""Result figures for the manuscript (Figs. 7-9).

Usage after the experiments:
    python results_figs.py --tradeoff tradeoff.csv --jitter intervals.csv --shap shap.csv

Expected CSV columns
    tradeoff.csv : model, macro_f1, p99_ms            (one row per model; model 'Proposed cascade' is highlighted)
    intervals.csv: condition, interval_ms             (one row per /joint_states interval; condition in C0..C3)
    shap.csv     : feature, mean_abs_shap, dataset    (top features of Stage 1; dataset in Edge-IIoTset, ROSIDS23)

Without arguments, empty templates (axes, labels, budget lines) are drawn so the layout can be reviewed.
"""
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "FreeSans", "font.size": 7.5, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "savefig.dpi": 600})
BLUE, GREEN, RED, GRAY = "#2563A8", "#2E7D32", "#B42318", "#6B7280"
COL_W = 3.45


def template_note(ax):
    ax.text(0.5, 0.5, "Template: populate from experiment CSV\n(results_figs.py)", transform=ax.transAxes,
            ha="center", va="center", fontsize=7, color="#9CA3AF", style="italic")


def tradeoff(path):
    fig, ax = plt.subplots(figsize=(COL_W, 2.3))
    for budget, lab, ha in [(2.0, "2 ms (500 Hz) ", "right"), (8.0, " 8 ms (125 Hz)", "left")]:
        ax.axvline(budget, color=RED, lw=0.8, ls=(0, (4, 2)))
        ax.text(budget, 0.98, lab, color=RED, fontsize=6.3, va="top", ha=ha, transform=ax.get_xaxis_transform())
    if path:
        import pandas as pd
        d = pd.read_csv(path)
        for _, r in d.iterrows():
            hi = r["model"] == "Proposed cascade"
            ax.scatter(r["p99_ms"], r["macro_f1"], s=28 if hi else 16, color=GREEN if hi else BLUE,
                       marker="*" if hi else "o", zorder=3)
            ax.annotate(r["model"], (r["p99_ms"], r["macro_f1"]), xytext=(3, 2), textcoords="offset points", fontsize=6.3)
    else:
        ax.set_ylim(80, 100); template_note(ax)
    ax.set_xscale("log"); ax.set_xlim(0.01, 100)
    ax.set_xlabel("End-to-end p99 latency (ms, log scale)"); ax.set_ylabel("Macro-F1 (%)")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", lw=0.3, color="#E5E7EB")
    fig.tight_layout(pad=0.3); fig.savefig("f_tradeoff.png"); plt.close(fig)


def jitter(path):
    fig, ax = plt.subplots(figsize=(COL_W, 2.1))
    conds = ["C0", "C1", "C2", "C3"]
    labels = ["C0\nbaseline", "C1\nIDS only", "C2\nattack only", "C3\nIDS + attack"]
    if path:
        import pandas as pd
        d = pd.read_csv(path)
        data = [d.loc[d.condition == c, "interval_ms"].values for c in conds]
        bp = ax.boxplot(data, widths=0.5, showfliers=False, patch_artist=True)
        for b, c in zip(bp["boxes"], [GRAY, GREEN, RED, BLUE]):
            b.set_facecolor(c); b.set_alpha(0.35); b.set_edgecolor(c)
    else:
        ax.set_xlim(0.5, 4.5); ax.set_ylim(1.5, 3.0); template_note(ax)
    ax.axhline(2.0, color=GRAY, lw=0.6); ax.axhline(3.0, color=RED, lw=0.8, ls=(0, (4, 2)))
    ax.text(4.45, 2.0, "nominal $T_c$", fontsize=6.3, ha="right", va="bottom", color=GRAY)
    ax.text(4.45, 3.0, "miss threshold 1.5$T_c$", fontsize=6.3, ha="right", va="top", color=RED)
    ax.set_xticks(range(1, 5)); ax.set_xticklabels(labels, fontsize=6.5)
    ax.set_ylabel("/joint_states interval (ms)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(pad=0.3); fig.savefig("f_jitter.png"); plt.close(fig)


def shap(path):
    fig, axes = plt.subplots(1, 2, figsize=(COL_W, 2.2), sharex=False)
    for ax, ds in zip(axes, ["Edge-IIoTset", "ROSIDS23"]):
        if path:
            import pandas as pd
            d = pd.read_csv(path); d = d[d.dataset == ds].nlargest(8, "mean_abs_shap").iloc[::-1]
            ax.barh(d.feature, d.mean_abs_shap, color=BLUE, height=0.6)
            ax.tick_params(axis="y", labelsize=6)
        else:
            ax.set_yticks([]); ax.text(0.5, 0.5, "Template", transform=ax.transAxes, ha="center", va="center", fontsize=7, color="#9CA3AF", style="italic")
        ax.set_title(ds, fontsize=7.5); ax.set_xlabel("mean |SHAP|")
        if not path: ax.set_xticks([0, 0.5, 1.0])
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(pad=0.3); fig.savefig("f_shap.png"); plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tradeoff"); p.add_argument("--jitter"); p.add_argument("--shap")
    a = p.parse_args()
    tradeoff(a.tradeoff); jitter(a.jitter); shap(a.shap)
    print("result figures written")
