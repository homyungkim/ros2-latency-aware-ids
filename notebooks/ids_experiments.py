# %% [markdown]
# # Latency-aware lightweight IDS — Kaggle experiment notebook
# Run once per dataset by changing `DATASET` in the settings cell.
# Produces the CSV files used to fill Tables VIII–XI and Figs. 7 and 9 of the manuscript,
# and exports the models measured on the lab workstation (Tables XII–XIII).
#
# Order of experiments: E1 baselines → cascade → E2 leakage → E3 ablation → E5 leave-one-attack-out
# → E6 SHAP → DL baselines (GPU) → export.

# %% Settings ---------------------------------------------------------------
import os, re, glob, json, time, warnings
DATASET = "edge"          # "edge" (Edge-IIoTset) | "rosids" (ROSIDS23) | "rospace" (ROSPaCe)
QUICK = os.environ.get("IDS_QUICK") == "1"             # True: 1 seed x 3 folds on a 20% sample, to check the pipeline end to end (~5-10 min)
SEEDS = [0, 1, 2, 3, 4]
N_FOLDS = 5
SMOTE_TARGET = 20000      # minority classes are oversampled up to this many training records (training fold only)
ROSPACE_MAX_ROWS = 700_000  # cap for ROSPaCe; the uploaded stratified sample (~631k rows) is used whole
K_CANDIDATES = [10, 15, 20, 30]
DELTA = 0.005             # tolerated macro-F1 loss when choosing k (eq. 3)
DELTA_TUNE = 0.005        # tolerated inner macro-F1 loss when choosing the cheapest configuration (latency-aware tuning)
PI_DEPLOY = 0.9           # benign share assumed for the expected-latency proxy during tuning (normal operation)
RHO = 0.995               # Stage 1 recall target (eq. 4)
OUT = os.environ.get("IDS_OUT", "/kaggle/working/results")
INPUT_ROOT = os.environ.get("IDS_INPUT", "/kaggle/input")
print("ids_experiments v12.2 (latency-aware tuning; ROSPaCe payload/identifier drops) | DATASET =", DATASET)

import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
os.makedirs(OUT, exist_ok=True)
os.makedirs(f"{OUT}/models", exist_ok=True)
if QUICK:
    SEEDS, N_FOLDS = [0], 3

# %% Dataset configuration --------------------------------------------------
# Identifier / environment-specific fields removed in the leakage-free protocol (Section IV-A).
CONFIG = {
    "edge": dict(
        file_pattern="**/ML-EdgeIIoT-dataset.csv",          # ML subset released by the authors
        label="Attack_type", binary_label="Attack_label", benign="Normal",
        drop_ids=["frame.time", "ip.src_host", "ip.dst_host", "arp.src.proto_ipv4", "arp.dst.proto_ipv4",
                  "http.file_data", "http.request.full_uri", "icmp.transmit_timestamp", "http.request.uri.query",
                  "tcp.options", "tcp.payload", "tcp.srcport", "tcp.dstport", "udp.port", "mqtt.msg"],
        id_regex=None),
    "rosids": dict(
        file_pattern="**/*.csv", label=None, binary_label=None, benign=None,   # label column auto-detected
        drop_ids=["Flow ID", "Src IP", "Dst IP", "Src Port", "Timestamp"],
        id_regex=r"(?i)^(flow[ _]?id|src[ _]?ip|dst[ _]?ip|src[ _]?port|timestamp)$"),
    "rospace": dict(
        file_pattern="**/*.csv", label="attack", binary_label=None, benign="observe",   # 'observe' = normal operation
        # drop payloads, raw TCP options, link-layer identifier and verbose Wireshark text (high-cardinality,
        # memorizable or session-specific); keep src_topic / msg_type, which are legitimate ROS 2 protocol features
        drop_ids=["timestamp", "Tcp_TimeWait", "layers.tcp.tcp.payload", "layers.tcp.tcp.options",
                  "layers.sll.sll.unused", "msg_data",
                  "layers.tcp.tcp.flags_tree.tcp.flags.syn_tree._ws.expert._ws.expert.message"],
        id_regex=r"(?i)(time|timestamp|^ip|_ip$|host|mac|addr|payload|\.options$|\.unused$|expert\.message|^msg_data$)"),
}
cfg = CONFIG[DATASET]

# %% Load -------------------------------------------------------------------
files = sorted(glob.glob(os.path.join(INPUT_ROOT, cfg["file_pattern"]), recursive=True))
print("found files:", files[:10], "..." if len(files) > 10 else "")
assert files, "No CSV found: add the dataset to this notebook (Add Input) and check file_pattern."


def read_any(path, nrows=None):
    # Copy to local disk first and parse with the pyarrow engine: reading the full CSV straight from
    # /kaggle/input with the C engine hung or killed the kernel in testing (2026-11 Kaggle image).
    import shutil
    local = os.path.join("/tmp", re.sub(r"[^\w.]", "_", os.path.relpath(path, INPUT_ROOT)))
    if not os.path.exists(local):
        shutil.copy(path, local)
    if nrows is None:
        try:
            return pd.read_csv(local, engine="pyarrow")
        except Exception as e:
            print("pyarrow engine failed, falling back to the C engine:", str(e)[:200])
    return pd.read_csv(local, low_memory=False, nrows=nrows)


