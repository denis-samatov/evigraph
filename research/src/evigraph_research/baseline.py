"""CPU baseline and first end-to-end pass of the evaluation protocol.

    train      -> TF-IDF + one-vs-rest logistic regression (text only)
    model_dev  -> two stackers with the same model class, out-of-fold by split group:
                    text       : logit(p_text), logit(prior)
                    text+graph : the same + neighbour votes and coverage flags
    calib_fit  -> isotonic calibration of each stacker; candidate thresholds for the policy
    risk_cert  -> Learn-then-Test certification at (alpha, delta); automation metrics
    final_test -> not touched

This compares graph features against a *weak* text model with no neighbour text. It is an
early signal for the go/no-go decision, not evidence for the paper.
"""

import os
import resource
import sys
import time
from contextlib import contextmanager
from typing import Any

import numpy as np
import orjson
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from evigraph_research import dataset, graphfeat, metrics, paths, policy, textmodel
from evigraph_research.splits import _bucket

EPS = 1e-6
ALPHAS = (0.01, 0.02, 0.05, 0.10)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 2**10


class Timer:
    def __init__(self) -> None:
        self.stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter()
        print(f"[{name}] ...", flush=True)
        yield
        self.stages[name] = round(time.perf_counter() - t, 1)
        print(f"[{name}] {self.stages[name]}s, peak RSS {_peak_rss_mb():.0f} MB", flush=True)


def _pair_features(
    rows: np.ndarray, p_text: np.ndarray, prior: np.ndarray, gf: graphfeat.GraphFeatures | None
) -> np.ndarray:
    """(n_rows * n_labels, n_features) design matrix, row-major over (doc, label)."""
    n, n_lab = p_text.shape
    cols = [_logit(p_text).ravel(), np.tile(_logit(prior), n)]
    if gf is not None:
        for name in gf.names:
            cols.append(gf.votes[name][rows].ravel())
            cols.append(np.repeat((gf.degree[name][rows] > 0).astype(np.float32), n_lab))
    return np.column_stack(cols).astype(np.float32)


def _stack_oof(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray, n_labels: int
) -> tuple[np.ndarray, LogisticRegression]:
    """2-fold out-of-fold predictions on model_dev, folds by split group; then a full refit."""
    fold = np.array([int(_bucket(g, seed=1) >= 0.5) for g in groups])
    fold_pairs = np.repeat(fold, n_labels)
    oof = np.zeros(len(x), dtype=np.float32)
    for k in (0, 1):
        tr, te = fold_pairs != k, fold_pairs == k
        m = LogisticRegression(C=1.0, max_iter=2000).fit(x[tr], y[tr])
        oof[te] = m.predict_proba(x[te])[:, 1]
    full = LogisticRegression(C=1.0, max_iter=2000).fit(x, y)
    return oof, full


