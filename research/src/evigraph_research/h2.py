"""Protocol 2.0 runner: certified tagging under source duplication (H2).

Clean phase (protocol 1.0 rules): pool = train; stackers on model_dev; thresholds on
calib_fit; certification on risk_cert. Deployment phase: copies of the targets' nearest
train documents are added to the pool; stackers and certified thresholds stay fixed and the
pool-dependent features of risk_cert documents are recomputed.
"""

import os
import time
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import orjson
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression

from evigraph_research import (
    dataset,
    dedup,
    metrics,
    paths,
    policy,
    protocol,
    provenance,
    textmodel,
)
from evigraph_research import protocol_v2 as p2
from evigraph_research.baseline import Timer, _stack_oof
from evigraph_research.compare import _features

# system -> (feature blocks, pool aggregation)
SPEC: dict[str, tuple[tuple[str, ...], str]] = {
    "T1_strong": (("p_strong",), "naive"),
    "C1_strong+knn": (("p_strong", "knn"), "naive"),
    "C1p_strong+knn_prov": (("p_strong", "knn"), "prov"),
    "G1_strong+graph": (("p_strong", "graph"), "naive"),
    "G1p_strong+graph_prov": (("p_strong", "graph"), "prov"),
}


@dataclass
class Fitted:
    model: LogisticRegression
    tau: dict[float, float | None]


@dataclass
class Copies:
    """Up to max(COPIES) copies per source, in generation order (first m are the m-copy set)."""

    source: np.ndarray  # pool index (train order) of each copy's source
    rank: np.ndarray  # copy number within its source, 0..M-1
    x: sp.csr_matrix  # copy vectors
    same_group: np.ndarray  # copy joined its source's provenance group
    jaccard: np.ndarray  # MinHash-estimated Jaccard to the source


def _noisy(text: str, rate: float, rng: np.random.Generator) -> str:
    toks = text[: textmodel.MAX_CHARS].split()
    keep = rng.random(len(toks)) >= rate
    return " ".join(t for t, k in zip(toks, keep, strict=True) if k)