if DATASET == "rospace":
    parts, per_file = [], max(1, ROSPACE_MAX_ROWS // max(1, len(files)))
    for f in files:
        d = read_any(f)
        parts.append(d.sample(min(len(d), per_file), random_state=0))
    raw = pd.concat(parts, ignore_index=True)
else:
    raw = pd.concat([read_any(f) for f in files], ignore_index=True) if len(files) > 1 else read_any(files[0])
raw.columns = [c.strip() for c in raw.columns]
print(raw.shape)

# label detection for datasets whose label column name varies by release
if cfg["label"] is None:
    cands = [c for c in raw.columns if c.lower() in ("label", "class", "attack", "attack_type", "category", "is_attack")]
    assert cands, f"Set cfg['label'] manually; columns: {list(raw.columns)[:40]}"
    cfg["label"] = cands[0]
y_raw = raw[cfg["label"]].astype(str).str.strip()
if cfg["benign"] is None:
    cfg["benign"] = next((v for v in y_raw.unique() if v.lower() in ("benign", "normal", "0", "false")), y_raw.value_counts().index[0])
print("label:", cfg["label"], "| benign class:", cfg["benign"])
print(y_raw.value_counts())

if QUICK:
    raw = raw.groupby(y_raw, group_keys=False).apply(lambda d: d.sample(frac=0.2, random_state=0)).reset_index(drop=True)
    y_raw = raw[cfg["label"]].astype(str).str.strip()

# %% Leakage-free preprocessing (Section IV-A) -------------------------------
label_cols = {cfg["label"]} | ({cfg["binary_label"]} if cfg["binary_label"] else set())
id_cols = [c for c in raw.columns if c in cfg["drop_ids"] or (cfg["id_regex"] and re.search(cfg["id_regex"], c))]
id_cols = [c for c in id_cols if c not in label_cols]
print("identifier fields removed:", id_cols)
NET_IDS = [c for c in id_cols if re.search(r"(?i)(src_host|dst_host|proto_ipv4|src[ _]?ip|dst[ _]?ip|ip\.src|ip\.dst|port|_ip$|^ip_|addr|mac)", c)
           and not re.search(r"(?i)(time|payload|uri|file_data|msg|options)", c)]
print("network identifiers retained in L1:", NET_IDS)


def canonical_str(col):
    """String form of a categorical column with numeric spellings unified ("0", "0.0" -> "0.0").
    Edge-IIoTset writes an absent protocol field as "0" in the normal-traffic capture and "0.0" in the attack
    captures, so the raw spelling alone reveals the label (serialisation artifact, Galal 2026, arXiv:2608.15761)."""
    s = col.astype(str).str.strip()
    num = pd.to_numeric(s, errors="coerce")
    return s.where(num.isna(), num.astype(float).map(repr))


def make_xy(df, keep_ids=(), dedup=True):
    """keep_ids: identifier fields to retain (L1 leakage configuration); all others in id_cols are removed."""
    X = df.drop(columns=[c for c in label_cols if c in df.columns])
    X = X.drop(columns=[c for c in id_cols if c in X.columns and c not in set(keep_ids)])
    y = df[cfg["label"]].astype(str).str.strip()
    X = X.replace([np.inf, -np.inf], np.nan)
    const = [c for c in X.columns if X[c].nunique(dropna=False) <= 1]
    X = X.drop(columns=const)
    for c in X.columns:
        if not pd.api.types.is_numeric_dtype(X[c]):
            X[c] = canonical_str(X[c])   # mixed-type columns (e.g. "0" and "GET") become one string category
    n0 = len(X)
    if dedup:
        dup = pd.concat([X, y.rename("__y")], axis=1).duplicated()
        X, y = X[~dup].reset_index(drop=True), y[~dup].reset_index(drop=True)
    return X, y, n0


X, y, n_before = make_xy(raw)
print(f"records: {n_before} -> {len(X)} after deduplication; features: {X.shape[1]}")
cat_cols = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
num_cols = [c for c in X.columns if c not in cat_cols]
print("categorical:", cat_cols)
json.dump({"dataset": DATASET, "records_raw": int(n_before), "records_used": int(len(X)), "features": int(X.shape[1]),
           "removed_ids": id_cols, "classes": y.value_counts().to_dict()}, open(f"{OUT}/{DATASET}_data_summary.json", "w"), indent=1)

# %% Pipeline components ----------------------------------------------------
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OrdinalEncoder, StandardScaler, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import f1_score, matthews_corrcoef, accuracy_score, precision_recall_fscore_support, confusion_matrix
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
import lightgbm as lgb
import xgboost as xgb
# L2 leaf regularization for every LightGBM model. Without it, LightGBM's default (lambda = 0) diverged on
# Edge-IIoTset when SMOTE was not used: leaf values exploded (raw scores ~1e6) and macro-F1 fell to 0.1-0.4 in
# about half of the folds. XGBoost uses lambda = 1 by default, so this also aligns the two libraries.
LGB_L2 = 1.0

try:
    import torch
    GPU = torch.cuda.is_available()
except Exception:
    GPU = False
print("GPU available:", GPU)

le = LabelEncoder().fit(y)
Y = le.transform(y)
BENIGN = int(le.transform([cfg["benign"]])[0])
CLASSES = list(le.classes_)


def signed_log1p(a):
    return np.sign(a) * np.log1p(np.abs(a))


def preprocessor(cols_cat, cols_num, scale=False):
    # scale=True (neural networks): signed log1p for heavy-tailed flow statistics, then standardization
    from sklearn.preprocessing import FunctionTransformer
    num = [("imp", SimpleImputer(strategy="median"))] + (
        [("log", FunctionTransformer(signed_log1p)), ("sc", StandardScaler())] if scale else [])
    return ColumnTransformer([
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("enc", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1))]), cols_cat),
        ("num", Pipeline(num), cols_num)], remainder="drop")


