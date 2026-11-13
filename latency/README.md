# 지연시간 측정 (원고 V-D절, 표 XII·XIII)

연구실 PC에서 Docker 컨테이너를 **CPU 1코어·메모리 2GB**로 제한하고, Kaggle에서 학습한 모델의 **batch-1 추론 지연**을 잽니다.
워밍업 1,000회 후 100,000회 측정하고 p50/p95/p99를 μs 단위로 기록합니다.

## 준비
1. Kaggle 결과 `results` 폴더를 `D:\IIoT 원격 제어 NW IDS\06_결과\edge`에 풉니다. 그러면 `06_결과\edge\models\`가 생깁니다.
2. Docker Desktop을 실행해 둡니다.
3. 노트북 PC는 **전원 연결** 상태로 두고, Windows 전원 모드를 **최고 성능**으로 설정합니다. 측정 중에는 다른 무거운 프로그램을 끕니다.

## 실행 (PowerShell, 이 폴더에서)
```
powershell -ExecutionPolicy Bypass -File .\run_latency.ps1 -Dataset edge
```
- 첫 실행에서는 이미지를 빌드하느라 3~5분이 걸리고, 측정 자체는 모델 7개 기준 약 20~40분입니다.
- 결과는 `06_결과\edge\latency_edge.csv`에 저장됩니다(모델, p50_us, p95_us, p99_us, mean_us, size_kB, forward_ratio).
- 같은 방법으로 `-Dataset rosids`, `-Dataset rospace`를 실행합니다.

## 측정 방식 (원고와 일치)
- 전처리(인코딩·스케일링)는 미리 한 번 적용하고 시간을 따로 기록합니다(`preprocess_us`).
- 모든 모델을 단일 스레드로 실행합니다. LightGBM과 XGBoost는 각 라이브러리의 네이티브 예측 API를 쓰고, 랜덤포레스트와 결정트리는 scikit-learn `predict`를 씁니다.
- 제안 캐스케이드는 Stage 1 확률이 τ* 이상일 때만 Stage 2를 호출합니다. `forward_ratio`가 식 (5)의 r입니다.
- 1D-CNN은 ONNX Runtime으로 FP32와 INT8을 각각 측정합니다.

## 문제 해결
| 증상 | 조치 |
|---|---|
| joblib 로드 오류 (버전 불일치) | Kaggle 노트북 새 셀에서 `import sklearn, lightgbm, xgboost, imblearn; print(sklearn.__version__, lightgbm.__version__, xgboost.__version__, imblearn.__version__)`을 실행해 버전을 확인한 뒤, `docker build --build-arg SKLEARN=x.y.z --build-arg LGBM=... --build-arg XGB=... --build-arg IMBL=... -t ids-latency .`로 다시 빌드 |
| `--cpuset-cpus=2` 오류 | 스크립트의 `--cpuset-cpus=2`를 `0`으로 바꿔 실행 |
| 경로 오류 | `run_latency.ps1` 맨 위 `$Root` 경로 확인 |

## 측정 장비 (원고 표에 기재)
Intel Core Ultra 7 258V (8코어: P 4 + LP-E 4), 32 GB RAM, Windows 11 Home (빌드 26200), WSL2 + Docker 29.8.0.
하이브리드 CPU라서 결과를 해석할 때 컨테이너가 고정된 코어의 종류(P/E)에 따라 값이 달라질 수 있습니다. 원고에는 "1 vCPU pinned within a WSL2 VM"으로 적습니다.
