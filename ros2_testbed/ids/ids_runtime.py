"""Online IDS for the ROS 2 testbed (conditions C1/C3, manuscript Section V-E).
Runs in the network namespace of the simulation container (network_mode service:sim), i.e. it sees every
packet to and from the robot controller, as a mirror port of the controller's switch port would.
Packets -> bidirectional flows (CICFlowMeter-style features, the ROSIDS23 feature set) -> exported flow is
classified by the exported cascade pipeline. Per-flow inference time and alerts are logged.
Usage: python ids_runtime.py --models /models --dataset rosids --tag C1_run1 --seconds 330"""
import argparse, json, os, signal, sys, time, threading
import numpy as np, pandas as pd, joblib
import __main__
from cascade_def import Cascade
__main__.Cascade = Cascade


def signed_log1p(a):
    return np.sign(a) * np.log1p(np.abs(a))


__main__.signed_log1p = signed_log1p
from scapy.all import AsyncSniffer, IP, TCP, UDP   # noqa: E402

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")


def _st(a):
    a = np.asarray(a, dtype=float)
    return (a.mean(), a.std(ddof=1) if len(a) > 1 else 0.0, a.max(), a.min()) if len(a) else (0.0, 0.0, 0.0, 0.0)


class Flow:
    __slots__ = ("key", "t0", "t_last", "ts", "fwd", "bwd", "fwd_ts", "bwd_ts", "fh", "bh", "flags", "init_fw", "init_bw", "dport", "proto")

    def __init__(self, key, t, dport, proto):
        self.key, self.t0, self.t_last = key, t, t
        self.ts, self.fwd, self.bwd, self.fwd_ts, self.bwd_ts = [], [], [], [], []
        self.fh = self.bh = 0; self.flags = dict(FIN=0, SYN=0, RST=0, PSH=0, ACK=0, URG=0)
        self.init_fw = self.init_bw = -1; self.dport, self.proto = dport, proto

    def features(self):
        us = 1e6
        dur = max(self.t_last - self.t0, 1e-6) * us
        allp = self.fwd + self.bwd
        f = {"Flow Duration": dur, "Tot Fwd Pkts": len(self.fwd), "Tot Bwd Pkts": len(self.bwd),
             "TotLen Fwd Pkts": sum(self.fwd), "TotLen Bwd Pkts": sum(self.bwd),
             "Dst Port": self.dport, "Protocol": self.proto,
             "Fwd Header Len": self.fh, "Bwd Header Len": self.bh,
             "Init Fwd Win Byts": self.init_fw, "Init Bwd Win Byts": self.init_bw,
             "Flow Byts/s": sum(allp) / dur * us, "Flow Pkts/s": len(allp) / dur * us,
             "Fwd Pkts/s": len(self.fwd) / dur * us, "Bwd Pkts/s": len(self.bwd) / dur * us,
             "Down/Up Ratio": len(self.bwd) / max(len(self.fwd), 1),
             "Fwd Act Data Pkts": sum(1 for x in self.fwd if x > 0)}
        for name, arr in (("Fwd Pkt Len", self.fwd), ("Bwd Pkt Len", self.bwd), ("Pkt Len", allp)):
            m, s, mx, mn = _st(arr)
            f.update({f"{name} Mean": m, f"{name} Std": s, f"{name} Max": mx, f"{name} Min": mn})
        f["Pkt Len Var"] = f["Pkt Len Std"] ** 2; f["Pkt Size Avg"] = f["Pkt Len Mean"]
        f["Fwd Seg Size Avg"] = f["Fwd Pkt Len Mean"]; f["Bwd Seg Size Avg"] = f["Bwd Pkt Len Mean"]
        for name, ts in (("Flow IAT", self.ts), ("Fwd IAT", self.fwd_ts), ("Bwd IAT", self.bwd_ts)):
            iat = np.diff(ts) * us if len(ts) > 1 else []
            m, s, mx, mn = _st(iat)
            f.update({f"{name} Mean": m, f"{name} Std": s, f"{name} Max": mx, f"{name} Min": mn})
            if name != "Flow IAT":
                f[f"{name} Tot"] = float(np.sum(iat)) if len(iat) else 0.0
        for k, v in self.flags.items():
            f[f"{k} Flag Cnt"] = v
        return f