def smote_for(y_train):
    counts = np.bincount(y_train)
    strategy = {c: SMOTE_TARGET for c, n in enumerate(counts) if 6 <= n < SMOTE_TARGET}
    if not strategy:
        return "passthrough"
    k = max(1, min(5, min(counts[c] for c in strategy) - 1))
    return SMOTE(sampling_strategy=strategy, k_neighbors=k, random_state=0)


def metrics(y_true, y_pred):
    benign_mask = y_true == BENIGN
    far = float(np.mean(y_pred[benign_mask] != BENIGN)) if benign_mask.any() else np.nan
    return dict(macro_f1=f1_score(y_true, y_pred, average="macro"), far=far,
                mcc=matthews_corrcoef(y_true, y_pred), acc=accuracy_score(y_true, y_pred))


# %% Cascaded detector (Section IV-C) ----------------------------------------
from sklearn.base import BaseEstimator, ClassifierMixin


class Cascade(BaseEstimator, ClassifierMixin):
    """Stage 1: compact binary LightGBM on all inputs; Stage 2: multi-class model on inputs with p >= tau.
    tau = max{tau : recall_attack(tau) >= rho} on an internal validation split (eq. 4)."""

    def __init__(self, benign=0, rho=RHO, d1=4, n1=80, lr1=0.1, d2=8, n2=200, stage2="xgb", random_state=0):
        self.benign, self.rho, self.d1, self.n1, self.lr1 = benign, rho, d1, n1, lr1
        self.d2, self.n2, self.stage2, self.random_state = d2, n2, stage2, random_state

    def _s2(self):
        if self.stage2 == "xgb":
            return xgb.XGBClassifier(n_estimators=self.n2, max_depth=self.d2, learning_rate=0.1, tree_method="hist",
                                     device="cuda" if GPU else "cpu", random_state=self.random_state, n_jobs=-1)
        return lgb.LGBMClassifier(n_estimators=self.n2, max_depth=self.d2, reg_lambda=LGB_L2, random_state=self.random_state, verbose=-1)

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float32); y = np.asarray(y)
        yb = (y != self.benign).astype(int)
        Xtr, Xva, ytr, yva = train_test_split(X, yb, test_size=0.2, stratify=yb, random_state=self.random_state)
        self.s1_ = lgb.LGBMClassifier(n_estimators=self.n1, max_depth=self.d1, num_leaves=2 ** self.d1 - 1,
                                      learning_rate=self.lr1, reg_lambda=LGB_L2, random_state=self.random_state,
                                      verbose=-1).fit(Xtr, ytr)
        p = self.s1_.predict_proba(Xva)[:, 1]
        pa = np.sort(p[yva == 1])                       # scores of attack samples
        idx = int(np.floor((1 - self.rho) * len(pa)))   # largest tau keeping recall >= rho
        self.tau_ = float(pa[idx]) if len(pa) else 0.5
        self.s1_.fit(X, yb)                             # refit Stage 1 on the whole training fold
        p_all = self.s1_.predict_proba(X)[:, 1]
        sel = (yb == 1) | (p_all >= self.tau_)          # attacks + benign hard negatives
        self.classes_ = np.unique(y)
        self.map_ = {c: i for i, c in enumerate(np.unique(y[sel]))}
        self.inv_ = np.array(list(self.map_.keys()))
        self.s2_ = self._s2().fit(X[sel], np.vectorize(self.map_.get)(y[sel]))
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=np.float32)
        p = self.s1_.predict_proba(X)[:, 1]
        out = np.full(len(X), self.benign)
        fwd = p >= self.tau_
        self.last_forward_ratio_ = float(fwd.mean()); self.last_fwd_ = fwd
        if fwd.any():
            out[fwd] = self.inv_[self.s2_.predict(X[fwd]).astype(int)]
        return out


# %% Model zoo ---------------------------------------------------------------
def model_factory(name, seed):
    if name == "Decision tree":
        return DecisionTreeClassifier(random_state=seed)
    if name == "Random forest":
        return RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=seed)
    if name == "XGBoost":
        return xgb.XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.1, tree_method="hist",
                                 device="cuda" if GPU else "cpu", random_state=seed, n_jobs=-1)
    if name == "LightGBM":
        return lgb.LGBMClassifier(n_estimators=300, num_leaves=63, reg_lambda=LGB_L2, random_state=seed, verbose=-1)
    if name == "Proposed cascade":
        return Cascade(benign=BENIGN, random_state=seed, **BEST)
    raise ValueError(name)