def _auto_at_empirical_risk(scores: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    """Descriptive only: the most permissive threshold whose empirical risk <= alpha."""
    s, yy = scores.ravel(), y.ravel()
    order = np.argsort(-s, kind="stable")
    errors = np.cumsum(~yy[order])
    n = np.arange(1, len(s) + 1)
    ok = np.flatnonzero(errors / n <= alpha)
    if not len(ok):
        return {"auto_recall": 0.0, "tau": None}
    last = ok[-1]
    return {
        "auto_recall": round(float((n[last] - errors[last]) / yy.sum()), 4),
        "tau": float(s[order[last]]),
    }


def run(*, n_features: int = 2**21, alpha: float = 0.05, delta: float = 0.1) -> dict:
    timer = Timer()
    with timer.stage("load"):
        ds = dataset.load(with_text=True)
        edges = pd.read_parquet(paths.CELLAR_EDGES)
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    is_train = ds.mask("train")
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    prior = y[is_train].mean(axis=0)

    n_jobs = max(1, (os.cpu_count() or 2) - 1)
    manifest_key = orjson.loads((paths.REPORTS / "split_manifest.json").read_bytes())[
        "manifest_sha256"
    ]
    with timer.stage("tfidf"):
        tr_path, ev_path = textmodel.tfidf(
            fr.loc[is_train, "text"].tolist(),
            fr["text"].iloc[eval_rows].tolist(),
            n_features=n_features,
            cache_key=manifest_key,
            n_jobs=n_jobs,
        )
    with timer.stage("text_model_fit_predict"):
        t0 = time.perf_counter()
        p = np.zeros((len(fr), n_lab), dtype=np.float32)
        p[eval_rows] = textmodel.fit_predict(tr_path, ev_path, y[is_train], n_jobs=n_jobs)
        per_doc_ms = 1000 * (time.perf_counter() - t0) / len(eval_rows)
    with timer.stage("graph_features"):
        gf = graphfeat.build(fr["celex_id"].tolist(), is_train, y, edges)

    def rows(split: str) -> np.ndarray:
        return np.flatnonzero(ds.mask(split))

    md, cf_, rc = rows("model_dev"), rows("calib_fit"), rows("risk_cert")
    results: dict = {"n_docs": {s: int(ds.mask(s).sum()) for s in dataset.SPLIT_ORDER}}
    results["text_model_dev"] = {
        "mrp": round(metrics.r_precision(y[md], p[md]), 4),
        **{k: round(v, 4) for k, v in metrics.f1_scores(y[md], p[md] >= 0.5).items()},
        **{f"recall@{k}": round(metrics.recall_at_k(y[md], p[md], k), 4) for k in (5, 10, 20, 30)},
    }

    systems = {"text": None, "text+graph": gf}
    for name, g in systems.items():
        with timer.stage(f"stack_{name}"):
            x_md = _pair_features(md, p[md], prior, g)
            oof, model = _stack_oof(
                x_md, y[md].ravel(), fr["split_group"].iloc[md].to_numpy(), n_lab
            )
            oof = oof.reshape(len(md), n_lab)
            res: dict[str, Any] = {
                "model_dev_oof": {
                    "mrp": round(metrics.r_precision(y[md], oof), 4),
                    **{k: round(v, 4) for k, v in metrics.f1_scores(y[md], oof >= 0.5).items()},
                    **{
                        f"auto_recall@emp_risk<={a}": _auto_at_empirical_risk(oof, y[md], a)[
                            "auto_recall"
                        ]
                        for a in ALPHAS
                    },
                }
            }
            raw_cf = model.predict_proba(_pair_features(cf_, p[cf_], prior, g))[:, 1]
            raw_rc = model.predict_proba(_pair_features(rc, p[rc], prior, g))[:, 1]
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
                raw_cf, y[cf_].ravel()
            )
            # Isotonic output is for display and calibration metrics only. Its plateaus merge
            # the top scores into ties, so thresholds are certified on the raw stacker score:
            # any monotone score yields the same applied sets, without the lost resolution.
            r_rc = raw_rc.reshape(len(rc), n_lab)
            s_rc = iso.predict(raw_rc).reshape(len(rc), n_lab)
            res["risk_cert_ranking"] = {
                "mrp": round(metrics.r_precision(y[rc], r_rc), 4),
                "ece_all_pairs": round(metrics.expected_calibration_error(s_rc, y[rc]), 4),
                "ece_top10_pairs": round(
                    metrics.expected_calibration_error_topk(s_rc, y[rc], 10), 4
                ),
            }

            thresholds = policy.candidate_thresholds(raw_cf, min_applied=500)
            res["policy"] = {}
            for a in ALPHAS:
                cert = policy.certify(r_rc, y[rc], thresholds, alpha=a, delta=delta)
                auto = r_rc >= cert.tau if cert.tau is not None else np.zeros_like(y[rc])
                auto_m = metrics.automation(y[rc], auto)
                entry: dict[str, object] = {
                    "tau_raw": cert.tau,
                    "tau_calibrated": (
                        round(float(iso.predict([cert.tau])[0]), 4)
                        if cert.tau is not None
                        else None
                    ),
                    "n_thresholds_tested": len(cert.tested),
                    "last_tested": [
                        {k: round(v, 4) if isinstance(v, float) else v for k, v in t.items()}
                        for t in cert.tested[-2:]
                    ],
                    **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in auto_m.items()},
                }
                if cert.tau is not None:
                    entry["risk_ci90_doc_bootstrap"] = [
                        round(v, 4) for v in policy.cluster_bootstrap_risk(auto, y[rc])
                    ]
                    for flag in ("template_copy_in_train",):
                        f = fr[flag].iloc[rc].to_numpy()
                        entry[f"by_{flag}"] = {
                            str(v): {
                                k: (round(x, 4) if isinstance(x, float) else x)
                                for k, x in metrics.automation(y[rc][f == v], auto[f == v]).items()
                            }
                            for v in (True, False)
                        }
                res["policy"][str(a)] = entry
            results[name] = res

    results["primary"] = {
        "alpha": alpha,
        "delta": delta,
        **{n: results[n]["policy"][str(alpha)]["auto_recall"] for n in systems},
    }
    results["cost"] = {
        "stages_s": timer.stages,
        "peak_rss_mb": round(_peak_rss_mb()),
        "text_fit_predict_ms_per_eval_doc": round(per_doc_ms, 2),
        "hashing_features": n_features,
        "max_chars": textmodel.MAX_CHARS,
        "text_model": f"SGD log-loss alpha={textmodel.SGD_ALPHA} epochs={textmodel.SGD_EPOCHS}",
    }
    (paths.REPORTS / "baseline.json").write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(orjson.dumps(results, option=orjson.OPT_INDENT_2).decode())
    return results
