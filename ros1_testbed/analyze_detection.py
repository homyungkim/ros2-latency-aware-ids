"""Detection delay and false-alarm analysis for the ROS 1 testbed (R1_C3 runs, where TCPROS traffic matches
the ROSIDS23 training domain). For each run it pairs <tag>_ids_flows.csv with <tag>_attack_start.txt and reports:
  detection_delay_s  first non-benign alert at or after the attack start, minus the attack start
  fp_before          non-benign alerts during the benign period before the attack (false alarms)
  benign_s           length of the benign period actually observed
Usage: python analyze_detection.py [runs_dir]   (default ./runs). Writes runs/detection_summary.csv."""
import glob, json, os, re, sys
import numpy as np, pandas as pd

RUNS = sys.argv[1] if len(sys.argv) > 1 else "runs"
rows = []
for start_f in sorted(glob.glob(f"{RUNS}/*_attack_start.txt")):
    tag = os.path.basename(start_f)[:-len("_attack_start.txt")]
    flows_f = f"{RUNS}/{tag}_ids_flows.csv"
    if not os.path.exists(flows_f):
        continue
    t_atk = float(open(start_f).read().strip())
    df = pd.read_csv(flows_f)
    if "label" not in df or "t" not in df or not len(df):
        continue
    m = re.match(r"(R1_C\d)_([a-z]+)_run(\d+)", tag)
    attack = m.group(2) if m else "?"
    alerts = df[df.label != "Benign"]
    after = alerts[alerts.t >= t_atk]
    before = alerts[alerts.t < t_atk]
    delay = float(after.t.min() - t_atk) if len(after) else None
    rows.append(dict(tag=tag, attack=attack, flows=len(df), alerts=int(len(alerts)),
                     detection_delay_s=delay, fp_before=int(len(before)),
                     benign_s=round(t_atk - df.t.min(), 1),
                     top_label=after.label.mode().iat[0] if len(after) else None))
    print(rows[-1])

if rows:
    out = pd.DataFrame(rows)
    out.to_csv(f"{RUNS}/detection_summary.csv", index=False)
    print("\n== per-attack means ==")
    g = out.groupby("attack").agg(runs=("tag", "size"), mean_delay_s=("detection_delay_s", "mean"),
                                  mean_fp=("fp_before", "mean")).round(3)
    print(g.to_string())
    print(f"\nsaved {RUNS}/detection_summary.csv")
else:
    print("no R1_C3 runs with both *_ids_flows.csv and *_attack_start.txt found in", RUNS)
