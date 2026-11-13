"""Batch-1 inference latency of the exported models (manuscript Section V-D, Tables XII-XIII).

Run inside the resource-limited container (1 CPU core, 2 GB RAM), see README.md:
    python measure_latency.py --models /work/models --dataset edge

For every model it times single-record prediction on preprocessed inputs:
1,000 warm-up calls, then N timed calls (default 100,000) with time.perf_counter_ns.
Preprocessing (encoding/scaling) is applied once beforehand and timed separately.
Output: latency_<dataset>.csv  (model, p50_us, p95_us, p99_us, mean_us, size_kB, forward_ratio)
"""
import argparse, json, os, platform, time, glob
import numpy as np
import pandas as pd
import joblib
import __main__
from cascade_def import Cascade
__main__.Cascade = Cascade   # the notebook pickled the cascade as __main__.Cascade


def signed_log1p(a):
    """Same transform as the notebook; the CNN preprocessor was pickled as __main__.signed_log1p."""
    return np.sign(a) * np.log1p(np.abs(a))


__main__.signed_log1p = signed_log1p

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")


def stats(ns):
    us = np.asarray(ns, dtype=np.float64) / 1e3
    return dict(p50_us=np.percentile(us, 50), p95_us=np.percentile(us, 95),
                p99_us=np.percentile(us, 99), mean_us=us.mean())


def throughput(fn, X, batch, seconds=2.0):
    """Records/s at a given batch size (single thread), measured over ~`seconds` of repeated calls."""
    import time as _t
    idx = np.random.default_rng(1).integers(0, len(X), size=batch)
    xb = np.ascontiguousarray(X[idx]); fn(xb)                      # warm up
    n, t0 = 0, _t.perf_counter()
    while _t.perf_counter() - t0 < seconds:
        fn(xb); n += batch
    return n / (_t.perf_counter() - t0)


def peak_rss_mb():
    """Peak resident set size of this process so far (MB). Linux VmHWM."""
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    import resource
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def time_calls(fn, X, n, warmup):
    idx = np.random.default_rng(0).integers(0, len(X), size=n + warmup)
    for i in idx[:warmup]:
        fn(X[i:i + 1])
    out = np.empty(n, dtype=np.int64)
    for k, i in enumerate(idx[warmup:]):
        x = X[i:i + 1]
        t0 = time.perf_counter_ns(); fn(x); out[k] = time.perf_counter_ns() - t0
    return out


def file_kb(*paths):
    return round(sum(os.path.getsize(p) for p in paths if p and os.path.exists(p)) / 1024, 1)


def single_thread(clf):
    for attr in ("n_jobs",):
        if hasattr(clf, attr):
            try: clf.set_params(**{attr: 1})
            except Exception: pass
    if hasattr(clf, "get_booster"):          # XGBoost: CPU, one thread
        try: clf.set_params(device="cpu", nthread=1)
        except Exception: pass
    return clf


