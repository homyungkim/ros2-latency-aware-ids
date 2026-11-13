# Latency-Aware Lightweight Intrusion Detection for ROS 2 Robotic Arm Remote Control

Code accompanying the paper

> H. M. Kim and J. Jang, "Latency-Aware Lightweight Intrusion Detection for ROS 2-Based Robotic Arm Remote Control in IIoT Networks," submitted to *IEEE Access*, 2026.

Department of AI Software, Kyungwoon University, Gumi, South Korea.

## Contents

| Folder | What it holds |
|---|---|
| `notebooks/` | `ids_experiments.ipynb` — leakage-free evaluation, cascade IDS, baselines, ablation, LOAO, SHAP, model export (run on Kaggle) |
| `scripts/data_prep/` | `rospace_sample.py` — class-stratified sample of ROSPaCe_reduced |
| `scripts/figures/` | figure scripts for the manuscript |
| `latency/` | batch-1 latency measurement on a 1-core / 2 GB container (lab workstation) |
| `ros2_testbed/` | ROS 2 Jazzy + Gazebo Harmonic UR5e testbed (Docker Compose) |
| `results/` | summary CSV files reported in the paper (added after acceptance) |
| `data/` | empty — datasets are **not** redistributed; see below |

## Datasets (download from the original sources)

| Dataset | Source |
|---|---|
| Edge-IIoTset | https://www.kaggle.com/datasets/mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot |
| ROSIDS23 | https://zenodo.org/records/10014434 (`ROSIDS23.csv`) |
| ROSPaCe (reduced) | https://springernature.figshare.com/articles/dataset/ROSPaCe_reduced/25594860 |

## Reproducing the results

1. ROSPaCe: `python scripts/data_prep/rospace_sample.py <extracted_folder> 600000`
2. Upload the data to Kaggle, import `notebooks/ids_experiments.ipynb`, set `DATASET` (`edge` / `rosids` / `rospace`), and run with a GPU.
3. Copy `results/models/` to the workstation and run the latency scripts in `latency/`.

Protocol: identifiers removed, deduplication before splitting, stratified 5-fold × 5 seeds, SMOTE and scaling fitted on training folds only, hyperparameters tuned on seed-0 training folds and then fixed.

## Requirements

Python 3.10+, see `requirements.txt`.

## Citation

See `CITATION.cff`. The citation will be updated with the DOI after publication.

## License

Code: MIT (see `LICENSE`). The datasets keep their original licenses.

## Acknowledgment

Supported by the ANCHOR program through the Gyeongbuk ANCHOR Center, funded by the Ministry of Education (MOE) and Gyeongsangbuk-do, Republic of Korea (2026-ANCHOR-15-102).
