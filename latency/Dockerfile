# Inference-only image for the latency benchmark (Section V-D).
# Library versions must match the Kaggle training environment so that the joblib files load;
# set them with --build-arg (see README.md) if loading fails.
FROM python:3.13-slim
ARG SKLEARN="1.6.1"
ARG LGBM="4.6.0"
ARG XGB="3.4.1"
ARG IMBL="0.14.2"
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy pandas pyarrow joblib onnx onnxruntime \
    "scikit-learn${SKLEARN:+==$SKLEARN}" "lightgbm${LGBM:+==$LGBM}" "xgboost${XGB:+==$XGB}" \
    "imbalanced-learn${IMBL:+==$IMBL}"
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
WORKDIR /work
COPY measure_latency.py cascade_def.py /app/
ENV PYTHONPATH=/app
ENTRYPOINT ["python", "/app/measure_latency.py"]