def run_cv(name, Xdf, Yarr, seeds=SEEDS, smote=None, features=None, collect_pred=False):
    """smote: None (= tuned setting SMOTE_MODE), 'in_fold', 'none', or 'before_split' (L2 leakage configuration)."""
    smote = SMOTE_MODE if smote is None else smote
    rows, preds = [], []
    Xdf = Xdf if features is None else Xdf[features]
    cc = [c for c in Xdf.columns if not pd.api.types.is_numeric_dtype(Xdf[c])]; nc = [c for c in Xdf.columns if c not in cc]
    for seed in seeds:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        Xs, Ys = Xdf, Yarr
        if smote == "before_split":                       # deliberately leaky, for Table X only
            pre = preprocessor(cc, nc).fit(Xs)
            Xn = pre.transform(Xs); sm = smote_for(Ys)
            if sm != "passthrough":
                Xn, Ys = sm.fit_resample(Xn, Ys)
            Xs = pd.DataFrame(Xn); cc2, nc2 = [], list(Xs.columns)
        else:
            cc2, nc2 = cc, nc
        for fold, (tr, te) in enumerate(skf.split(Xs, Ys)):
            steps = [("pre", preprocessor(cc2, nc2))]
            if smote == "in_fold":
                steps.append(("smote", smote_for(Ys[tr])))
            steps.append(("clf", model_factory(name, seed)))
            pipe = ImbPipeline(steps)
            t0 = time.time(); pipe.fit(Xs.iloc[tr], Ys[tr]); t_fit = time.time() - t0
            yp = np.asarray(pipe.predict(Xs.iloc[te])).astype(int).ravel()
            m = metrics(Ys[te], yp); m.update(model=name, seed=seed, fold=fold, fit_s=round(t_fit, 1))
            clf = pipe.named_steps["clf"]
            if hasattr(clf, "last_forward_ratio_"):
                m["forward_ratio_r"] = clf.last_forward_ratio_
                b = Ys[te] == BENIGN                           # Stage-1 forwarding rates of benign / attack records
                m["fwd_benign"] = float(clf.last_fwd_[b].mean()); m["fwd_attack"] = float(clf.last_fwd_[~b].mean())
            rows.append(m)
            if collect_pred:
                preds.append((Ys[te], yp))
            print(f"{name:18s} seed {seed} fold {fold}: macroF1={m['macro_f1']:.4f} FAR={m['far']:.4f} ({t_fit:.0f}s)")
    return pd.DataFrame(rows), preds


SMOTE_MODE = "in_fold"     # replaced by the tuned choice below


def summarize(df):
    g = df.groupby("model")[["macro_f1", "far", "mcc", "acc"]]
    s = g.mean().add_suffix("_mean").join(g.std().add_suffix("_std"))
    return s.round(5)


# %% Inner validation splits (seed-0 training folds only; test folds are never used for any selection) ---
TUNE_MAX = 100_000          # inner-training subsample per fold, to bound tuning time
DEFAULT = dict(d1=4, n1=60, lr1=0.1, d2=6, n2=200, rho=RHO)   # starting point enqueued in every study
BEST, SMOTE_ON = dict(DEFAULT), False
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)


def latency_proxy(p, f_b, f_a, n_cls2):
    """Expected per-record inference cost in tree-depth units at benign share PI_DEPLOY:
    Stage 1 (binary LightGBM, every record) n1*d1 + forwarded share * Stage 2 (multi-class XGBoost: n2 trees per class) n2*d2*K2."""
    load = PI_DEPLOY * f_b + (1 - PI_DEPLOY) * f_a
    return p["n1"] * p["d1"] + load * p["n2"] * p["d2"] * n_cls2, load


def tune(features, n_trials, tag):
    """Optuna (TPE) on the seed-0 inner splits; SMOTE on/off is part of the search space.
    Latency-aware selection: among trials within DELTA_TUNE of the best inner macro-F1,
    the configuration with the lowest expected-cost proxy (latency_proxy) is chosen."""
    def objective(trial):
        # latency-aware search space: Stage 1 runs on every record, so it is kept small (<= 100 trees of depth <= 5);
        # Stage 2 runs only on forwarded records and is bounded at 300 trees of depth <= 8.
        # rho includes lower recall targets, so that Stage 1 can stop more benign traffic when classes overlap.
        p = dict(d1=trial.suggest_categorical("d1", [3, 4, 5]), n1=trial.suggest_int("n1", 20, 100),
                 lr1=trial.suggest_float("lr1", 0.03, 0.3, log=True), d2=trial.suggest_int("d2", 3, 8),
                 n2=trial.suggest_int("n2", 50, 300),
                 rho=trial.suggest_categorical("rho", [0.95, 0.98, 0.99, 0.995, 0.999]))
        f1, f_b, f_a, k2 = inner_score(features, p, trial.suggest_categorical("smote", [True, False]), rates=True)
        cost, load = latency_proxy(p, f_b, f_a, k2)
        for k_, v_ in dict(fwd_benign=f_b, fwd_attack=f_a, load=load, cost=cost).items():
            trial.set_user_attr(k_, v_)
        return f1
    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=0))
    for sm in (False, True):
        st.enqueue_trial({**DEFAULT, "smote": sm})
    st.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    st.trials_dataframe().to_csv(f"{OUT}/{DATASET}_tuning_trials_{tag}.csv", index=False)
    done = [t for t in st.trials if t.value is not None]
    best_f1 = max(t.value for t in done)
    cand = [t for t in done if t.value >= best_f1 - DELTA_TUNE]
    pick = min(cand, key=lambda t: (t.user_attrs["cost"], -t.value))
    bp = dict(pick.params); sm = bool(bp.pop("smote"))
    print(f"tuning [{tag}]:", bp, "| SMOTE:", sm, "| inner macro-F1:", round(pick.value, 4),
          f"(best {best_f1:.4f}, {len(cand)} candidates) | benign fwd {pick.user_attrs['fwd_benign']:.3f}",
          f"| cost {pick.user_attrs['cost']:.0f}")
    TUNE_LOG[tag] = dict(best_inner_f1=best_f1, n_candidates=len(cand), **pick.user_attrs)
    return bp, sm, pick.value


