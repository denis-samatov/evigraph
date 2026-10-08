"""Protocol 3.0 runner: the single evaluation on final_test.

For every LEGAL-BERT seed the systems are refitted exactly as in protocols 1.0 and 2.1
(stackers on model_dev, thresholds certified on risk_cert) and applied unchanged to
final_test. Pool-dependent features of final_test documents are computed the same way as for
the certification splits: kNN over the train pool (naive and provenance-aware, adaptive
window), graph votes from train neighbours, TF-IDF and neighbour-text models refitted with
the same deterministic SGD.

`dry_run=True` lets risk_cert play the role of final_test without opening it. The run then
checks that the final-test feature path reproduces the certification-time features and the
certified automation of protocols 1.0 and 2.1; its output goes to a separate file.
"""

import os
import time
from typing import Any

import joblib
import numpy as np
import orjson
import pandas as pd
import scipy.sparse as sp

from evigraph_research import (
    controls,
    dataset,
    graphfeat,
    metrics,
    paths,
    policy,
    protocol,
    provenance,
    textmodel,
)
from evigraph_research import protocol_v3 as cfg
from evigraph_research import protocol_v21 as v21
from evigraph_research.baseline import Timer, _stack_oof
from evigraph_research.compare import _features
from evigraph_research.h2 import _doc_stats, make_copies

# system -> (feature blocks, pool aggregation); protocol 1.0 systems plus the 2.x variants
SYSTEMS: dict[str, tuple[tuple[str, ...], str]] = {
    **{name: (blocks, "naive") for name, blocks in protocol.SYSTEMS.items()},
    "C1p_strong+knn_prov": (("p_strong", "knn"), "prov"),
    "G1p_strong+graph_prov": (("p_strong", "graph"), "prov"),
}
F1_SYSTEMS = (
    "T1_strong",
    "C1_strong+knn",
    "C1p_strong+knn_prov",
    "G1_strong+graph",
    "G1p_strong+graph_prov",
)
F3_SYSTEMS = F1_SYSTEMS
PREDS = paths.CACHE / "preds"


def _strong_files(seed: int) -> tuple[Any, Any]:
    """(certification-split predictions, final_test predictions) of a LEGAL-BERT seed."""
    evals = paths.STRONG_PREDS if seed == 0 else PREDS / f"p_strong_seed{seed}.joblib"
    return evals, PREDS / f"p_strong_final_seed{seed}.joblib"


def _aligned(path, celex: list[str]) -> np.ndarray:
    saved = joblib.load(path)
    if saved["celex_id"] != celex:
        msg = f"{path.name} is not aligned with the expected documents"
        raise protocol.ProtocolError(msg)
    return saved["p"]


def _risk(st: np.ndarray) -> float:
    a = st[:, 0].sum()
    return float(st[:, 1].sum() / a) if a else float("nan")


def _auto_recall(st: np.ndarray) -> float:
    g = st[:, 3].sum()
    return float(st[:, 2].sum() / g) if g else float("nan")


def _ci(values) -> list[float]:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if not len(v):
        return [float("nan"), float("nan")]
    lo, hi = np.quantile(v, [0.025, 0.975])
    return [round(float(lo), 4), round(float(hi), 4)]


def _verdict(point: float, ci: list[float], alpha: float) -> str:
    if ci[0] > alpha:
        return "violated"
    return "holds" if point <= alpha else "inconclusive"


