"""Exploratory comparison: can a covariate-shift correction rescue naive kNN under duplication?

Setting of protocol 2.1 (fresh targets, exact copies, system C1 = LEGAL-BERT + naive kNN,
alpha = 0.10). After copies enter the pool, the stacker features of risk_cert documents shift.
Weighted conformal methods (Tibshirani et al., 2019) reweight calibration examples by the
density ratio p_deploy(x) / p_cert(x), estimated here with a probabilistic classifier between
certification-time and deployment-time pair features, and re-certify the threshold on the
weighted risk (effective sample size by Kish). Unlike labelled re-certification, it needs no
new labels. Its assumption is that P(y | x) does not change; duplication breaks exactly that:
a high kNN vote produced by copies looks like real consensus but is right less often.

References for comparison:
* clean certification (the deployed policy, no correction);
* weighted re-certification (this method, no new labels);
* oracle re-certification on labelled post-copy data (needs fresh labels; an upper reference);
* provenance-aware kNN (C1p) results from protocol 2.1.

Exploratory, not pre-registered: run on risk_cert only.
"""

import time

import joblib
import numpy as np
import orjson
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict

from evigraph_research import dataset, paths, policy, protocol, provenance, textmodel
from evigraph_research import protocol_v21 as cfg
from evigraph_research.baseline import _stack_oof
from evigraph_research.compare import _features

BLOCKS = ("p_strong", "knn")
WEIGHT_CLIP = 20.0


def weighted_certify(scores, y, grid, w, *, alpha: float, delta: float) -> dict:
    """Fixed-sequence certification on the weighted error rate, Kish effective sample size."""
    s, err = scores.ravel(), (~y.ravel().astype(bool)).astype(float)
    ww = np.repeat(w, y.shape[1])
    tau = None
    tested = []
    for t in grid:
        a = s >= t
        wa = ww[a]
        if wa.sum() == 0:
            break
        rate = float((wa * err[a]).sum() / wa.sum())
        n_eff = float(wa.sum() ** 2 / (wa**2).sum())
        ucb = policy.clopper_pearson_upper(round(rate * n_eff), max(round(n_eff), 1), delta)
        tested.append(
            {
                "tau": float(t),
                "n_eff": round(n_eff, 1),
                "rate": round(rate, 4),
                "ucb": round(ucb, 4),
            }
        )
        if ucb > alpha:
            break
        tau = float(t)
    return {"tau": tau, "tested": tested[-2:]}


def describe(x_pairs, scores, n_docs: int, n_lab: int) -> np.ndarray:
    """Per-document shift descriptors: top-10 kNN votes, top-10 stacker scores, top similarity,
    and the concentration of the vote (sum of squared votes over sum of votes)."""
    x = x_pairs.reshape(n_docs, n_lab, -1)
    votes = x[:, :, 2]  # column order of compare._features: prior, p_strong, knn vote, knn top
    top_sim = x[:, 0, 3]
    sv = -np.sort(-votes, axis=1)[:, :10]
    ss = -np.sort(-scores, axis=1)[:, :10]
    conc = (votes**2).sum(axis=1) / np.maximum(votes.sum(axis=1), 1e-9)
    return np.column_stack([sv, ss, top_sim, conc])


def realised(scores, y, tau) -> dict:
    if tau is None:
        return {"risk": None, "auto_recall": 0.0, "applied": 0}
    auto = scores >= tau
    applied = int(auto.sum())
    errors = int((auto & ~y).sum())
    return {
        "risk": round(errors / applied, 4) if applied else None,
        "auto_recall": round((applied - errors) / max(int(y.sum()), 1), 4),
        "applied": applied,
    }


