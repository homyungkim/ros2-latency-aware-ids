# IDS container for conditions C1/C3: same library versions as Kaggle (models unpickle unchanged)
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libpcap0.8 procps && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy pandas pyarrow joblib scapy \
    "scikit-learn==1.6.1" "lightgbm==4.6.0" "xgboost==3.4.1" "imbalanced-learn==0.14.2"
COPY ids_runtime.py cascade_def.py /app/
WORKDIR /app
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
CMD ["sleep", "infinity"]