def run(*, seeds: tuple[int, ...] = cfg.SEEDS, dry_run: bool = False) -> dict:  # noqa: PLR0912
    timer = Timer()
    n_jobs = max(1, (os.cpu_count() or 2) - 1)
    with timer.stage("load"):
        ds = dataset.load(with_text=True)
        protocol.assert_manifest(ds.frame)
        if not dry_run:
            protocol.open_final_test("protocol 3.0 evaluation")
        edges = pd.read_parquet(paths.CELLAR_EDGES)
        dups = pd.read_parquet(paths.DUPLICATES).set_index("celex_id")
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    celex = fr["celex_id"].tolist()
    is_train = ds.mask("train")
    train_idx = np.flatnonzero(is_train)
    y_train = y[is_train]
    prior = y_train.mean(axis=0)
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    md, cf_, rc = (np.flatnonzero(ds.mask(s)) for s in ("model_dev", "calib_fit", "risk_cert"))
    ft = rc if dry_run else np.flatnonzero(ds.mask("final_test"))
    groups_all = dups.loc[celex, "near_group"].to_numpy()
    groups_train = groups_all[is_train]
    checks: dict[str, Any] = {}

    # ---- seed-independent features: certification splits from the caches of 1.0 / 2.1
    with timer.stage("cached_features"):
        clean = joblib.load(
            PREDS / f"h2_clean_k{protocol.KNN_K}_c{v21.KNN_CANDIDATES}_adaptive.joblib"
        )
        base: dict[str, dict] = {}
        for kind in ("naive", "prov"):
            base[kind] = {
                "knn_vote": clean[kind]["knn_vote"].copy(),
                "knn_top": clean[kind]["knn_top"].copy(),
                "graph": clean[kind]["graph"],  # computed for every corpus row
            }
        for name, file in (
            ("p_tfidf", "p_tfidf"),
            ("p_nbtext", f"p_nbtext_top{protocol.NBTEXT_TOP_TERMS}"),
        ):
            full = np.zeros((len(fr), n_lab), np.float32)
            full[eval_rows] = joblib.load(PREDS / f"{file}.joblib")
            for d in base.values():
                d[name] = full

    # ---- the same features for final_test documents
    with timer.stage("final_text_features"):
        tr_path, ev_path = textmodel.tfidf(
            [], [], n_features=2**21, cache_key=protocol.MANIFEST_SHA256, n_jobs=n_jobs
        )
        x_train = joblib.load(tr_path)
        tf = textmodel.transformer(
            [], n_features=2**21, cache_key=protocol.MANIFEST_SHA256, n_jobs=n_jobs
        )
        texts_ft = fr["text"].iloc[ft].tolist()
        x_ft = tf.transform(textmodel.counts(texts_ft, n_features=2**21, n_jobs=n_jobs))
        x_ft = x_ft.astype(np.float32).tocsr()
        out_dir = paths.CACHE / ("final_dryrun" if dry_run else "final")
        out_dir.mkdir(parents=True, exist_ok=True)
        ft_path = out_dir / "x_tfidf.joblib"
        joblib.dump(x_ft, ft_path)

        nb = graphfeat.reference_neighbours(
            celex, fr["publication_date"].to_numpy(), is_train, edges, hub_cap=protocol.HUB_CAP
        )
        ntr, _ = controls.nbtext_matrices(
            tr_path,
            ev_path,
            nb[train_idx][:, train_idx],
            nb[eval_rows][:, train_idx],
            cache_key=protocol.MANIFEST_SHA256[:16],
            top_terms=protocol.NBTEXT_TOP_TERMS,
        )
        nbx_ft = controls._neighbour_text(nb[ft][:, train_idx], x_train, protocol.NBTEXT_TOP_TERMS)
        nb_path = out_dir / "x_nbtext.joblib"
        joblib.dump(sp.hstack([x_ft, nbx_ft], format="csr", dtype=np.float32), nb_path)

    with timer.stage("final_text_models"):
        p_tfidf_ft = textmodel.fit_predict(tr_path, ft_path, y_train, n_jobs=n_jobs)
        p_nbtext_ft = textmodel.fit_predict(ntr, nb_path, y_train, n_jobs=n_jobs)

    with timer.stage("final_knn"):
        naive, prov, top, _ = provenance.knn_both(
            x_ft,
            x_train,
            y_train,
            k=protocol.KNN_K,
            groups=groups_train,
            candidates=v21.KNN_CANDIDATES,
            adaptive=True,
        )

    if dry_run:  # the final-test path must reproduce the certification-time features
        checks["features_max_abs_diff"] = {
            "p_tfidf": float(np.abs(p_tfidf_ft - base["naive"]["p_tfidf"][ft]).max()),
            "p_nbtext": float(np.abs(p_nbtext_ft - base["naive"]["p_nbtext"][ft]).max()),
            "knn_naive": float(np.abs(naive - base["naive"]["knn_vote"][ft]).max()),
            "knn_prov": float(np.abs(prov - base["prov"]["knn_vote"][ft]).max()),
            "knn_top": float(np.abs(top - base["naive"]["knn_top"][ft]).max()),
        }
        print(checks, flush=True)
    for kind, votes in (("naive", naive), ("prov", prov)):
        d = base[kind]
        d["knn_vote"] = d["knn_vote"].copy()
        d["knn_top"] = d["knn_top"].copy()
        d["knn_vote"][ft] = votes
        d["knn_top"][ft] = top
        for name, p in (("p_tfidf", p_tfidf_ft), ("p_nbtext", p_nbtext_ft)):
            d[name] = d[name].copy()
            d[name][ft] = p

    # ---- F3 deployment features: copies of the sources of final_test targets
    rng = np.random.default_rng(cfg.FINAL_TARGET_SEED)
    targets = np.sort(rng.choice(ft, cfg.TARGETS, replace=False))
    t_pos = np.searchsorted(ft, targets)
    _, _, _, top1 = provenance.knn_both(
        x_ft[t_pos], x_train, y_train, k=protocol.KNN_K, groups=None
    )
    sources = np.unique(top1)
    members = [np.flatnonzero(top1 == src) for src in sources]  # targets of each source
    src_texts = fr["text"].iloc[train_idx[sources]].tolist()
    deployed: dict[tuple[float, int], dict[str, dict]] = {}
    detection: dict[str, dict] = {}
    for rate in cfg.NOISE:
        copies = make_copies(sources, src_texts, x_train, tf, rate=rate, n_jobs=n_jobs, cfg=v21)
        detection[str(rate)] = {
            "joined_source_group": round(float(copies.same_group.mean()), 4),
            "mean_jaccard": round(float(copies.jaccard.mean()), 4),
        }
        for m in cfg.COPIES:
            if m == 0:
                continue
            with timer.stage(f"copies_noise{rate}_m{m}"):
                sel = copies.rank < m
                src = copies.source[sel]
                n_cp = len(src)
                x_pool = sp.vstack([x_train, copies.x[sel]], format="csr")
                y_cp = y_train[src]
                g_cp = np.where(
                    copies.same_group[sel],
                    groups_train[src].astype(object),
                    np.array([f"copy:{i}" for i in range(n_cp)], dtype=object),
                )
                nv, pv, tp, _ = provenance.knn_both(
                    x_ft[t_pos],
                    x_pool,
                    np.vstack([y_train, y_cp]),
                    k=protocol.KNN_K,
                    groups=np.concatenate([groups_train.astype(object), g_cp]),
                    candidates=v21.KNN_CANDIDATES,
                    adaptive=True,
                )
                cp_ids = [f"COPY{i}" for i in range(n_cp)]
                copy_map = pd.DataFrame(
                    {"copy": cp_ids, "src": np.array(celex, dtype=object)[train_idx[src]]}
                )
                cp_edges = copy_map.merge(edges, on="src").drop(columns="src")
                cp_edges = cp_edges.rename(columns={"copy": "src"})
                ext_edges = pd.concat([edges, cp_edges[edges.columns]], ignore_index=True)
                ext_args = (
                    celex + cp_ids,
                    np.concatenate([is_train, np.ones(n_cp, bool)]),
                    np.vstack([y, y_cp]),
                    ext_edges,
                )
                g_ext = np.concatenate([groups_all.astype(object), g_cp])
                deployed[rate, m] = {}
                for kind, votes in (("naive", nv), ("prov", pv)):
                    gf = provenance.graph_features(
                        *ext_args,
                        groups=None if kind == "naive" else g_ext,
                        hub_cap=protocol.HUB_CAP,
                    )
                    gf.votes = {k: v[: len(fr)] for k, v in gf.votes.items()}
                    gf.degree = {k: v[: len(fr)] for k, v in gf.degree.items()}
                    d = dict(base[kind])
                    d["knn_vote"] = d["knn_vote"].copy()
                    d["knn_top"] = d["knn_top"].copy()
                    d["knn_vote"][targets] = votes
                    d["knn_top"][targets] = tp
                    d["graph"] = gf
                    deployed[rate, m][kind] = d

    # ---- per seed: fit, certify, evaluate
    results: dict[str, Any] = {
        "protocol": cfg.PROTOCOL_VERSION,
        "dry_run": dry_run,
        "final_docs": len(ft),
        "targets": len(targets),
        "distinct_sources": len(sources),
        "copy_detection": detection,
        "seeds": {},
    }
    groups_md = fr["split_group"].iloc[md].to_numpy()
    boot_rng = np.random.default_rng(cfg.BOOTSTRAP_SEED)
    boots_ft = [boot_rng.integers(0, len(ft), len(ft)) for _ in range(cfg.BOOTSTRAP_RESAMPLES)]
    # F3 intervals resample sources (clusters of targets sharing a copied source)
    boots_t = [
        np.concatenate([members[c] for c in boot_rng.integers(0, len(members), len(members))])
        for _ in range(cfg.BOOTSTRAP_RESAMPLES)
    ]
    for seed in seeds:
        evals_path, final_path = _strong_files(seed)
        if not evals_path.exists() or not (dry_run or final_path.exists()):
            results["seeds"][str(seed)] = {"missing": True}
            continue
        with timer.stage(f"seed{seed}"):
            p_strong = np.zeros((len(fr), n_lab), np.float32)
            p_strong[eval_rows] = _aligned(evals_path, fr["celex_id"].iloc[eval_rows].tolist())
            if not dry_run:
                p_strong[ft] = _aligned(final_path, fr["celex_id"].iloc[ft].tolist())
            res = _evaluate_seed(
                p_strong=p_strong,
                base=base,
                deployed=deployed,
                y=y,
                prior=prior,
                n_lab=n_lab,
                md=md,
                cf_=cf_,
                rc=rc,
                ft=ft,
                targets=targets,
                groups_md=groups_md,
                boots_ft=boots_ft,
                boots_t=boots_t,
            )
        results["seeds"][str(seed)] = res
    results["summary"] = _summary(results["seeds"])
    results["checks"] = checks
    results["cost"] = {"stages_s": timer.stages}
    name = "final_dryrun_v3.json" if dry_run else cfg.RESULTS_FILE
    (paths.REPORTS / name).write_bytes(
        orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
    )
    print(orjson.dumps(results["summary"], option=orjson.OPT_INDENT_2).decode())
    return results