TUNE_LOG = {}


def inner_score(features=None, params=None, smote_on=False, rates=False):
    """Mean macro-F1 of the cascade on the seed-0 inner validation splits (test folds untouched).
    rates=True also returns the Stage-1 forwarding rates of benign/attack records and the number of Stage-2 classes."""
    params = DEFAULT if params is None else params
    cols = list(X.columns) if features is None else list(features)
    cc_ = [c for c in cols if c in cat_cols]; nc_ = [c for c in cols if c not in cat_cols]
    sc, fb, fa, k2 = [], [], [], []
    for itr, iva in _inner:
        steps = [("pre", preprocessor(cc_, nc_))] + ([("smote", smote_for(Y[itr]))] if smote_on else [])
        pipe = ImbPipeline(steps + [("clf", Cascade(benign=BENIGN, random_state=0, **params))]).fit(X[cols].iloc[itr], Y[itr])
        sc.append(f1_score(Y[iva], pipe.predict(X[cols].iloc[iva]), average="macro"))
        c_ = pipe.named_steps["clf"]; b_ = Y[iva] == BENIGN
        fb.append(c_.last_fwd_[b_].mean()); fa.append(c_.last_fwd_[~b_].mean()); k2.append(len(c_.inv_))
    if rates:
        return float(np.mean(sc)), float(np.mean(fb)), float(np.mean(fa)), float(np.mean(k2))
    return float(np.mean(sc))
_skf0 = list(StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEEDS[0]).split(X, Y))
_inner = []
for tr, _ in _skf0:         # test folds are never touched
    itr, iva = train_test_split(tr, test_size=0.2, stratify=Y[tr], random_state=0)
    if len(itr) > TUNE_MAX:
        itr = train_test_split(itr, train_size=TUNE_MAX, stratify=Y[itr], random_state=0)[0]
    _inner.append((itr, iva))


# %% Feature selection: choose k* by eq. (3) using MI + SHAP (Section IV-B) ------
# Ranking and k* use only the seed-0 inner training/validation splits, never a test fold.
from sklearn.feature_selection import mutual_info_classif
import shap
itr0 = _inner[0][0]
pre_fs = preprocessor(cat_cols, num_cols).fit(X.iloc[itr0])
Xn = pd.DataFrame(pre_fs.transform(X.iloc[itr0]), columns=cat_cols + num_cols)
yn = Y[itr0]
sub = Xn.sample(min(len(Xn), 50000), random_state=0); ysub = yn[sub.index.values]
mi = pd.Series(mutual_info_classif(sub, ysub, random_state=0), index=Xn.columns)
ref = lgb.LGBMClassifier(n_estimators=200, reg_lambda=LGB_L2, verbose=-1, random_state=0).fit(sub, ysub)
sv = np.abs(np.array(shap.TreeExplainer(ref).shap_values(sub.iloc[:5000])))
feat_axis = [i for i, n in enumerate(sv.shape) if n == Xn.shape[1]][-1]
shap_imp = pd.Series(sv.mean(axis=tuple(i for i in range(sv.ndim) if i != feat_axis)), index=Xn.columns)
rank = (mi.rank(ascending=False) + shap_imp.rank(ascending=False)).sort_values().index.tolist()
# Stage A: configuration tuned on all features (seed-0 inner splits), used to choose k*
P_A, SM_A, f_all = tune(None, 10 if QUICK else 30, "A_all_features")
ksel = [dict(k=len(rank), macro_f1=f_all)]
for k in K_CANDIDATES:
    if k < len(rank):
        ksel.append(dict(k=k, macro_f1=inner_score(rank[:k], P_A, SM_A))); print(ksel[-1])
ksel = pd.DataFrame(ksel).sort_values("k"); ksel.to_csv(f"{OUT}/{DATASET}_ksel.csv", index=False)
ok = ksel[ksel.macro_f1 >= f_all - DELTA]
K_STAR = int(ok.k.min())
TOPK = rank[:K_STAR]
print("k* =", K_STAR, TOPK)
json.dump({"k_star": K_STAR, "n_features": len(rank), "features": TOPK, "inner_macro_f1_all": f_all},
          open(f"{OUT}/{DATASET}_kstar.json", "w"), indent=1)

# %% Hyperparameter tuning (Table V), stage B: re-tuned on the k* features, seed-0 inner splits only ---
# The selected configuration (including whether SMOTE is used) is then fixed for all 25 folds and every seed.
N_TRIALS = 5 if QUICK else 50
BEST, SMOTE_ON, best_val = tune(TOPK, N_TRIALS, "B_kstar")
SMOTE_MODE = "in_fold" if SMOTE_ON else "none"
json.dump({"stage_A_all_features": {"params": P_A, "smote": SM_A, "inner_macro_f1": f_all},
           "best_params": BEST, "smote": SMOTE_ON, "inner_macro_f1": best_val,
           "selection": {"rule": "min latency proxy within DELTA_TUNE of best inner macro-F1",
                         "DELTA_TUNE": DELTA_TUNE, "PI_DEPLOY": PI_DEPLOY, **TUNE_LOG}},
          open(f"{OUT}/{DATASET}_tuning.json", "w"), indent=1)


