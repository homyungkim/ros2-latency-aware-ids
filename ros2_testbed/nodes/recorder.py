"""Control-quality recorder (manuscript eqs. for jitter and deadline misses, Table XIII, Fig. 8).
Records wall-clock arrival times of /joint_states, the tracking error of the trajectory controller,
and the real-time factor from /clock. Usage:  python3 recorder.py --cond C0 --run 1 --duration 300
Outputs /data/<cond>_run<k>_intervals.csv and /data/<cond>_run<k>_summary.json"""
import argparse, json, time, math
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from rosgraph_msgs.msg import Clock
from control_msgs.msg import JointTrajectoryControllerState

TC_MS = 2.0   # nominal control period at 500 Hz


class Recorder(Node):
    def __init__(self):
        super().__init__("recorder")
        self.t_js, self.err, self.clock = [], [], []
        self.create_subscription(JointState, "/joint_states", self.on_js, 1000)
        self.create_subscription(JointTrajectoryControllerState, "/joint_trajectory_controller/controller_state", self.on_state, 100)
        self.create_subscription(Clock, "/clock", self.on_clock, qos_profile_sensor_data)

    def on_js(self, _):
        self.t_js.append(time.perf_counter_ns())

    def on_state(self, m):
        e = list(m.error.positions) if len(m.error.positions) else []
        if e:
            self.err.append(math.sqrt(sum(x * x for x in e) / len(e)))

    def on_clock(self, m):
        self.clock.append((time.perf_counter_ns(), m.clock.sec + m.clock.nanosec * 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", default="C0"); ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--duration", type=float, default=300); ap.add_argument("--warmup", type=float, default=20)
    ap.add_argument("--out", default="/data")
    a = ap.parse_args()
    rclpy.init(); n = Recorder()
    t_end = time.time() + a.warmup + a.duration; t_start = time.time() + a.warmup
    started = False
    while rclpy.ok() and time.time() < t_end:
        rclpy.spin_once(n, timeout_sec=0.1)
        if not started and time.time() >= t_start:        # discard the warm-up period
            n.t_js.clear(); n.err.clear(); n.clock.clear(); started = True
    t = np.asarray(n.t_js, dtype=np.float64) / 1e6
    d = np.diff(t)                                           # inter-arrival times (ms)
    rtf = np.nan
    if len(n.clock) > 2:
        (w0, s0), (w1, s1) = n.clock[0], n.clock[-1]
        rtf = (s1 - s0) / ((w1 - w0) / 1e9)
    minutes = a.duration / 60
    summary = dict(cond=a.cond, run=a.run, n=int(len(d)),
                   mean_ms=float(d.mean()) if len(d) else None,
                   sigma_J_ms=float(d.std(ddof=1)) if len(d) > 1 else None,
                   p99_ms=float(np.percentile(d, 99)) if len(d) else None,
                   misses_per_min=float((d > 1.5 * TC_MS).sum() / minutes) if len(d) else None,
                   rmse_rad=float(np.sqrt(np.mean(np.square(n.err)))) if n.err else None,
                   rtf=float(rtf), valid=bool(rtf >= 0.99) if not math.isnan(rtf) else None)
    base = f"{a.out}/{a.cond}_run{a.run}"
    np.savetxt(f"{base}_intervals.csv", d, fmt="%.4f", header="interval_ms", comments="")
    json.dump(summary, open(f"{base}_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