def _evaluate_seed(
    *,
    p_strong,
    base,
    deployed,
    y,
    prior,
    n_lab,
    md,
    cf_,
    rc,
    ft,
    targets,
    groups_md,
    boots_ft,
    boots_t,
) -> dict:
    alphas = (cfg.ALPHA, cfg.ALPHA_SECONDARY)
    t_pos = np.searchsorted(ft, targets)
    systems: dict[str, dict] = {}
    stats_ft: dict[str, np.ndarray] = {}
    stats_t: dict[str, dict[tuple[float, int], np.ndarray]] = {}
    for name, (blocks, kind) in SYSTEMS.items():
        data = dict(base[kind], p_strong=p_strong)
        _, model = _stack_oof(
            _features(md, blocks, data, prior, n_lab), y[md].ravel(), groups_md, n_lab
        )
        raw_cf = model.predict_proba(_features(cf_, blocks, data, prior, n_lab))[:, 1]
        r_rc = model.predict_proba(_features(rc, blocks, data, prior, n_lab))[:, 1]
        r_rc = r_rc.reshape(len(rc), n_lab)
        s_ft = model.predict_proba(_features(ft, blocks, data, prior, n_lab))[:, 1]
        s_ft = s_ft.reshape(len(ft), n_lab)
        grid = policy.candidate_thresholds(
            raw_cf, min_applied=protocol.GRID_MIN_APPLIED, ratio=protocol.GRID_RATIO
        )
        tau = {
            a: policy.certify(r_rc, y[rc], grid, alpha=a, delta=protocol.DELTA).tau for a in alphas
        }
        row: dict[str, Any] = {
            "final_mrp": round(metrics.r_precision(y[ft], s_ft), 4),
            "risk_cert_mrp": round(metrics.r_precision(y[rc], r_rc), 4),
            "by_alpha": {},
        }
        for a, t in tau.items():
            cert_auto = r_rc >= t if t is not None else np.zeros_like(y[rc])
            ft_auto = s_ft >= t if t is not None else np.zeros_like(y[ft])
            st = _doc_stats(y[ft], ft_auto)
            row["by_alpha"][str(a)] = {
                "tau": t,
                "certified_auto_recall_risk_cert": round(
                    metrics.automation(y[rc], cert_auto)["auto_recall"], 4
                ),
                "final_risk": round(_risk(st), 4),
                "final_auto_recall": round(_auto_recall(st), 4),
                "final_applied": int(st[:, 0].sum()),
            }
            if a == cfg.ALPHA:
                stats_ft[name] = st
                point = _risk(st)
                ci = _ci([_risk(st[b]) for b in boots_ft])
                row["by_alpha"][str(a)]["final_risk_ci95"] = ci
                row["by_alpha"][str(a)]["final_auto_recall_ci95"] = _ci(
                    [_auto_recall(st[b]) for b in boots_ft]
                )
                row["by_alpha"][str(a)]["F1_verdict"] = _verdict(point, ci, cfg.ALPHA)
        systems[name] = row

        if name in F3_SYSTEMS:
            t_alpha = tau[cfg.ALPHA]
            stats_t[name] = {(0.0, 0): stats_ft[name][t_pos]}
            for (rate, m), by_kind in deployed.items():
                d = dict(by_kind[kind], p_strong=p_strong)
                s_t = model.predict_proba(_features(targets, blocks, d, prior, n_lab))[:, 1]
                s_t = s_t.reshape(len(targets), n_lab)
                auto = s_t >= t_alpha if t_alpha is not None else np.zeros_like(y[targets])
                stats_t[name][rate, m] = _doc_stats(y[targets], auto)

    contrasts: list[dict[str, Any]] = []
    for treat, ctrl in protocol.H1_CONTRASTS:
        a, b = stats_ft[treat], stats_ft[ctrl]
        contrasts.append(
            {
                "treatment": treat,
                "control": ctrl,
                "auto_recall_diff": round(_auto_recall(a) - _auto_recall(b), 4),
                "ci95": _ci([_auto_recall(a[i]) - _auto_recall(b[i]) for i in boots_ft]),
            }
        )
    f2 = {
        "contrasts": contrasts,
        "graph_adds_beyond_text": all(c["ci95"][0] > 0 for c in contrasts),
    }

    h2_table = []
    for name, by_m in stats_t.items():
        base_st = by_m[0.0, 0]
        for (rate, m), st in by_m.items():
            st_all = stats_ft[name].copy()  # marginal: every final_test document
            st_all[t_pos] = st
            h2_table.append(
                {
                    "system": name,
                    "noise": rate,
                    "copies": m,
                    "risk_all": round(_risk(st_all), 4),
                    "risk_targets": round(_risk(st), 4),
                    "auto_recall_targets": round(_auto_recall(st), 4),
                    "risk_targets_ci95": _ci([_risk(st[b]) for b in boots_t]),
                    "risk_change_ci95": _ci([_risk(st[b]) - _risk(base_st[b]) for b in boots_t]),
                }
            )

    def find(name: str, m: int) -> dict:  # decision rules use exact copies
        return next(r for r in h2_table if (r["system"], r["noise"], r["copies"]) == (name, 0.0, m))

    m_max = max(cfg.COPIES)
    c1, c1p, g1 = (
        find(n, m_max) for n in ("C1_strong+knn", "C1p_strong+knn_prov", "G1_strong+graph")
    )
    ar = {n: _auto_recall(stats_ft[n]) for n in ("C1_strong+knn", "C1p_strong+knn_prov")}
    f3 = {
        "H2a_vulnerability": {
            "C1_risk_targets": c1["risk_targets"],
            "ci95": c1["risk_targets_ci95"],
            "met": bool(c1["risk_targets_ci95"][0] > cfg.ALPHA),
        },
        "H2b_invariance": {
            "C1p_risk_change": round(
                c1p["risk_targets"] - find("C1p_strong+knn_prov", 0)["risk_targets"], 4
            ),
            "ci95": c1p["risk_change_ci95"],
            "met": bool(c1p["risk_change_ci95"][1] <= cfg.INVARIANCE_MARGIN),
        },
        "H2c_cost": {  # on the clean final_test, all documents
            "diff": round(ar["C1p_strong+knn_prov"] - ar["C1_strong+knn"], 4),
            "met": bool(ar["C1p_strong+knn_prov"] - ar["C1_strong+knn"] >= -cfg.COST_MARGIN),
        },
        "H2d_graph_robustness": {
            "G1_risk_change": round(
                g1["risk_targets"] - find("G1_strong+graph", 0)["risk_targets"], 4
            ),
            "ci95": g1["risk_change_ci95"],
            "met": bool(g1["risk_change_ci95"][1] <= cfg.INVARIANCE_MARGIN),
        },
    }
    f1 = {n: systems[n]["by_alpha"][str(cfg.ALPHA)]["F1_verdict"] for n in F1_SYSTEMS}
    return {"systems": systems, "F1": f1, "F2": f2, "F3": f3, "h2_table": h2_table}


def _summary(by_seed: dict[str, dict]) -> dict:
    done = {s: r for s, r in by_seed.items() if not r.get("missing")}
    out: dict[str, Any] = {
        "seeds_evaluated": sorted(done),
        "seeds_missing": sorted(set(by_seed) - set(done)),
    }
    if not done:
        return out
    out["F1"] = {n: [r["F1"][n] for r in done.values()] for n in F1_SYSTEMS}
    out["F2_graph_adds_beyond_text"] = (
        f"{sum(r['F2']['graph_adds_beyond_text'] for r in done.values())} of {len(done)}"
    )
    out["F3"] = {
        rule: f"{sum(r['F3'][rule]['met'] for r in done.values())} of {len(done)}"
        for rule in next(iter(done.values()))["F3"]
    }
    return out


if __name__ == "__main__":
    t0 = time.perf_counter()
    run(dry_run=True)
    print(f"{time.perf_counter() - t0:.0f}s")