# %% E1: detection performance of ML baselines and the cascade (Table VIII) -----
ML_MODELS = ["Decision tree", "Random forest", "XGBoost", "LightGBM", "Proposed cascade"]
all_rows, cascade_preds = [], None
for name in ML_MODELS:
    feats = TOPK if name == "Proposed cascade" else None      # baselines use all features
    df, preds = run_cv(name, X, Y, features=feats, collect_pred=(name == "Proposed cascade"))
    all_rows.append(df)
    if name == "Proposed cascade":
        cascade_preds = preds
    pd.concat(all_rows).to_csv(f"{OUT}/{DATASET}_E1_folds.csv", index=False)   # saved after every model
e1 = pd.concat(all_rows)
print(summarize(e1))
summarize(e1).to_csv(f"{OUT}/{DATASET}_E1_summary.csv")

# %% Per-class results of the cascade (Table IX) --------------------------------
yt = np.concatenate([a for a, _ in cascade_preds]); yp = np.concatenate([b for _, b in cascade_preds])
p, r, f, s = precision_recall_fscore_support(yt, yp, labels=range(len(CLASSES)), zero_division=0)
perclass = pd.DataFrame({"class": CLASSES, "precision": p, "recall": r, "f1": f, "support": s})
perclass.to_csv(f"{OUT}/{DATASET}_perclass.csv", index=False)
pd.DataFrame(confusion_matrix(yt, yp), index=CLASSES, columns=CLASSES).to_csv(f"{OUT}/{DATASET}_confusion.csv")
print(perclass)

# %% Statistical test (Friedman + Nemenyi, Section V-C) --------------------------
from scipy.stats import friedmanchisquare
pivot = e1.pivot_table(index=["seed", "fold"], columns="model", values="macro_f1")
stat, pval = friedmanchisquare(*[pivot[c] for c in pivot.columns])
print(f"Friedman chi2={stat:.3f}, p={pval:.3g}")
try:
    import scikit_posthocs as sp
    sp.posthoc_nemenyi_friedman(pivot.values).set_axis(pivot.columns, axis=0).set_axis(pivot.columns, axis=1)\
        .to_csv(f"{OUT}/{DATASET}_nemenyi.csv")
except ImportError:
    print("pip install scikit-posthocs for the Nemenyi post hoc test")
json.dump({"friedman_chi2": float(stat), "p": float(pval)}, open(f"{OUT}/{DATASET}_friedman.json", "w"))

# %% E2: evaluation leakage configurations L0-L3 (Table X) ------------------------
leak = []
d = e1[e1.model == "Proposed cascade"].copy(); d["config"] = "L0 proposed protocol"; leak.append(d)   # reuse E1
if NET_IDS:
    Xi, yi, _ = make_xy(raw, keep_ids=NET_IDS)
    d, _ = run_cv("Proposed cascade", Xi, le.transform(yi), features=TOPK + NET_IDS)
    d["config"] = "L1 network identifiers retained"; leak.append(d)
d, _ = run_cv("Proposed cascade", X, Y, features=TOPK, smote="before_split"); d["config"] = "L2 SMOTE before split"; leak.append(d)
Xn_, yn_, _ = make_xy(raw, dedup=False)
d, _ = run_cv("Proposed cascade", Xn_, le.transform(yn_), features=TOPK); d["config"] = "L3 no deduplication"; leak.append(d)
leak = pd.concat(leak)
leak_s = leak.groupby("config")["macro_f1"].agg(["mean", "std"])
leak_s["delta_pp"] = (leak_s["mean"] - leak_s.loc["L0 proposed protocol", "mean"]) * 100
leak_s.to_csv(f"{OUT}/{DATASET}_E2_leakage.csv"); print(leak_s)

# %% E3: ablation, accuracy part (Table XI; size and p99 are measured on the workstation) ---
abl = []
d = e1[e1.model == "Proposed cascade"].copy(); d["variant"] = "Full cascade (k* features)"; abl.append(d)   # reuse E1
d, _ = run_cv("Proposed cascade", X, Y); d["variant"] = "w/o feature selection (all features)"; abl.append(d)
alt = "none" if SMOTE_ON else "in_fold"
d, _ = run_cv("Proposed cascade", X, Y, features=TOPK, smote=alt)
d["variant"] = "w/o SMOTE" if SMOTE_ON else "with SMOTE"; abl.append(d)
d, _ = run_cv("LightGBM", X, Y, features=TOPK); d["variant"] = "Single model (no cascade, k* features)"; abl.append(d)
abl = pd.concat(abl); abl.groupby("variant")[["macro_f1", "far"]].agg(["mean", "std"]).to_csv(f"{OUT}/{DATASET}_E3_ablation.csv")

