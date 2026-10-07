"""Protocol v1 runner: pre-registered systems, certification and H1 contrasts.

Every system is the same stacker (logistic regression on (doc, label) pairs, fitted on
model_dev, 2-fold out-of-fold by split group) over different feature blocks; see
protocol.SYSTEMS. Thresholds come from calib_fit, certification from risk_cert.

H1 contrasts are judged on certified AutoRecall at protocol.ALPHA_PRIMARY with a paired
bootstrap over risk_cert documents. Each resample re-runs the whole certification with the
threshold grid fixed, so the interval includes the variability of the certified threshold.
"""

import os
import time
from typing import Any

import joblib
import numpy as np
import orjson
import pandas as pd
from scipy.stats import beta
from sklearn.isotonic import IsotonicRegression

from evigraph_research import (
    controls,
    dataset,
    graphfeat,
    metrics,
    paths,
    policy,
    protocol,
    textmodel,
)
from evigraph_research.baseline import Timer, _logit, _stack_oof

PREDS = paths.CACHE / "preds"


def _cached(name: str, build):
    path = PREDS / f"{name}.joblib"
    if path.exists():
        return joblib.load(path)
    value = build()
    PREDS.mkdir(parents=True, exist_ok=True)
    joblib.dump(value, path)
    return value


def _features(
    rows: np.ndarray, blocks: tuple[str, ...], data: dict, prior: np.ndarray, n_lab: int
) -> np.ndarray:
    n = len(rows)
    cols = [np.tile(_logit(prior), n)]
    for b in blocks:
        if b.startswith("p_"):
            cols.append(_logit(data[b][rows]).ravel())
        elif b == "knn":
            cols.append(data["knn_vote"][rows].ravel())
            cols.append(np.repeat(data["knn_top"][rows], n_lab))
        elif b == "graph":
            gf: graphfeat.GraphFeatures = data["graph"]
            for name in gf.names:
                cols.append(gf.votes[name][rows].ravel())
                cols.append(np.repeat((gf.degree[name][rows] > 0).astype(np.float32), n_lab))
        else:
            msg = f"unknown feature block {b}"
            raise ValueError(msg)
    return np.column_stack(cols).astype(np.float32)