def run() -> dict:
    t0 = time.perf_counter()
    ds = dataset.load()
    protocol.assert_manifest(ds.frame)
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    is_train = ds.mask("train")
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    pos = np.full(len(fr), -1)
    pos[eval_rows] = np.arange(len(eval_rows))
    md, cf_, rc = (np.flatnonzero(ds.mask(s)) for s in ("model_dev", "calib_fit", "risk_cert"))
    prior = y[is_train].mean(axis=0)

    feats = joblib.load(
        paths.CACHE / "preds" / f"h2_clean_k{protocol.KNN_K}_c{cfg.KNN_CANDIDATES}_adaptive.joblib"
    )
    naive = feats["naive"]
    _, model = _stack_oof(
        _features(md, BLOCKS, naive, prior, n_lab),
        y[md].ravel(),
        fr["split_group"].iloc[md].to_numpy(),
        n_lab,
    )
    raw_cf = model.predict_proba(_features(cf_, BLOCKS, naive, prior, n_lab))[:, 1]
    x_rc_clean = _features(rc, BLOCKS, naive, prior, n_lab)
    s_rc_clean = model.predict_proba(x_rc_clean)[:, 1].reshape(len(rc), n_lab)
    grid = policy.candidate_thresholds(
        raw_cf, min_applied=protocol.GRID_MIN_APPLIED, ratio=protocol.GRID_RATIO
    )
    tau_clean = policy.certify(s_rc_clean, y[rc], grid, alpha=cfg.ALPHA, delta=protocol.DELTA).tau

    # targets and sources exactly as in protocol 2.1
    earlier = np.random.default_rng(cfg.EXCLUDED_TARGET_SEED).choice(rc, cfg.TARGETS, replace=False)
    targets = np.sort(
        np.random.default_rng(cfg.TARGET_SEED).choice(
            np.setdiff1d(rc, earlier), cfg.TARGETS, replace=False
        )
    )
    is_target = np.isin(rc, targets)
    tr_path, ev_path = textmodel.tfidf(
        [], [], n_features=2**21, cache_key=protocol.MANIFEST_SHA256, n_jobs=1
    )
    x_train, x_eval = joblib.load(tr_path), joblib.load(ev_path)
    _, _, _, top1 = provenance.knn_both(
        x_eval[pos[targets]], x_train, y[is_train], k=protocol.KNN_K, groups=None
    )
    sources = np.unique(top1)

    out = {"alpha": cfg.ALPHA, "delta": protocol.DELTA, "tau_clean": tau_clean, "scenarios": []}
    for m in (0, 10, 30, 100):
        if m == 0:
            data = naive
        else:
            x_pool = sp.vstack([x_train, x_train[np.repeat(sources, m)]], format="csr")
            y_pool = np.vstack([y[is_train], y[is_train][np.repeat(sources, m)]])
            votes, _, top, _ = provenance.knn_both(
                x_eval[pos[rc]], x_pool, y_pool, k=protocol.KNN_K, groups=None
            )
            data = dict(naive)
            data["knn_vote"] = naive["knn_vote"].copy()
            data["knn_top"] = naive["knn_top"].copy()
            data["knn_vote"][rc] = votes
            data["knn_top"][rc] = top
        x_dep = _features(rc, BLOCKS, data, prior, n_lab)
        s_dep = model.predict_proba(x_dep)[:, 1].reshape(len(rc), n_lab)

        # density ratio between certification-time and deployment-time features, per document;
        # descriptors keep the shape of the vote distribution (sorted votes, concentration)
        d_clean = describe(x_rc_clean, s_rc_clean, len(rc), n_lab)
        d_dep = describe(x_dep, s_dep, len(rc), n_lab)
        X = np.vstack([d_clean, d_dep])
        z = np.r_[np.zeros(len(rc)), np.ones(len(rc))]
        auc = float(
            roc_auc_score(
                z,
                cross_val_predict(
                    HistGradientBoostingClassifier(), X, z, cv=5, method="predict_proba"
                )[:, 1],
            )
        )
        clf = HistGradientBoostingClassifier().fit(X, z)
        p = clf.predict_proba(d_clean)[:, 1]
        w = np.clip(p / np.maximum(1 - p, 1e-6), 0, WEIGHT_CLIP)
        w = w / w.mean()
        weighted = weighted_certify(
            s_rc_clean, y[rc], grid, w, alpha=cfg.ALPHA, delta=protocol.DELTA
        )
        oracle = policy.certify(s_dep, y[rc], grid, alpha=cfg.ALPHA, delta=protocol.DELTA).tau

        tgt = is_target
        row = {
            "copies": m,
            "weights": {
                "shift_detector_auc": round(auc, 4),
                "max": round(float(w.max()), 2),
                "kish_n_eff_docs": round(float(w.sum() ** 2 / (w**2).sum()), 1),
            },
            "clean_tau": {"tau": tau_clean, **realised(s_dep[tgt], y[rc][tgt], tau_clean)},
            "weighted_recert": {**weighted, **realised(s_dep[tgt], y[rc][tgt], weighted["tau"])},
            "oracle_recert_with_new_labels": {
                "tau": oracle,
                **realised(s_dep[tgt], y[rc][tgt], oracle),
            },
        }
        out["scenarios"].append(row)
        print(
            f"m={m}: detector AUC {auc:.3f} | clean risk {row['clean_tau']['risk']} | "
            f"weighted tau {weighted['tau']} risk "
            f"{row['weighted_recert']['risk']} | oracle {row['oracle_recert_with_new_labels']}",
            flush=True,
        )
    out["seconds"] = round(time.perf_counter() - t0)
    (paths.REPORTS / "weighted_conformal.json").write_bytes(
        orjson.dumps(out, option=orjson.OPT_INDENT_2)
    )
    return out


if __name__ == "__main__":
    run()