# %% E5: leave-one-attack-out (Section VI-E) -----------------------------------
loao = []
Xt = X[TOPK]; cc = [c for c in TOPK if c in cat_cols]; nc = [c for c in TOPK if c not in cat_cols]
for a in [c for c in range(len(CLASSES)) if c != BENIGN]:
    held = Y == a
    Xtr_, Ytr_ = Xt[~held], Y[~held]
    pipe = ImbPipeline([("pre", preprocessor(cc, nc)), ("clf", Cascade(benign=BENIGN, **BEST))]).fit(Xtr_, Ytr_)
    pred = pipe.predict(Xt[held])
    loao.append(dict(held_out=CLASSES[a], detected_as_attack=float(np.mean(pred != BENIGN)), n=int(held.sum())))
    print(loao[-1])
pd.DataFrame(loao).to_csv(f"{OUT}/{DATASET}_E5_loao.csv", index=False)

# %% E6: SHAP of Stage 1 (Fig. 9) ------------------------------------------------
final = ImbPipeline([("pre", preprocessor(cc, nc))] + ([("smote", smote_for(Y))] if SMOTE_ON else [])
                    + [("clf", Cascade(benign=BENIGN, **BEST))]).fit(Xt, Y)
s1 = final.named_steps["clf"].s1_
Xs = pd.DataFrame(final.named_steps["pre"].transform(Xt.sample(min(5000, len(Xt)), random_state=0)), columns=cc + nc)
sv1 = shap.TreeExplainer(s1).shap_values(Xs)
sv1 = sv1[1] if isinstance(sv1, list) else sv1
name_map = {"edge": "Edge-IIoTset", "rosids": "ROSIDS23", "rospace": "ROSPaCe"}
pd.DataFrame({"feature": cc + nc, "mean_abs_shap": np.abs(sv1).mean(axis=0), "dataset": name_map[DATASET]})\
    .sort_values("mean_abs_shap", ascending=False).to_csv(f"{OUT}/{DATASET}_shap.csv", index=False)

# %% Export the final models for latency measurement on the workstation (Section V-D) ---
import joblib
joblib.dump(final, f"{OUT}/models/{DATASET}_cascade_pipeline.joblib")
s1.booster_.save_model(f"{OUT}/models/{DATASET}_stage1_lgbm.txt")
for name in ["Random forest", "XGBoost", "LightGBM"]:
    m = ImbPipeline([("pre", preprocessor(cc, nc)), ("clf", model_factory(name, 0))]).fit(Xt, Y)
    joblib.dump(m, f"{OUT}/models/{DATASET}_{name.replace(' ', '_')}.joblib")
Xt.sample(min(100000, len(Xt)), random_state=1).to_parquet(f"{OUT}/models/{DATASET}_latency_test_records.parquet")
import sklearn
json.dump({"classes": CLASSES, "benign": cfg["benign"], "features": TOPK, "tau": final.named_steps["clf"].tau_,
           "smote": SMOTE_ON, "best_params": BEST,
           "versions": {"sklearn": sklearn.__version__, "lightgbm": lgb.__version__, "xgboost": xgb.__version__,
                        "imblearn": __import__("imblearn").__version__, "pandas": pd.__version__}},
          open(f"{OUT}/models/{DATASET}_meta.json", "w"), indent=1)
print("exported")

# %% [markdown]
# ## Deep learning baselines (GPU) — MLP, 1D-CNN, CNN-LSTM, Transformer
# Inputs are the top-k feature vectors; convolutional and recurrent layers run along the feature axis.

# %% DL models -------------------------------------------------------------------
import torch, torch.nn as nn
DEV = "cuda" if GPU else "cpu"


class MLP(nn.Module):
    def __init__(s, d, c): super().__init__(); s.n = nn.Sequential(nn.Linear(d, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, c))
    def forward(s, x): return s.n(x)


class CNN1D(nn.Module):
    # No adaptive pooling: AdaptiveAvgPool1d with an output size that does not divide k* cannot be exported to ONNX.
    def __init__(s, d, c, f=32):
        super().__init__()
        s.c = nn.Sequential(nn.Conv1d(1, f, 3, padding=1), nn.ReLU(), nn.Conv1d(f, f, 3, padding=1), nn.ReLU())
        s.h = nn.Linear(f * d, c)
    def forward(s, x): return s.h(s.c(x.unsqueeze(1)).flatten(1))


class CNNLSTM(nn.Module):
    def __init__(s, d, c, f=32):
        super().__init__()
        s.c = nn.Sequential(nn.Conv1d(1, f, 3, padding=1), nn.ReLU())
        s.l = nn.LSTM(f, 64, batch_first=True); s.h = nn.Linear(64, c)
    def forward(s, x):
        z = s.c(x.unsqueeze(1)).transpose(1, 2); _, (h, _) = s.l(z); return s.h(h[-1])


class TinyTransformer(nn.Module):
    def __init__(s, d, c, e=32):
        super().__init__()
        s.emb = nn.Linear(1, e); s.pos = nn.Parameter(torch.zeros(1, d, e))
        s.enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(e, 4, 64, 0.1, batch_first=True), 2); s.h = nn.Linear(e, c)
    def forward(s, x): return s.h(s.enc(s.emb(x.unsqueeze(-1)) + s.pos).mean(1))


DL = {"MLP": MLP, "1D-CNN": CNN1D, "CNN-LSTM": CNNLSTM, "Transformer": TinyTransformer}