class WeightedCertifier:
    """Fixed-sequence certification on one system's risk_cert scores under doc weights."""

    def __init__(self, scores: np.ndarray, y: np.ndarray, thresholds: np.ndarray) -> None:
        flat = scores.ravel()
        order = np.argsort(-flat, kind="stable")
        self.doc = (order // scores.shape[1]).astype(np.int64)
        self.err = (~y.ravel()[order]).astype(np.float64)
        sorted_scores = flat[order]
        # number of pairs with score >= tau, for each tau (descending thresholds)
        self.pos = np.searchsorted(-sorted_scores, -thresholds, side="right")
        self.gold = y.sum(axis=1).astype(np.float64)

    def auto_recall(self, w: np.ndarray, alpha: float, delta: float) -> float:
        pw = w[self.doc].astype(np.float64)
        cn = np.concatenate([[0.0], np.cumsum(pw)])[self.pos]
        ck = np.concatenate([[0.0], np.cumsum(pw * self.err)])[self.pos]
        ok = cn > ck
        ucb = np.ones_like(cn)
        ucb[ok] = beta.ppf(1 - delta, ck[ok] + 1, cn[ok] - ck[ok])
        passed = ucb <= alpha
        first_fail = np.argmin(passed) if not passed.all() else len(passed)
        if first_fail == 0:
            return 0.0
        j = first_fail - 1
        return float((cn[j] - ck[j]) / (w * self.gold).sum())


def _ci(values: np.ndarray) -> list[float]:
    lo, hi = np.quantile(values, [0.025, 0.975])
    return [round(float(lo), 4), round(float(hi), 4)]


def run() -> dict:
    timer = Timer()
    n_jobs = max(1, (os.cpu_count() or 2) - 1)
    with timer.stage("load"):
        ds = dataset.load(with_text=True)
        protocol.assert_manifest(ds.frame)
        edges = pd.read_parquet(paths.CELLAR_EDGES)
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    is_train = ds.mask("train")
    train_idx = np.flatnonzero(is_train)
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    prior = y[is_train].mean(axis=0)
    celex = fr["celex_id"].tolist()

    def full(p_eval: np.ndarray) -> np.ndarray:
        out = np.zeros((len(fr), p_eval.shape[1]), dtype=np.float32)
        out[eval_rows] = p_eval
        return out

    data: dict = {}
    with timer.stage("tfidf_and_text"):
        tr_path, ev_path = textmodel.tfidf(
            fr.loc[is_train, "text"].tolist(),
            fr["text"].iloc[eval_rows].tolist(),
            n_features=2**21,
            cache_key=protocol.MANIFEST_SHA256,
            n_jobs=n_jobs,
        )
        data["p_tfidf"] = full(
            _cached(
                "p_tfidf",
                lambda: textmodel.fit_predict(tr_path, ev_path, y[is_train], n_jobs=n_jobs),
            )
        )
    with timer.stage("knn"):
        vote, top = _cached(
            f"knn_k{protocol.KNN_K}",
            lambda: controls.knn_votes(tr_path, ev_path, y[is_train], k=protocol.KNN_K),
        )
        data["knn_vote"], data["knn_top"] = full(vote), np.zeros(len(fr), np.float32)
        data["knn_top"][eval_rows] = top
    with timer.stage("nbtext"):
        nb = graphfeat.reference_neighbours(
            celex, fr["publication_date"].to_numpy(), is_train, edges, hub_cap=protocol.HUB_CAP
        )
        ntr, nev = controls.nbtext_matrices(
            tr_path,
            ev_path,
            nb[train_idx][:, train_idx],
            nb[eval_rows][:, train_idx],
            cache_key=protocol.MANIFEST_SHA256[:16],
            top_terms=protocol.NBTEXT_TOP_TERMS,
        )
        data["p_nbtext"] = full(
            _cached(
                f"p_nbtext_top{protocol.NBTEXT_TOP_TERMS}",
                lambda: textmodel.fit_predict(ntr, nev, y[is_train], n_jobs=n_jobs),
            )
        )
        nb_cov = float((np.diff(nb[eval_rows].indptr) > 0).mean())
    with timer.stage("strong_and_graph"):
        saved = joblib.load(paths.STRONG_PREDS)
        if saved["celex_id"] != fr["celex_id"].iloc[eval_rows].tolist():
            msg = "strong predictions are not aligned with the evaluation rows"
            raise protocol.ProtocolError(msg)
        data["p_strong"] = full(saved["p"])
        data["graph"] = graphfeat.build(celex, is_train, y, edges, hub_cap=protocol.HUB_CAP)

    def rows(split: str) -> np.ndarray:
        return np.flatnonzero(ds.mask(split))

    md, cf_, rc = rows("model_dev"), rows("calib_fit"), rows("risk_cert")
    groups_md = fr["split_group"].iloc[md].to_numpy()
    results: dict = {
        "protocol": protocol.PROTOCOL_VERSION,
        "strong_text_epoch": saved["epoch"],
        "nbtext_coverage_eval": round(nb_cov, 4),
        "systems": {},
    }
    certifiers, oof_rp = {}, {}
    for name, blocks in protocol.SYSTEMS.items():
        with timer.stage(name):
            oof, model = _stack_oof(
                _features(md, blocks, data, prior, n_lab), y[md].ravel(), groups_md, n_lab
            )
            oof = oof.reshape(len(md), n_lab)
            raw_cf = model.predict_proba(_features(cf_, blocks, data, prior, n_lab))[:, 1]
            raw_rc = model.predict_proba(_features(rc, blocks, data, prior, n_lab))[:, 1]
            r_rc = raw_rc.reshape(len(rc), n_lab)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
                raw_cf, y[cf_].ravel()
            )
            s_rc = iso.predict(raw_rc).reshape(len(rc), n_lab)
            thresholds = policy.candidate_thresholds(
                raw_cf, min_applied=protocol.GRID_MIN_APPLIED, ratio=protocol.GRID_RATIO
            )
            res: dict = {
                "blocks": list(blocks),
                "model_dev_oof": {
                    "mrp": round(metrics.r_precision(y[md], oof), 4),
                    **{k: round(v, 4) for k, v in metrics.f1_scores(y[md], oof >= 0.5).items()},
                },
                "risk_cert": {
                    "mrp": round(metrics.r_precision(y[rc], r_rc), 4),
                    "ece_top10_pairs": round(
                        metrics.expected_calibration_error_topk(s_rc, y[rc], 10), 4
                    ),
                },
                "policy": {},
            }
            for a in protocol.ALPHAS:
                cert = policy.certify(r_rc, y[rc], thresholds, alpha=a, delta=protocol.DELTA)
                auto = r_rc >= cert.tau if cert.tau is not None else np.zeros_like(y[rc])
                res["policy"][str(a)] = {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in metrics.automation(y[rc], auto).items()
                }
            results["systems"][name] = res
            certifiers[name] = WeightedCertifier(r_rc, y[rc], thresholds)
            unit = certifiers[name].auto_recall(
                np.ones(len(rc), np.int64), protocol.ALPHA_PRIMARY, protocol.DELTA
            )
            expected = res["policy"][str(protocol.ALPHA_PRIMARY)]["auto_recall"]
            if abs(unit - expected) > 1e-4:
                msg = f"{name}: weighted certifier {unit:.4f} != certify {expected:.4f}"
                raise AssertionError(msg)
            order = np.argsort(-oof, axis=1, kind="stable")
            r = y[md].sum(axis=1)
            oof_rp[name] = np.array(
                [y[md][i, order[i, : r[i]]].mean() if r[i] else np.nan for i in range(len(md))]
            )

    with timer.stage("bootstrap"):
        rng = np.random.default_rng(protocol.BOOTSTRAP_SEED)
        names = list(protocol.SYSTEMS)
        ar = {n: np.zeros(protocol.BOOTSTRAP_RESAMPLES) for n in names}
        mrp = {n: np.zeros(protocol.BOOTSTRAP_RESAMPLES) for n in names}
        for b in range(protocol.BOOTSTRAP_RESAMPLES):
            w = np.bincount(rng.integers(0, len(rc), len(rc)), minlength=len(rc))
            idx_md = rng.integers(0, len(md), len(md))
            for n in names:
                ar[n][b] = certifiers[n].auto_recall(w, protocol.ALPHA_PRIMARY, protocol.DELTA)
                mrp[n][b] = np.nanmean(oof_rp[n][idx_md])
        for n in names:
            results["systems"][n]["auto_recall_primary_ci95"] = _ci(ar[n])
        contrasts: list[dict[str, Any]] = []
        for treat, ctrl in protocol.H1_CONTRASTS:
            d_ar = ar[treat] - ar[ctrl]
            point = (
                results["systems"][treat]["policy"][str(protocol.ALPHA_PRIMARY)]["auto_recall"]
                - results["systems"][ctrl]["policy"][str(protocol.ALPHA_PRIMARY)]["auto_recall"]
            )
            contrasts.append(
                {
                    "treatment": treat,
                    "control": ctrl,
                    "auto_recall_diff": round(point, 4),
                    "auto_recall_diff_ci95": _ci(d_ar),
                    "model_dev_mrp_diff_ci95": _ci(mrp[treat] - mrp[ctrl]),
                }
            )
        results["h1"] = {
            "alpha": protocol.ALPHA_PRIMARY,
            "delta": protocol.DELTA,
            "contrasts": contrasts,
            "graph_adds_beyond_text": all(c["auto_recall_diff_ci95"][0] > 0 for c in contrasts),
        }
    results["cost"] = {"stages_s": timer.stages}
    out = paths.REPORTS / "comparison_v1.json"
    out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(orjson.dumps(results["h1"], option=orjson.OPT_INDENT_2).decode())
    return results


if __name__ == "__main__":
    t = time.perf_counter()
    run()
    print(f"{time.perf_counter() - t:.0f}s")
