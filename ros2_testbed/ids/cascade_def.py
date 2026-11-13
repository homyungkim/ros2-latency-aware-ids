"""Definition of the cascade estimator, identical to the Kaggle notebook.
joblib files pickled in the notebook refer to __main__.Cascade, so measure_latency.py
registers this class under __main__ before loading them."""
import numpy as np
import lightgbm as lgb
import xgboost as xgb
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.model_selection import train_test_split

RHO = 0.995
GPU = False


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
        return lgb.LGBMClassifier(n_estimators=self.n2, max_depth=self.d2, random_state=self.random_state, verbose=-1)

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float32); y = np.asarray(y)
        yb = (y != self.benign).astype(int)
        Xtr, Xva, ytr, yva = train_test_split(X, yb, test_size=0.2, stratify=yb, random_state=self.random_state)
        self.s1_ = lgb.LGBMClassifier(n_estimators=self.n1, max_depth=self.d1, num_leaves=2 ** self.d1 - 1,
                                      learning_rate=self.lr1, random_state=self.random_state, verbose=-1).fit(Xtr, ytr)
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
        self.last_forward_ratio_ = float(fwd.mean())
        if fwd.any():
            out[fwd] = self.inv_[self.s2_.predict(X[fwd]).astype(int)]
        return out