def train_dl(arch, Xtr, ytr, epochs=40, bs=512, seed=0, patience=5):
    """AdamW + cosine schedule, mild class weighting (sqrt inverse frequency, capped at 10),
    early stopping on a 10% stratified validation split of the training fold."""
    torch.manual_seed(seed); np.random.seed(seed)
    tr_i, va_i = train_test_split(np.arange(len(ytr)), test_size=0.1, stratify=ytr, random_state=seed)
    m = DL[arch](Xtr.shape[1], len(CLASSES)).to(DEV)
    opt = torch.optim.AdamW(m.parameters(), 1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    cnt = np.maximum(np.bincount(ytr[tr_i], minlength=len(CLASSES)), 1)
    w = torch.tensor(np.sqrt(cnt.max() / cnt), dtype=torch.float32, device=DEV).clamp(max=10)
    lossf = nn.CrossEntropyLoss(weight=w)
    Xt_ = torch.tensor(Xtr[tr_i], dtype=torch.float32); yt_ = torch.tensor(ytr[tr_i])
    best, best_state, bad = -1.0, None, 0
    for ep in range(epochs):
        m.train(); perm = torch.randperm(len(Xt_))
        for i in range(0, len(perm), bs):
            b = perm[i:i + bs]; opt.zero_grad()
            loss = lossf(m(Xt_[b].to(DEV)), yt_[b].to(DEV)); loss.backward(); opt.step()
        sched.step()
        f = f1_score(ytr[va_i], predict_dl(m, Xtr[va_i]), average="macro")
        if f > best + 1e-4:
            best, bad = f, 0; best_state = {k: v.detach().clone() for k, v in m.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    m.load_state_dict(best_state)
    return m


def predict_dl(m, X_):
    m.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(X_), 8192):
            out.append(m(torch.tensor(X_[i:i + 8192], dtype=torch.float32, device=DEV)).argmax(1).cpu().numpy())
    return np.concatenate(out)


dl_rows = []
for arch in DL:
    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold, (tr, te) in enumerate(skf.split(Xt, Y)):
            pre_ = preprocessor(cc, nc, scale=True).fit(Xt.iloc[tr])
            t0 = time.time()
            m = train_dl(arch, pre_.transform(Xt.iloc[tr]), Y[tr], epochs=3 if QUICK else 40, seed=seed)
            yp = predict_dl(m, pre_.transform(Xt.iloc[te]))
            r_ = metrics(Y[te], yp); r_.update(model=arch, seed=seed, fold=fold, fit_s=round(time.time() - t0, 1))
            dl_rows.append(r_); print(arch, seed, fold, round(r_["macro_f1"], 4))
        pd.DataFrame(dl_rows).to_csv(f"{OUT}/{DATASET}_DL_folds.csv", index=False)
print(summarize(pd.DataFrame(dl_rows)))
summarize(pd.concat([e1, pd.DataFrame(dl_rows)])).to_csv(f"{OUT}/{DATASET}_table_VIII.csv")

# %% Export 1D-CNN to ONNX (FP32 and INT8 static quantization) for the workstation ---
pre_all = preprocessor(cc, nc, scale=True).fit(Xt)
Xall = pre_all.transform(Xt).astype(np.float32)
cnn = train_dl("1D-CNN", Xall, Y, epochs=3 if QUICK else 40).cpu().eval()
onnx_fp32 = f"{OUT}/models/{DATASET}_cnn_fp32.onnx"
torch.onnx.export(cnn, torch.tensor(Xall[:1]), onnx_fp32, input_names=["x"], output_names=["y"],
                  dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)
joblib.dump(pre_all, f"{OUT}/models/{DATASET}_cnn_preprocessor.joblib")
onnx_int8 = onnx_fp32.replace("fp32", "int8")
try:
    from onnxruntime.quantization import quantize_static, quantize_dynamic, CalibrationDataReader, QuantType, QuantFormat
    from onnxruntime.quantization.shape_inference import quant_pre_process
    onnx_pre = onnx_fp32.replace("fp32", "fp32_pre")
    quant_pre_process(onnx_fp32, onnx_pre)

    class Calib(CalibrationDataReader):
        def __init__(s, data): s.it = iter([{"x": data[i:i + 1]} for i in range(len(data))])
        def get_next(s): return next(s.it, None)

    calib = Xall[np.random.RandomState(0).choice(len(Xall), min(1000, len(Xall)), replace=False)]
    try:
        quantize_static(onnx_pre, onnx_int8, Calib(calib), quant_format=QuantFormat.QDQ,
                        weight_type=QuantType.QInt8, activation_type=QuantType.QUInt8)
        print("ONNX INT8 (static) exported")
    except Exception as e:
        import traceback; traceback.print_exc()
        quantize_dynamic(onnx_pre, onnx_int8, weight_type=QuantType.QInt8)
        print("static quantization failed; ONNX INT8 (dynamic) exported instead:", e)
    import onnxruntime as ort
    xs = Xall[:5000]
    o32 = ort.InferenceSession(onnx_fp32).run(None, {"x": xs})[0].argmax(1)
    o8 = ort.InferenceSession(onnx_int8).run(None, {"x": xs})[0].argmax(1)
    print("INT8 vs FP32 prediction agreement on 5,000 records:", float((o32 == o8).mean()))
except Exception as e:
    import traceback; traceback.print_exc()
    print("INT8 quantization skipped:", e)

print("All done. Download /kaggle/working/results or save this version as a Kaggle dataset.")
