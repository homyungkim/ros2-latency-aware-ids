# ROS 1 (Noetic) control-loop testbed

Companion to `../ros2_testbed`. Same UR5e arm, same pick-and-place teleoperation, same control-quality metrics
(jitter, deadline misses, RMSE, RTF), but ROS 1 / **TCPROS** traffic.

**Why a second testbed.** The detector is trained on ROSIDS23, which is ROS 1 / TCPROS. The ROS 2 testbed runs
DDS/UDP, so there its detection output is only indicative. Here the traffic matches the training domain, so the
IDS detection results (detection delay, false alarms) are a genuine test — this is the testbed that backs the
"latency-aware" detection claim.

## Conditions
| Condition | Containers | Command |
|---|---|---|
| R1_C0 baseline | sim, teleop | `powershell -ExecutionPolicy Bypass -File .\run_r1.ps1 -Cond R1_C0 -Runs 5` |
| R1_C1 IDS only | + ids | `... -Cond R1_C1 -Runs 5` |
| R1_C2 attack only | + attacker | `... -Cond R1_C2 -Attack dos -Runs 5` |
| R1_C3 attack + IDS | + ids + attacker | `... -Cond R1_C3 -Attack dos -Runs 5` |

Attacks (`nodes/attack.sh`, ROSIDS23 classes): `dos` SYN flood on the ROS master (~10k/s), `pub` forged
trajectory commands at 2 Hz, `sub` unauthorized subscribe, `subflood` 100 rogue subscriptions to /joint_states.
Each attack starts 60 s into the run (benign period first) and writes its start time to
`runs/<tag>_attack_start.txt`.

## Pieces
* `docker/Dockerfile` — ros:noetic-robot + ur_gazebo + ros_control (built as `ids-ros1:noetic`).
* `nodes/sim.sh` — roscore + headless Gazebo Classic + UR5e, effort joint-trajectory controller, /joint_states
  at 500 Hz.
* `nodes/teleop.py`, `nodes/recorder.py` — same trajectory and metrics as the ROS 2 testbed.
* `ids/` — the same online detector as the ROS 2 testbed (packets → flows → cascade from `06_결과/rosids/models`),
  1 CPU / 2 GB. Runs in the sim network namespace (mirror of the controller port).
* `run_r1.ps1` — runs a condition N times and prints the control-quality and IDS summaries.
* `analyze_detection.py` — after R1_C3, pairs each run's IDS flow log with its attack-start time and reports
  detection delay and pre-attack false alarms (`runs/detection_summary.csv`).

## Order
1. `run_r1.ps1 -Cond R1_C0 -Runs 5` — confirm 500 Hz baseline holds (RTF ≥ 0.99).
2. `run_r1.ps1 -Cond R1_C1 -Runs 5` — IDS impact on control timing.
3. `run_r1.ps1 -Cond R1_C2 -Attack dos -Runs 5` and `-Cond R1_C3 -Attack dos -Runs 5`; repeat for pub / subflood.
4. `python analyze_detection.py` — detection delay and false alarms.

The final cascade models come from the v12.1 Kaggle run (`06_결과/rosids/models`); until that is in place the IDS
container falls back to whatever is in that folder, so run the detection conditions only after the models are updated.
