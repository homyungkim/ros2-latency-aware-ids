#!/usr/bin/env python3
"""ROS 1 control-quality recorder (same metrics as the ROS 2 recorder): wall-clock /joint_states intervals,
controller tracking error, real-time factor from /clock. Usage: recorder.py --cond R1_C0 --run 1 --duration 300"""
import argparse, json, math, time
import numpy as np, rospy
from sensor_msgs.msg import JointState
from rosgraph_msgs.msg import Clock
from control_msgs.msg import JointTrajectoryControllerState
TC_MS = 2.0
ap = argparse.ArgumentParser()
ap.add_argument("--cond", default="R1_C0"); ap.add_argument("--run", type=int, default=1)
ap.add_argument("--duration", type=float, default=300); ap.add_argument("--warmup", type=float, default=20)
ap.add_argument("--out", default="/data")
a = ap.parse_args()
rospy.init_node("recorder", disable_signals=True)
t_js, err, clk = [], [], []
rospy.Subscriber("/joint_states", JointState, lambda _: t_js.append(time.perf_counter_ns()), queue_size=1000, tcp_nodelay=True)
def on_state(m):
    e = list(m.error.positions)
    if e: err.append(math.sqrt(sum(x * x for x in e) / len(e)))
rospy.Subscriber("/eff_joint_traj_controller/state", JointTrajectoryControllerState, on_state, queue_size=100)
rospy.Subscriber("/clock", Clock, lambda m: clk.append((time.perf_counter_ns(), m.clock.to_sec())), queue_size=10)
time.sleep(a.warmup); t_js.clear(); err.clear(); clk.clear()
time.sleep(a.duration)
t = np.asarray(list(t_js), dtype=np.float64) / 1e6; d = np.diff(t)
rtf = np.nan
if len(clk) > 2:
    (w0, s0), (w1, s1) = clk[0], clk[-1]; rtf = (s1 - s0) / ((w1 - w0) / 1e9)
mins = a.duration / 60
s = dict(cond=a.cond, run=a.run, n=int(len(d)), mean_ms=float(d.mean()) if len(d) else None,
         sigma_J_ms=float(d.std(ddof=1)) if len(d) > 1 else None, p99_ms=float(np.percentile(d, 99)) if len(d) else None,
         misses_per_min=float((d > 1.5 * TC_MS).sum() / mins) if len(d) else None,
         rmse_rad=float(np.sqrt(np.mean(np.square(err)))) if err else None, rtf=float(rtf),
         valid=bool(rtf >= 0.98) if not math.isnan(rtf) else None)
base = f"{a.out}/{a.cond}_run{a.run}"
np.savetxt(f"{base}_intervals.csv", d, fmt="%.4f", header="interval_ms", comments="")
json.dump(s, open(f"{base}_summary.json", "w"), indent=1); print(json.dumps(s, indent=1))
rospy.signal_shutdown("done")