def fast_predict(clf):
    """Native single-thread inference API where the library offers one (same rule for every model):
    LightGBM Booster.predict, XGBoost inplace_predict; scikit-learn models use predict."""
    if hasattr(clf, "booster_"):                                   # LightGBM sklearn wrapper
        b = clf.booster_
        return lambda x, b=b: b.predict(x, num_threads=1)
    if hasattr(clf, "get_booster"):                                # XGBoost sklearn wrapper
        b = clf.get_booster(); b.set_param({"nthread": 1, "device": "cpu"})
        return lambda x, b=b: b.inplace_predict(x)
    return clf.predict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="/work/models")
    ap.add_argument("--dataset", default="edge")
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--warmup", type=int, default=1_000)
    ap.add_argument("--out", default="/work")
    a = ap.parse_args()
    M, D = a.models, a.dataset
    meta = json.load(open(f"{M}/{D}_meta.json"))
    recs = pd.read_parquet(f"{M}/{D}_latency_test_records.parquet")
    print(f"{D}: {len(recs)} test records, {recs.shape[1]} features; python {platform.python_version()}")
    rows = []

    # ---- tree models and the cascade (sklearn/imblearn pipelines) ----
    for path in sorted(glob.glob(f"{M}/{D}_*.joblib")):
        name = os.path.basename(path)[len(D) + 1:-7]
        if name in ("cnn_preprocessor",):
            continue
        kb = os.path.getsize(path) / 1024
        try:
            pipe = joblib.load(path)
        except (MemoryError, Exception) as e:   # e.g. a model too large to load in the edge-class container
            rows.append(dict(model=name.replace("_", " "), p50_us=np.nan, p95_us=np.nan, p99_us=np.nan,
                             mean_us=np.nan, size_kB=round(kb, 1), forward_ratio=np.nan, preprocess_us=np.nan))
            print("skipped (load failed):", name, repr(e)[:80]); continue
        pre = pipe.named_steps["pre"]; clf = single_thread(pipe.named_steps["clf"])
        t0 = time.perf_counter(); X = np.ascontiguousarray(pre.transform(recs), dtype=np.float32)
        pre_us = (time.perf_counter() - t0) / len(recs) * 1e6
        if name == "cascade_pipeline":
            b1, tau = clf.s1_.booster_, clf.tau_
            s2 = fast_predict(clf.s2_)
            def fn(x, b1=b1, s2=s2, tau=tau):
                if b1.predict(x, num_threads=1)[0] >= tau:     # Stage 1: P(attack)
                    return s2(x)                                 # Stage 2 only for forwarded records
                return None
            r = float((b1.predict(X, num_threads=1) >= tau).mean())
            label = "Proposed cascade"
            # component times for the expected-latency model E[T] = t1 + r * t2 (any benign share)
            ns1 = time_calls(lambda x, b1=b1: b1.predict(x, num_threads=1), X, a.n, a.warmup)
            ns2 = time_calls(s2, X, a.n, a.warmup)
            rows.append(dict(model="Cascade Stage 1 only (t1)", **stats(ns1), size_kB=np.nan, forward_ratio=np.nan, preprocess_us=pre_us))
            rows.append(dict(model="Cascade Stage 2 only (t2)", **stats(ns2), size_kB=np.nan, forward_ratio=np.nan, preprocess_us=pre_us))
            print(rows[-2]); print(rows[-1])
        else:
            fn, r, label = fast_predict(clf), np.nan, name.replace("_", " ")
        ns = time_calls(fn, X, a.n, a.warmup)
        thr = throughput(fn, X, 64)
        rows.append(dict(model=label, **stats(ns), size_kB=file_kb(path), forward_ratio=r, preprocess_us=pre_us,
                         rss_mb=peak_rss_mb(), thr_b64=round(thr)))
        print(rows[-1])

    # ---- 1D-CNN via ONNX Runtime (FP32 and INT8), one thread ----
    try:
        import onnxruntime as ort
        if not os.path.exists(f"{M}/{D}_cnn_preprocessor.joblib"):
            raise FileNotFoundError("CNN preprocessor not exported")
        pre = joblib.load(f"{M}/{D}_cnn_preprocessor.joblib")
        X = np.ascontiguousarray(pre.transform(recs), dtype=np.float32)
        so = ort.SessionOptions(); so.intra_op_num_threads = 1; so.inter_op_num_threads = 1
        p32, p8 = f"{M}/{D}_cnn_fp32.onnx", f"{M}/{D}_cnn_int8.onnx"
        if os.path.exists(p32) and not os.path.exists(p8):
            # INT8 model not exported on Kaggle: quantize the FP32 model here (dynamic, weights INT8)
            from onnxruntime.quantization import quantize_dynamic, QuantType
            p8 = f"{a.out}/{D}_cnn_int8_local.onnx"
            quantize_dynamic(p32, p8, weight_type=QuantType.QInt8)
            print("INT8 model quantized locally (dynamic):", p8)
        for prec, p in (("fp32", p32), ("int8", p8)):
            if not os.path.exists(p):
                print("missing", p); continue
            sess = ort.InferenceSession(p, so, providers=["CPUExecutionProvider"])
            fn = lambda x, s=sess: s.run(None, {"x": x})
            ns = time_calls(fn, X, a.n, a.warmup)
            rows.append(dict(model=f"1D-CNN ({prec.upper()}, ONNX)", **stats(ns), size_kB=file_kb(p), forward_ratio=np.nan))
            print(rows[-1])
    except Exception as e:   # never lose the tree-model rows because of the CNN part
        print("1D-CNN skipped:", repr(e))

    df = pd.DataFrame(rows).round(2)
    out = f"{a.out}/latency_{D}.csv"; df.to_csv(out, index=False)
    print(df.to_string(index=False)); print("saved", out)


if __name__ == "__main__":
    main()