def make_copies(
    sources: np.ndarray, src_texts: list[str], x_train, tf, *, rate: float, n_jobs: int, cfg
) -> Copies:
    m_max = max(cfg.COPIES)
    source = np.repeat(sources, m_max)
    rank = np.tile(np.arange(m_max), len(sources))
    if rate == 0.0:
        n = len(source)
        return Copies(source, rank, x_train[source], np.ones(n, bool), np.ones(n, np.float32))
    rng = np.random.default_rng(cfg.NOISE_SEED + int(rate * 1000))
    texts = [_noisy(src_texts[i // m_max], rate, rng) for i in range(len(source))]
    x = tf.transform(textmodel.counts(texts, n_features=x_train.shape[1], n_jobs=n_jobs))
    sig_src = dedup.signatures(src_texts, mask_digits=False)
    sig_cp = dedup.signatures(texts, mask_digits=False)
    jac = (sig_cp == np.repeat(sig_src, m_max, axis=0)).mean(axis=1).astype(np.float32)
    return Copies(source, rank, x.astype(np.float32).tocsr(), jac >= cfg.PROVENANCE_THRESHOLD, jac)


def _doc_stats(y: np.ndarray, auto: np.ndarray) -> np.ndarray:
    """Per document: applied pairs, errors, correct, gold."""
    applied = auto.sum(axis=1)
    errors = (auto & ~y).sum(axis=1)
    return np.column_stack([applied, errors, applied - errors, y.sum(axis=1)]).astype(np.int64)


def _risk(stats: np.ndarray) -> float:
    a = stats[:, 0].sum()
    return float(stats[:, 1].sum() / a) if a else float("nan")


def _auto_recall(stats: np.ndarray) -> float:
    g = stats[:, 3].sum()
    return float(stats[:, 2].sum() / g) if g else float("nan")


def run(cfg=p2) -> dict:
    adaptive = getattr(cfg, "ADAPTIVE_CANDIDATES", False)
    timer = Timer()
    n_jobs = max(1, (os.cpu_count() or 2) - 1)
    with timer.stage("load"):
        ds = dataset.load(with_text=True)
        protocol.assert_manifest(ds.frame)
        edges = pd.read_parquet(paths.CELLAR_EDGES)
        dups = pd.read_parquet(paths.DUPLICATES).set_index("celex_id")
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    celex = fr["celex_id"].tolist()
    is_train = ds.mask("train")
    train_idx = np.flatnonzero(is_train)
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    pos = np.full(len(fr), -1)
    pos[eval_rows] = np.arange(len(eval_rows))
    md, cf_, rc = (np.flatnonzero(ds.mask(s)) for s in ("model_dev", "calib_fit", "risk_cert"))
    prior = y[is_train].mean(axis=0)
    y_train = y[is_train]
    groups_all = dups.loc[celex, "near_group"].to_numpy()
    groups_train = groups_all[is_train]

    with timer.stage("text_features"):
        tr_path, ev_path = textmodel.tfidf(
            fr.loc[is_train, "text"].tolist(),
            fr["text"].iloc[eval_rows].tolist(),
            n_features=2**21,
            cache_key=protocol.MANIFEST_SHA256,
            n_jobs=n_jobs,
        )
        x_train, x_eval = joblib.load(tr_path), joblib.load(ev_path)
        tf = textmodel.transformer(
            fr.loc[is_train, "text"].tolist(),
            n_features=2**21,
            cache_key=protocol.MANIFEST_SHA256,
            n_jobs=n_jobs,
        )
        saved = joblib.load(paths.STRONG_PREDS)
        if saved["celex_id"] != fr["celex_id"].iloc[eval_rows].tolist():
            raise protocol.ProtocolError("strong predictions are not aligned")
        p_strong = np.zeros((len(fr), n_lab), np.float32)
        p_strong[eval_rows] = saved["p"]

    def pool_features(x_pool, y_pool, g_pool, rows, graph_args) -> dict[str, dict]:
        """Naive and provenance feature dicts for `rows` (other rows are left at zero)."""
        naive, prov, top, _ = provenance.knn_both(
            x_eval[pos[rows]],
            x_pool,
            y_pool,
            k=protocol.KNN_K,
            groups=g_pool,
            candidates=cfg.KNN_CANDIDATES,
            adaptive=adaptive,
        )
        out = {}
        for kind, votes in (("naive", naive), ("prov", prov)):
            d = {"p_strong": p_strong, "knn_vote": np.zeros((len(fr), n_lab), np.float32)}
            d["knn_vote"][rows] = votes
            d["knn_top"] = np.zeros(len(fr), np.float32)
            d["knn_top"][rows] = top
            ext_celex, ext_pool, ext_y, ext_edges, ext_groups = graph_args
            d["graph"] = provenance.graph_features(
                ext_celex,
                ext_pool,
                ext_y,
                ext_edges,
                groups=None if kind == "naive" else ext_groups,
                hub_cap=protocol.HUB_CAP,
            )
            out[kind] = d
        return out

    clean_graph = (celex, is_train, y, edges, groups_all)
    with timer.stage("clean_features"):
        feats = _cached_clean(
            lambda: pool_features(x_train, y_train, groups_train, eval_rows, clean_graph),
            cfg=cfg,
        )

    fitted: dict[str, Fitted] = {}
    clean: dict[str, dict] = {}
    with timer.stage("fit_and_certify"):
        groups_md = fr["split_group"].iloc[md].to_numpy()
        for name, (blocks, kind) in SPEC.items():
            data = feats[kind]
            _, model = _stack_oof(
                _features(md, blocks, data, prior, n_lab), y[md].ravel(), groups_md, n_lab
            )
            raw_cf = model.predict_proba(_features(cf_, blocks, data, prior, n_lab))[:, 1]
            r_rc = model.predict_proba(_features(rc, blocks, data, prior, n_lab))[:, 1]
            r_rc = r_rc.reshape(len(rc), n_lab)
            grid = policy.candidate_thresholds(
                raw_cf, min_applied=protocol.GRID_MIN_APPLIED, ratio=protocol.GRID_RATIO
            )
            tau = {
                a: policy.certify(r_rc, y[rc], grid, alpha=a, delta=protocol.DELTA).tau
                for a in (cfg.ALPHA, cfg.ALPHA_SECONDARY)
            }
            fitted[name] = Fitted(model, tau)
            clean[name] = {
                str(a): metrics.automation(
                    y[rc], r_rc >= t if t is not None else np.zeros_like(y[rc])
                )
                for a, t in tau.items()
            }

    # Targets and their sources (nearest train document by TF-IDF cosine).
    candidates_rc = rc
    excluded_seed = getattr(cfg, "EXCLUDED_TARGET_SEED", None)
    if excluded_seed is not None:  # targets of an earlier version, drawn the same way
        earlier = np.random.default_rng(excluded_seed).choice(rc, cfg.TARGETS, replace=False)
        candidates_rc = np.setdiff1d(rc, earlier)
    rng = np.random.default_rng(cfg.TARGET_SEED)
    targets = np.sort(rng.choice(candidates_rc, cfg.TARGETS, replace=False))
    is_target = np.isin(rc, targets)
    _, _, _, top1 = provenance.knn_both(
        x_eval[pos[targets]], x_train, y_train, k=protocol.KNN_K, groups=None
    )
    sources = np.unique(top1)

    def scores(data_by_kind: dict[str, dict]) -> dict[str, np.ndarray]:
        out = {}
        for name, (blocks, kind) in SPEC.items():
            x = _features(rc, blocks, data_by_kind[kind], prior, n_lab)
            out[name] = fitted[name].model.predict_proba(x)[:, 1].reshape(len(rc), n_lab)
        return out

    stats: dict[tuple, dict[str, dict[float, np.ndarray]]] = {}

    def record(key: tuple, sc: dict[str, np.ndarray]) -> None:
        stats[key] = {}
        for name in SPEC:
            stats[key][name] = {}
            for a, t in fitted[name].tau.items():
                auto = sc[name] >= t if t is not None else np.zeros((len(rc), n_lab), bool)
                stats[key][name][a] = _doc_stats(y[rc], auto)

    record(("clean", 0.0, 0), scores(feats))

    detection = {}
    scenarios = [("dup", r, m) for r in cfg.NOISE for m in cfg.COPIES if m > 0]
    scenarios += [("mislabel", 0.0, m) for m in cfg.MISLABEL_COPIES]
    src_texts = fr["text"].iloc[train_idx[sources]].tolist()
    copies_by_rate: dict[float, Copies] = {}
    wrong = np.random.default_rng(cfg.MISLABEL_SEED).integers(0, len(train_idx), len(sources))

    for kind_s, rate, m in scenarios:
        with timer.stage(f"{kind_s}_noise{rate}_m{m}"):
            if rate not in copies_by_rate:
                copies_by_rate[rate] = make_copies(
                    sources, src_texts, x_train, tf, rate=rate, n_jobs=n_jobs, cfg=cfg
                )
                c = copies_by_rate[rate]
                detection[str(rate)] = {
                    "joined_source_group": round(float(c.same_group.mean()), 4),
                    "mean_jaccard": round(float(c.jaccard.mean()), 4),
                }
            c = copies_by_rate[rate]
            sel = c.rank < m
            src_pool = c.source[sel]
            n_cp = int(sel.sum())
            src_slot = np.searchsorted(sources, src_pool)
            y_cp = y_train[wrong[src_slot]] if kind_s == "mislabel" else y_train[src_pool]
            g_cp = np.where(
                c.same_group[sel],
                groups_train[src_pool],
                np.array([f"copy:{i}" for i in range(n_cp)], dtype=object),
            )
            x_pool = _vstack(x_train, c.x[sel])
            y_pool = np.vstack([y_train, y_cp])
            g_pool = np.concatenate([groups_train.astype(object), g_cp])

            cp_ids = [f"COPY{i}" for i in range(n_cp)]
            src_celex = np.array(celex, dtype=object)[train_idx[src_pool]]
            copy_map = pd.DataFrame({"copy": cp_ids, "src": src_celex})
            cp_edges = copy_map.merge(edges, on="src").drop(columns="src")
            cp_edges = cp_edges.rename(columns={"copy": "src"})
            ext_edges = pd.concat([edges, cp_edges[edges.columns]], ignore_index=True)
            ext_celex = celex + cp_ids
            ext_pool = np.concatenate([is_train, np.ones(n_cp, bool)])
            y_ext = np.vstack([y, y_cp])
            g_ext = np.concatenate([groups_all.astype(object), g_cp])
            feats_s = pool_features(
                x_pool, y_pool, g_pool, rc, (ext_celex, ext_pool, y_ext, ext_edges, g_ext)
            )
            # graph features were computed for the extended node set; keep corpus rows only
            for d in feats_s.values():
                gf = d["graph"]
                gf.votes = {k: v[: len(fr)] for k, v in gf.votes.items()}
                gf.degree = {k: v[: len(fr)] for k, v in gf.degree.items()}
            record((kind_s, rate, m), scores(feats_s))

    with timer.stage("bootstrap"):
        results = _summarise(
            stats,
            is_target,
            clean,
            fitted,
            detection=detection,
            sources=sources,
            targets=targets,
            cfg=cfg,
        )
    results["cost"] = {"stages_s": timer.stages}
    (paths.REPORTS / getattr(cfg, "RESULTS_FILE", "h2_results.json")).write_bytes(
        orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
    )
    print(orjson.dumps(results["decision"], option=orjson.OPT_INDENT_2).decode())
    return results


def _vstack(a, b):
    return sp.vstack([a, b], format="csr")


def _cached_clean(build, *, cfg):
    adaptive = "_adaptive" if getattr(cfg, "ADAPTIVE_CANDIDATES", False) else ""
    name = f"h2_clean_k{protocol.KNN_K}_c{cfg.KNN_CANDIDATES}{adaptive}.joblib"
    path = paths.CACHE / "preds" / name
    if path.exists():
        return joblib.load(path)
    value = build()
    joblib.dump(value, path)
    return value


def _summarise(stats, is_target, clean, fitted, *, detection, sources, targets, cfg) -> dict:
    rng = np.random.default_rng(cfg.BOOTSTRAP_SEED)
    t_idx = np.flatnonzero(is_target)
    boots = [rng.integers(0, len(t_idx), len(t_idx)) for _ in range(cfg.BOOTSTRAP_RESAMPLES)]
    base_key = ("clean", 0.0, 0)

    def ci(values: list[float]) -> list[float]:
        v = np.asarray(values, dtype=float)
        v = v[~np.isnan(v)]
        if not len(v):
            return [float("nan"), float("nan")]
        lo, hi = np.quantile(v, [0.025, 0.975])
        return [round(float(lo), 4), round(float(hi), 4)]

    table = []
    for key, by_sys in stats.items():
        kind, rate, m = key
        for name, by_alpha in by_sys.items():
            for a, st in by_alpha.items():
                tgt = st[t_idx]
                base = stats[base_key][name][a][t_idx]
                row = {
                    "scenario": kind,
                    "noise": rate,
                    "copies": m,
                    "system": name,
                    "alpha": a,
                    "risk_all": round(_risk(st), 4),
                    "auto_recall_all": round(_auto_recall(st), 4),
                    "risk_targets": round(_risk(tgt), 4),
                    "auto_recall_targets": round(_auto_recall(tgt), 4),
                    "applied_targets": int(tgt[:, 0].sum()),
                }
                if a == cfg.ALPHA:
                    row["risk_targets_ci95"] = ci([_risk(tgt[b]) for b in boots])
                    row["risk_change_ci95"] = ci([_risk(tgt[b]) - _risk(base[b]) for b in boots])
                table.append(row)

    def find(kind, rate, m, name, a=cfg.ALPHA):
        return next(
            r
            for r in table
            if (r["scenario"], r["noise"], r["copies"], r["system"], r["alpha"])
            == (kind, rate, m, name, a)
        )

    m_max = max(cfg.COPIES)
    c1 = find("dup", 0.0, m_max, "C1_strong+knn")
    c1p = find("dup", 0.0, m_max, "C1p_strong+knn_prov")
    ar_c1 = clean["C1_strong+knn"][str(cfg.ALPHA)]["auto_recall"]
    ar_c1p = clean["C1p_strong+knn_prov"][str(cfg.ALPHA)]["auto_recall"]
    decision: dict[str, Any] = {
        "H2a_vulnerability": {
            "C1_risk_targets": c1["risk_targets"],
            "ci95": c1["risk_targets_ci95"],
            "met": bool(c1["risk_targets_ci95"][0] > cfg.ALPHA),
        },
        "H2b_invariance": {
            "C1p_risk_change": round(
                c1p["risk_targets"] - find("clean", 0.0, 0, "C1p_strong+knn_prov")["risk_targets"],
                4,
            ),
            "ci95": c1p["risk_change_ci95"],
            "met": bool(c1p["risk_change_ci95"][1] <= cfg.INVARIANCE_MARGIN),
        },
        "H2c_cost": {
            "auto_recall_C1": round(ar_c1, 4),
            "auto_recall_C1p": round(ar_c1p, 4),
            "diff": round(ar_c1p - ar_c1, 4),
            "met": bool(ar_c1p - ar_c1 >= -cfg.COST_MARGIN),
        },
    }
    decision["H2_supported"] = all(v["met"] for v in decision.values())
    if getattr(cfg, "PROTOCOL_VERSION", "") == "2.1":
        g1 = find("dup", 0.0, m_max, "G1_strong+graph")
        g1_base = find("clean", 0.0, 0, "G1_strong+graph")
        decision["H2d_graph_robustness"] = {
            "G1_risk_change": round(g1["risk_targets"] - g1_base["risk_targets"], 4),
            "ci95": g1["risk_change_ci95"],
            "met": bool(g1["risk_change_ci95"][1] <= cfg.INVARIANCE_MARGIN),
        }
    return {
        "protocol": cfg.PROTOCOL_VERSION,
        "targets": len(targets),
        "distinct_sources": len(sources),
        "certified_tau": {n: {str(a): t for a, t in f.tau.items()} for n, f in fitted.items()},
        "clean": {
            n: {
                a: {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}
                for a, d in c.items()
            }
            for n, c in clean.items()
        },
        "copy_detection": detection,
        "table": table,
        "decision": decision,
    }


if __name__ == "__main__":
    t0 = time.perf_counter()
    run()
    print(f"{time.perf_counter() - t0:.0f}s")
