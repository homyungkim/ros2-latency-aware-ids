# ROS 2 제어 루프 테스트베드 (원고 V-E절, 표 XIII, 그림 6·8)

ROS 2 Jazzy + Gazebo Harmonic(헤드리스) + UR5e + ros2_control 500 Hz를 Docker 컨테이너로 실행합니다.
외부와 격리된 브리지 네트워크 하나에 컨테이너 4개(sim, teleop, ids, attacker)를 둡니다.

## 단계
| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 시뮬레이션(sim) + 원격조작(teleop) + 기록기(recorder) → **조건 C0** | 이번에 제공 |
| 2 | 온라인 IDS(ids), 공격 재현(attacker) → 조건 C1·C2·C3 | Kaggle 결과(모델) 확인 후 제공 |

## 1단계 실행 (PowerShell, 이 폴더에서)
1. 이미지 빌드(최초 1회, 10~20분, 약 3~4 GB):
   `docker compose build`
2. 동작 확인:
   ```
   docker compose up -d sim teleop
   Start-Sleep 40
   powershell -ExecutionPolicy Bypass -File .\check.ps1
   ```
   - `joint_trajectory_controller`와 `joint_state_broadcaster`가 **active**인지
   - `update_rate`가 **500**인지
   - `/joint_states`의 average rate가 약 **500**인지
   확인한 뒤 `docker compose down`
3. 시험 1회(5분): `powershell -ExecutionPolicy Bypass -File .\run_c0.ps1 -Runs 1`
   → `runs\C0_run1_summary.json`에 σ_J, p99 간격, 분당 데드라인 미스, RMSE, RTF가 기록됩니다.
4. 정상이면 본 측정 10회: `run_c0.ps1 -Runs 10` (약 1시간)

## 기록 항목 (원고 식과 일치)
- `/joint_states` 도착 간격 Δt_i (벽시계 기준) → σ_J(jitter), p99, Miss = Σ𝕀[Δt_i > 1.5 T_c], T_c = 2 ms
- 추종 오차 RMSE: `/joint_trajectory_controller/controller_state`의 error.positions
- 실시간 비율 RTF: `/clock`(시뮬레이션 시간) ÷ 벽시계. RTF < 0.99인 실행은 `valid: false`로 표시하고 제외
- 시작 후 20초는 워밍업으로 버립니다.

## 측정 조건
전원 연결, Windows 전원 모드 **최고 성능**, 다른 무거운 프로그램 종료. 지연시간 측정과 동시에 돌리지 않습니다.

## 문제 해결
| 증상 | 조치 |
|---|---|
| 빌드 중 패키지를 찾지 못함 | `docker compose build --no-cache` 재시도, 오류 마지막 20줄 공유 |
| 컨트롤러가 active가 아님 | `docker compose logs sim`의 마지막 50줄 공유 |
| `/joint_states` rate가 500보다 크게 낮음 | RTF 확인(`ros2 topic hz /clock`), 다른 프로그램 종료 |

## Step 2: conditions C1-C3 (IDS and attacks)

| Condition | Containers | Command |
|---|---|---|
| C1 IDS only | sim, teleop, ids | `powershell -ExecutionPolicy Bypass -File .\run_c123.ps1 -Cond C1 -Runs 10` |
| C2 attack only | sim, teleop, attacker | `... -Cond C2 -Attack dos -Runs 5` |
| C3 attack + IDS | sim, teleop, ids, attacker | `... -Cond C3 -Attack dos -Runs 5` |

* `ids` runs in the network namespace of `sim` (`network_mode: service:sim`), so it sees all traffic of the
  robot controller, like a mirror port. It is limited to 1 CPU and 2 GB (edge-class budget).
* `ids/ids_runtime.py`: packets -> bidirectional flows (CICFlowMeter-style features of ROSIDS23, idle 1 s /
  active 5 s timeouts) -> exported cascade from `06_결과/rosids/models`. Logs per-flow preprocessing and
  inference time, labels, first alert time and CPU use (`runs/<tag>_ids_flows.csv`, `_ids_summary.json`).
* Attacks (`nodes/attack.sh`): `dos` UDP flood (~10k pkt/s) to the DDS port of sim, `pub` forged trajectory
  goals at 2 Hz (unauthorized publish), `subflood` 100 rogue subscriptions to /joint_states.
* Note: the detector is trained on ROSIDS23 (ROS 1 / TCPROS traffic); the testbed runs ROS 2 / DDS over UDP.
  C1/C3 therefore measure the resource and timing impact of running the detector on live traffic; detection
  results in the testbed are reported as observed, not as an accuracy claim.
