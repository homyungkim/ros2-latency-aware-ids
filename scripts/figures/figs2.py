"""Publication figures drawn at final print size (IEEE Access: column 3.45 in, full width 7.0 in).
Text is 7-8 pt at print size so it stays legible."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

plt.rcParams.update({
    "font.family": "FreeSans", "font.size": 7.5, "mathtext.fontset": "stix",
    "axes.linewidth": 0.6, "savefig.dpi": 600,
})

INK = "#1F2937"; MUTED = "#4B5563"
BLUE, BLUE_E = "#E3EDF8", "#2563A8"
GREEN, GREEN_E = "#E4F2E3", "#2E7D32"
RED, RED_E = "#FBE6E4", "#B42318"
GRAY, GRAY_E = "#F1F2F4", "#6B7280"
AMBER, AMBER_E = "#FDF1DC", "#B45309"


def canvas(w, h):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, fc=GRAY, ec=GRAY_E, fs=7.5, bold=False, ls="-", lw=0.9, color=INK, r=0.05):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=color,
            fontweight="bold" if bold else "normal", linespacing=1.2)


def group(ax, x, y, w, h, label, ec=GRAY_E):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                fc="none", ec=ec, lw=0.7, ls=(0, (4, 2))))
    ax.text(x + 0.08, y + h - 0.06, label, ha="left", va="top", fontsize=7, color=ec, fontweight="bold")


def arrow(ax, p, q, color=INK, ls="-", both=False, lw=0.9, ms=7, cs="arc3"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=ms,
                                 color=color, lw=lw, ls=ls, shrinkA=1.5, shrinkB=1.5, connectionstyle=cs))


def save(fig, name):
    fig.savefig(name, dpi=600)
    plt.close(fig)


# ---------------------------------------------------------------- Fig. 1 workflow (full width)
fig, ax = canvas(7.0, 2.25)
group(ax, 0.05, 0.12, 1.25, 2.03, "Public data", GRAY_E)
for i, (n, s) in enumerate([("Edge-IIoTset", "IIoT / OT"), ("ROSIDS23", "ROS"), ("ROSPaCe", "ROS 2")]):
    box(ax, 0.17, 1.42 - i * 0.55, 1.01, 0.42, f"{n}\n{s}", fc="white", ec=GRAY_E, fs=7)
group(ax, 1.42, 0.12, 3.45, 2.03, "Training and accuracy evaluation (Kaggle GPU)", BLUE_E)
steps = [("Leakage-free\npreprocessing", "Sec. IV-A"), ("Feature\nselection", "Sec. IV-B"),
         ("Cascaded IDS\ntraining", "Sec. IV-C"), ("Compression\nand export", "Sec. IV-D")]
for i, (t, s) in enumerate(steps):
    x = 1.55 + i * 0.82
    box(ax, x, 1.10, 0.72, 0.62, t, fc=BLUE, ec=BLUE_E, fs=7)
    ax.text(x + 0.36, 1.03, s, ha="center", va="top", fontsize=6.2, color=MUTED)
    if i: arrow(ax, (x - 0.10, 1.41), (x, 1.41))
box(ax, 1.55, 0.25, 3.18, 0.50, "Accuracy evaluation: 5-fold × 5 seeds, leakage configurations L0–L3,\nleave-one-attack-out, Friedman–Nemenyi test (Sec. V-C)", fc="white", ec=BLUE_E, fs=6.8)
arrow(ax, (1.30, 1.41), (1.55, 1.41))
arrow(ax, (3.14, 1.10), (3.14, 0.75))
group(ax, 5.0, 0.12, 1.95, 2.03, "Deployment validation (workstation)", GREEN_E)
box(ax, 5.12, 1.13, 1.71, 0.62, "Edge-class latency\n1 core, 2 GB container\np50 / p99, throughput (Sec. V-D)", fc=GREEN, ec=GREEN_E, fs=6.8)
box(ax, 5.12, 0.25, 1.71, 0.70, "ROS 2 control-loop simulation\nGazebo, UR5e, 500 Hz\nconditions C0–C3 (Sec. V-E)", fc=GREEN, ec=GREEN_E, fs=6.8)
arrow(ax, (4.75, 1.41), (5.12, 1.41), color=GREEN_E)
arrow(ax, (5.97, 1.13), (5.97, 0.95), color=GREEN_E)
save(fig, "f_workflow.png")

# ---------------------------------------------------------------- Fig. 2 system and threat model (full width)
fig, ax = canvas(7.0, 2.75)
group(ax, 0.05, 0.08, 4.40, 2.60, "Robotic cell (OT network)", GRAY_E)
box(ax, 0.20, 1.80, 1.40, 0.62, "Robotic arm\nROS 2 / ros2_control", fc=BLUE, ec=BLUE_E, bold=True, fs=7)
box(ax, 0.20, 0.95, 1.40, 0.62, "Robot controller\njoint trajectory controller\n$f_c$ = 500 Hz", fc=BLUE, ec=BLUE_E, fs=7)
box(ax, 0.20, 0.20, 1.40, 0.55, "IIoT sensors / PLC\nModbus/TCP, MQTT", fs=7)
box(ax, 1.95, 0.95, 0.85, 0.62, "OT switch\n(mirror port)", fs=7)
box(ax, 3.15, 0.95, 1.15, 1.02, "Edge gateway\n\nProposed\ncascaded IDS", fc=GREEN, ec=GREEN_E, bold=True, fs=7)
arrow(ax, (0.90, 1.80), (0.90, 1.57), both=True)
arrow(ax, (1.60, 1.26), (1.95, 1.26), both=True)
arrow(ax, (1.60, 0.48), (2.10, 0.95), both=True)
arrow(ax, (2.80, 1.40), (3.15, 1.40), color=GREEN_E, ls=(0, (3, 2)))
ax.text(2.975, 1.46, "copy", fontsize=6.3, ha="center", color=GREEN_E)
box(ax, 4.85, 1.95, 2.05, 0.55, "Remote operator /\nteleoperation station", fs=7)
box(ax, 4.85, 1.12, 2.05, 0.55, "Plant / enterprise network\n(security operations)", fs=7)
box(ax, 4.85, 0.20, 2.05, 0.62, "Attacker\nbotnet-recruited IoT node,\nexposed remote access", fc=RED, ec=RED_E, ls=(0, (3, 2)), fs=7)
arrow(ax, (4.30, 1.80), (4.85, 2.20), both=True)
arrow(ax, (4.30, 1.40), (4.85, 1.40), color=GREEN_E)
ax.text(4.58, 1.46, "alerts", fontsize=6.3, ha="center", color=GREEN_E)
arrow(ax, (4.85, 0.45), (2.62, 0.95), color=RED_E, ls=(0, (3, 2)), cs="arc3,rad=-0.12")
ax.text(3.45, 0.16, "DoS/DDoS, scanning, ARP/DNS spoofing,\nunauthorized publish / subscribe", fontsize=6.3, color=RED_E, ha="center")
save(fig, "f_system.png")

# ---------------------------------------------------------------- Fig. 3 latency budget (column width)
fig, ax = canvas(3.45, 1.45)
x0, W = 0.25, 2.95  # T_c spans W inches
y = 0.62
segs = [(0.18, "$L_{net}$", GRAY, GRAY_E), (0.24, "$L_{feat}$", AMBER, AMBER_E),
        (0.20, "$L_{inf}$", GREEN, GREEN_E)]
cx = x0
for frac, lab, fc, ec in segs:
    ax.add_patch(Rectangle((cx, y), W * frac, 0.30, fc=fc, ec=ec, lw=0.8))
    ax.text(cx + W * frac / 2, y + 0.15, lab, ha="center", va="center", fontsize=7.5)
    cx += W * frac
ax.add_patch(Rectangle((cx, y), x0 + W - cx, 0.30, fc="white", ec=GRAY_E, lw=0.8, ls=(0, (3, 2))))
ax.text((cx + x0 + W) / 2, y + 0.15, "slack", ha="center", va="center", fontsize=7, color=MUTED)
ax.plot([x0 + W] * 2, [0.35, 1.20], color=RED_E, lw=1.0)
ax.text(x0 + W, 1.25, "deadline", ha="center", va="bottom", fontsize=6.5, color=RED_E)
arrow(ax, (x0, 1.08), (x0 + W, 1.08), both=True, lw=0.7, ms=5)
ax.text(x0 + W / 2, 1.12, "control period $T_c = 1/f_c$ (2 ms at 500 Hz)", ha="center", va="bottom", fontsize=7)
e2e0, e2e1 = x0 + W * 0.18, x0 + W * 0.62
arrow(ax, (e2e0, 0.47), (e2e1, 0.47), both=True, lw=0.7, ms=5, color=GREEN_E)
ax.text((e2e0 + e2e1) / 2, 0.40, "$L_{e2e}$ (inline IDS), bounded at p99 by (2)", ha="center", va="top", fontsize=6.6, color=GREEN_E)
ax.plot([x0] * 2, [0.35, 1.0], color=INK, lw=0.6)
ax.text(x0, 0.30, "command\nsent", ha="center", va="top", fontsize=6.0, color=MUTED)
save(fig, "f_budget.png")

# ---------------------------------------------------------------- Fig. 4 leakage-free protocol (column width)
fig, ax = canvas(3.45, 3.05)
box(ax, 0.15, 2.58, 3.15, 0.34, "Raw records (all three datasets)", fs=7)
box(ax, 0.15, 2.10, 3.15, 0.34, "① Remove identifier fields (addresses, ports, time, payload)", fc=AMBER, ec=AMBER_E, fs=6.8)
box(ax, 0.15, 1.62, 3.15, 0.34, "② Remove duplicates before any split", fc=AMBER, ec=AMBER_E, fs=6.8)
box(ax, 0.15, 1.14, 3.15, 0.34, "③ Stratified 5-fold split (× 5 seeds)", fc=AMBER, ec=AMBER_E, fs=6.8)
for yy in (2.58, 2.10, 1.62):
    arrow(ax, (1.725, yy), (1.725, yy - 0.14))
group(ax, 0.15, 0.08, 1.95, 0.94, "④ Training fold", BLUE_E)
box(ax, 0.25, 0.48, 0.55, 0.30, "fit\nscaler", fc=BLUE, ec=BLUE_E, fs=6.5)
box(ax, 0.88, 0.48, 0.55, 0.30, "SMOTE", fc=BLUE, ec=BLUE_E, fs=6.5)
box(ax, 1.51, 0.48, 0.52, 0.30, "train\nmodel", fc=BLUE, ec=BLUE_E, fs=6.5)
arrow(ax, (0.80, 0.63), (0.88, 0.63)); arrow(ax, (1.43, 0.63), (1.51, 0.63))
ax.text(1.12, 0.22, "all fitted transforms stay here", ha="center", fontsize=6.2, color=BLUE_E)
group(ax, 2.20, 0.08, 1.10, 0.94, "Test fold", GREEN_E)
box(ax, 2.30, 0.48, 0.90, 0.30, "transform +\nevaluate", fc=GREEN, ec=GREEN_E, fs=6.5)
ax.text(2.75, 0.22, "never resampled", ha="center", fontsize=6.2, color=GREEN_E)
arrow(ax, (1.10, 1.14), (1.10, 1.02)); arrow(ax, (2.75, 1.14), (2.75, 1.02))
arrow(ax, (2.03, 0.70), (2.30, 0.70), ls=(0, (3, 2)))
save(fig, "f_leakage.png")

# ---------------------------------------------------------------- Fig. 5 cascade (full width)
fig, ax = canvas(7.0, 1.85)
box(ax, 0.08, 0.62, 0.95, 0.62, "Mirrored traffic\n(packets / flows)", fs=7)
box(ax, 1.30, 0.62, 1.15, 0.62, "Feature extraction\n(top-$k$ header and\nflow features)", fs=7)
box(ax, 2.72, 0.55, 1.30, 0.76, "Stage 1\ncompact binary GBDT\n(all inputs, latency $t_1$)", fc=GREEN, ec=GREEN_E, bold=True, fs=7)
box(ax, 4.62, 1.02, 1.30, 0.70, "Stage 2\nINT8 multi-class model\n(latency $t_2$)", fc=BLUE, ec=BLUE_E, bold=True, fs=7)
box(ax, 4.62, 0.12, 1.30, 0.52, "Forward as benign", fs=7)
box(ax, 6.15, 1.02, 0.80, 0.70, "Alert +\nattack type", fc=RED, ec=RED_E, fs=7)
arrow(ax, (1.03, 0.93), (1.30, 0.93)); arrow(ax, (2.45, 0.93), (2.72, 0.93))
arrow(ax, (4.02, 1.10), (4.62, 1.37)); ax.text(4.08, 1.38, "$p(x) \\geq \\tau$\nfraction $r$", fontsize=6.8, va="bottom")
arrow(ax, (4.02, 0.75), (4.62, 0.38)); ax.text(4.12, 0.42, "$p(x) < \\tau$", fontsize=6.8, va="top")
arrow(ax, (5.92, 1.37), (6.15, 1.37))
arrow(ax, (5.27, 1.02), (5.27, 0.64), color=GRAY_E, ls=(0, (3, 2)))
ax.text(5.32, 0.83, "benign class\n(rejects Stage 1 false positives)", fontsize=6.2, color=MUTED, va="center")
save(fig, "f_cascade.png")

# ---------------------------------------------------------------- Fig. 6 simulation testbed (full width)
fig, ax = canvas(7.0, 2.35)
group(ax, 0.05, 0.08, 6.90, 2.20, "Workstation (Ubuntu, Docker), isolated from external networks", GRAY_E)
ax.add_patch(Rectangle((0.30, 1.02), 6.40, 0.13, fc="#D1D5DB", ec="none"))
ax.text(6.68, 1.085, "Docker bridge network (DDS, TCP/UDP)", fontsize=6.5, ha="right", va="center", color=INK)
cont = [
    (0.30, "Robot simulation", "Gazebo (headless), UR5e\nros2_control, 500 Hz", BLUE, BLUE_E),
    (1.95, "Teleoperation node", "repeated pick-and-place\ntrajectory goals", BLUE, BLUE_E),
    (3.60, "Attacker", "tcpreplay of public pcaps;\nunauthorized publish,\nsubscriber flood, SYN flood", RED, RED_E),
    (5.25, "IDS container", "cascaded IDS\n1 core, 2 GB\nsniffs bridge", GREEN, GREEN_E),
]
for x, title, body, fc, ec in cont:
    box(ax, x, 1.35, 1.45, 0.72, "", fc=fc, ec=ec)
    ax.text(x + 0.725, 1.92, title, ha="center", va="center", fontsize=7.2, fontweight="bold", color=INK)
    ax.text(x + 0.725, 1.58, body, ha="center", va="center", fontsize=6.5, color=INK, linespacing=1.15)
    arrow(ax, (x + 0.725, 1.35), (x + 0.725, 1.15), both=True, color=ec)
box(ax, 1.20, 0.25, 2.30, 0.52, "Recorder: /joint_states, controller state\n→ jitter, deadline misses, RMSE", fs=6.6)
box(ax, 4.00, 0.25, 2.30, 0.52, "Alert log with timestamps\n→ time to detect, false alarms / h", fs=6.6)
arrow(ax, (2.35, 1.02), (2.35, 0.77)); arrow(ax, (5.97, 1.02), (5.97, 0.77), color=GREEN_E)
save(fig, "f_testbed.png")
print("figures ok")