class IDS:
    def __init__(self, a):
        meta = json.load(open(f"{a.models}/{a.dataset}_meta.json"))
        self.cols, self.classes, self.benign = meta["features"], meta["classes"], meta["benign"]
        self.pipe = joblib.load(f"{a.models}/{a.dataset}_cascade_pipeline.joblib")
        self.pre, c = self.pipe.named_steps["pre"], self.pipe.named_steps["clf"]
        # native single-thread inference, as in the latency benchmark (Stage 2 only for forwarded flows)
        self.b1, self.tau, self.inv, self.ben_idx = c.s1_.booster_, c.tau_, c.inv_, c.benign
        s2 = c.s2_
        if hasattr(s2, "get_booster"):
            bst = s2.get_booster(); bst.set_param({"nthread": 1, "device": "cpu"})
            self.s2 = lambda x, b=bst: np.asarray(b.inplace_predict(x))
        else:
            self.s2 = lambda x, m=s2: np.asarray(m.predict_proba(x))
        self.idle, self.active = a.idle, a.active
        self.flows, self.lock = {}, threading.Lock()
        self.rows, self.n_pkts, self.missing, self.src_of = [], 0, set(), {}

    def on_pkt(self, p):
        if IP not in p:
            return
        t = float(p.time); ip = p[IP]; self.n_pkts += 1
        l4 = TCP if TCP in p else UDP if UDP in p else None
        sp, dp = (p[l4].sport, p[l4].dport) if l4 else (0, 0)
        a, b = (ip.src, sp), (ip.dst, dp)
        key = (min(a, b), max(a, b), ip.proto)
        size = len(p[l4].payload) if l4 else len(ip.payload)
        hdr = ((p[TCP].dataofs or 5) * 4) if l4 is TCP else (8 if l4 is UDP else 0)
        with self.lock:
            fl = self.flows.get(key)
            if fl is None:
                fl = self.flows[key] = Flow(key, t, dp, ip.proto)
                self.src_of[key] = a                               # direction of the first packet = forward
            fwd = self.src_of.get(key) == a
            fl.t_last = t; fl.ts.append(t)
            if fwd:
                fl.fwd.append(size); fl.fwd_ts.append(t); fl.fh += hdr
            else:
                fl.bwd.append(size); fl.bwd_ts.append(t); fl.bh += hdr
            if l4 is TCP:
                fg = int(p[TCP].flags)
                for bit, name in ((1, "FIN"), (2, "SYN"), (4, "RST"), (8, "PSH"), (16, "ACK"), (32, "URG")):
                    fl.flags[name] += bool(fg & bit)
                if fwd and fl.init_fw < 0: fl.init_fw = p[TCP].window
                if not fwd and fl.init_bw < 0: fl.init_bw = p[TCP].window
                if fg & 0x05:                                   # FIN or RST ends the flow
                    self.export(key)

    def export(self, key, now=None):
        fl = self.flows.pop(key, None)
        if fl is None:
            return
        self.src_of.pop(key, None)
        f = fl.features()
        row = {}
        for c in self.cols:
            if c not in f:
                self.missing.add(c)
            row[c] = f.get(c, 0.0)
        X = pd.DataFrame([row], columns=self.cols)
        t0 = time.perf_counter_ns()
        x = np.ascontiguousarray(self.pre.transform(X), dtype=np.float32)
        t1 = time.perf_counter_ns()
        if self.b1.predict(x, num_threads=1)[0] >= self.tau:
            pr = self.s2(x).reshape(1, -1)
            y = int(self.inv[int(pr.argmax(1)[0])]) if pr.shape[1] > 1 else int(self.inv[int(pr[0, 0] >= 0.5)])
        else:
            y = self.ben_idx
        t2 = time.perf_counter_ns(); dt = (t2 - t1) / 1e3; pre_us = (t1 - t0) / 1e3
        label = self.classes[y]
        self.rows.append(dict(t=time.time(), proto=fl.proto, dport=fl.dport, pkts=len(fl.ts), label=label, infer_us=dt, preprocess_us=pre_us,
                              alert_delay_ms=(time.time() - fl.t0) * 1e3))

    def sweep(self):
        now = time.time()
        with self.lock:
            for k, fl in list(self.flows.items()):
                if now - fl.t_last > self.idle or now - fl.t0 > self.active:
                    self.export(k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="/models"); ap.add_argument("--dataset", default="rosids")
    ap.add_argument("--tag", default="C1_run1"); ap.add_argument("--seconds", type=float, default=330)
    ap.add_argument("--iface", default="eth0"); ap.add_argument("--idle", type=float, default=1.0)
    ap.add_argument("--active", type=float, default=5.0); ap.add_argument("--out", default="/data")
    a = ap.parse_args()
    ids = IDS(a)
    sn = AsyncSniffer(iface=a.iface, store=False, prn=ids.on_pkt); sn.start()
    t_end = time.time() + a.seconds; c0 = time.process_time(); w0 = time.time()
    stop = {"x": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(x=True)); signal.signal(signal.SIGINT, lambda *_: stop.update(x=True))
    while time.time() < t_end and not stop["x"]:
        time.sleep(0.2); ids.sweep()
    sn.stop()
    with ids.lock:
        for k in list(ids.flows):
            ids.export(k)
    cpu = (time.process_time() - c0) / max(time.time() - w0, 1e-6) * 100
    df = pd.DataFrame(ids.rows); df.to_csv(f"{a.out}/{a.tag}_ids_flows.csv", index=False)
    inf = df["infer_us"].to_numpy() if len(df) else np.array([np.nan])
    summ = dict(tag=a.tag, packets=ids.n_pkts, flows=int(len(df)), cpu_percent=round(cpu, 1),
                infer_p50_us=float(np.nanpercentile(inf, 50)), infer_p99_us=float(np.nanpercentile(inf, 99)),
                preprocess_p50_us=float(df["preprocess_us"].median()) if len(df) else None,
                labels=df["label"].value_counts().to_dict() if len(df) else {},
                first_alert_s=(float(df.loc[df.label != ids.benign, "t"].min() - w0) if len(df) and (df.label != ids.benign).any() else None),
                missing_features=sorted(ids.missing))
    json.dump(summ, open(f"{a.out}/{a.tag}_ids_summary.json", "w"), indent=1); print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
