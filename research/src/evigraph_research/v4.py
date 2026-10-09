"""Protocol 4.0 runner: copy detection under edits (H3) and re-certification under drift (H4).

Stackers and certified thresholds are rebuilt exactly as in protocol 3.0 (model_dev, calib_fit
grid, risk_cert certification) for T1, C1 and C1p of every LEGAL-BERT seed. Built-in check: the
exact-copy scenario on the protocol 2.1 risk_cert targets must reproduce the 2.1 result for C1.
"""

import os
import re
import time
from typing import Any

import joblib
import numpy as np
import orjson
import pandas as pd
import scipy.sparse as sp

from evigraph_research import dataset, dedup, paths, policy, protocol, provenance, textmodel
from evigraph_research import protocol_v2 as v2
from evigraph_research import protocol_v3 as v3
from evigraph_research import protocol_v4 as cfg
from evigraph_research import protocol_v21 as v21
from evigraph_research.baseline import Timer, _stack_oof
from evigraph_research.compare import _features
from evigraph_research.final import _aligned, _auto_recall, _ci, _risk, _strong_files
from evigraph_research.h2 import _doc_stats

SYSTEMS: dict[str, tuple[tuple[str, ...], str]] = {
    "T1_strong": (("p_strong",), "naive"),
    "C1_strong+knn": (("p_strong", "knn"), "naive"),
    "C1p_strong+knn_prov": (("p_strong", "knn"), "prov"),
}
TOKEN = re.compile(r"\w+")


def _words(text: str) -> set[str]:
    return set(TOKEN.findall(text[: textmodel.MAX_CHARS].lower()))


def _edit(text: str, kind: str, rate: float, rng: np.random.Generator, vocab: list[str]) -> str:
    toks = text[: textmodel.MAX_CHARS].split()
    hit = rng.random(len(toks)) < rate
    if kind == "del":
        return " ".join(t for t, h in zip(toks, hit, strict=True) if not h)
    return " ".join(
        vocab[rng.integers(len(vocab))] if h else t for t, h in zip(toks, hit, strict=True)
    )


def _clustered_boots(members: list[np.ndarray], rng: np.random.Generator) -> list[np.ndarray]:
    return [
        np.concatenate([members[c] for c in rng.integers(0, len(members), len(members))])
        for _ in range(cfg.BOOTSTRAP_RESAMPLES)
    ]


def run() -> dict:
    timer = Timer()
    n_jobs = max(1, (os.cpu_count() or 2) - 1)
    with timer.stage("load"):
        ds = dataset.load(with_text=True)
        protocol.assert_manifest(ds.frame)
        protocol.open_final_test("protocol 4.0 (H3 targets, H4 audit and evaluation)")
        dups = pd.read_parquet(paths.DUPLICATES).set_index("celex_id")
    fr, y, n_lab = ds.frame, ds.y, len(ds.labels)
    celex = fr["celex_id"].tolist()
    texts = fr["text"].tolist()
    is_train = ds.mask("train")
    train_idx = np.flatnonzero(is_train)
    y_train = y[is_train]
    prior = y_train.mean(axis=0)
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))
    pos = np.full(len(fr), -1)
    pos[eval_rows] = np.arange(len(eval_rows))
    md, cf_, rc = (np.flatnonzero(ds.mask(s)) for s in ("model_dev", "calib_fit", "risk_cert"))
    ft = np.flatnonzero(ds.mask("final_test"))
    ft_pos = np.full(len(fr), -1)
    ft_pos[ft] = np.arange(len(ft))
    groups_train = dups.loc[celex, "near_group"].to_numpy()[is_train].astype(object)

    with timer.stage("features"):
        tr_path, ev_path = textmodel.tfidf(
            [], [], n_features=2**21, cache_key=protocol.MANIFEST_SHA256, n_jobs=n_jobs
        )
        x_train, x_eval = joblib.load(tr_path), joblib.load(ev_path)
        tf = textmodel.transformer(
            [], n_features=2**21, cache_key=protocol.MANIFEST_SHA256, n_jobs=n_jobs
        )
        x_ft = tf.transform(
            textmodel.counts([texts[i] for i in ft], n_features=2**21, n_jobs=n_jobs)
        )
        x_ft = x_ft.astype(np.float32).tocsr()
        clean = joblib.load(
            paths.CACHE
            / "preds"
            / f"h2_clean_k{protocol.KNN_K}_c{v21.KNN_CANDIDATES}_adaptive.joblib"
        )
        naive, prov, top, _ = provenance.knn_both(
            x_ft,
            x_train,
            y_train,
            k=protocol.KNN_K,
            groups=groups_train,
            candidates=v21.KNN_CANDIDATES,
            adaptive=True,
        )
        base: dict[str, dict] = {}
        for kind, votes in (("naive", naive), ("prov", prov)):
            d = {
                "knn_vote": clean[kind]["knn_vote"].copy(),
                "knn_top": clean[kind]["knn_top"].copy(),
            }
            d["knn_vote"][ft] = votes
            d["knn_top"][ft] = top
            base[kind] = d

    def query(rows: np.ndarray) -> sp.csr_matrix:
        if np.all(ft_pos[rows] >= 0):
            return x_ft[ft_pos[rows]]
        return x_eval[pos[rows]]

    # ---- fitted systems per seed
    fitted: dict[int, dict[str, dict]] = {}
    with timer.stage("fit_and_certify"):
        groups_md = fr["split_group"].iloc[md].to_numpy()
        for seed in cfg.SEEDS:
            evals_path, final_path = _strong_files(seed)
            p_strong = np.zeros((len(fr), n_lab), np.float32)
            p_strong[eval_rows] = _aligned(evals_path, fr["celex_id"].iloc[eval_rows].tolist())
            p_strong[ft] = _aligned(final_path, fr["celex_id"].iloc[ft].tolist())
            fitted[seed] = {}
            for name, (blocks, kind) in SYSTEMS.items():
                data = dict(base[kind], p_strong=p_strong)
                _, model = _stack_oof(
                    _features(md, blocks, data, prior, n_lab), y[md].ravel(), groups_md, n_lab
                )
                raw_cf = model.predict_proba(_features(cf_, blocks, data, prior, n_lab))[:, 1]
                grid = policy.candidate_thresholds(
                    raw_cf, min_applied=protocol.GRID_MIN_APPLIED, ratio=protocol.GRID_RATIO
                )
                r_rc = model.predict_proba(_features(rc, blocks, data, prior, n_lab))[:, 1]
                r_rc = r_rc.reshape(len(rc), n_lab)
                s_ft = model.predict_proba(_features(ft, blocks, data, prior, n_lab))[:, 1]
                tau = {
                    a: policy.certify(r_rc, y[rc], grid, alpha=a, delta=protocol.DELTA).tau
                    for a in (cfg.ALPHA, cfg.ALPHA_SECONDARY)
                }
                fitted[seed][name] = {
                    "model": model,
                    "blocks": blocks,
                    "kind": kind,
                    "grid": grid,
                    "tau": tau,
                    "s_ft": s_ft.reshape(len(ft), n_lab),
                    "p_strong": p_strong,
                }

    results: dict[str, Any] = {"protocol": cfg.PROTOCOL_VERSION, "checks": {}}
    with timer.stage("h4"):
        results["h4"] = _h4(fitted, fr, y, ft)

    # ---- H3 target sets
    earlier3 = np.sort(
        np.random.default_rng(v3.FINAL_TARGET_SEED).choice(ft, v3.TARGETS, replace=False)
    )
    t_final = np.sort(
        np.random.default_rng(cfg.FINAL_TARGET_SEED).choice(
            np.setdiff1d(ft, earlier3), cfg.TARGETS, replace=False
        )
    )
    earlier2 = np.random.default_rng(v2.TARGET_SEED).choice(rc, v2.TARGETS, replace=False)
    t_rc = np.sort(
        np.random.default_rng(v21.TARGET_SEED).choice(
            np.setdiff1d(rc, earlier2), v21.TARGETS, replace=False
        )
    )
    vocab_rng = np.random.default_rng(cfg.EDIT_SEED)
    vocab = " ".join(texts[i][:20_000] for i in vocab_rng.choice(train_idx, 500)).split()
    word_cache: dict[int, set[str]] = {}

    def words_of(i: int) -> set[str]:  # train position -> word types
        if i not in word_cache:
            word_cache[i] = _words(texts[train_idx[i]])
        return word_cache[i]

    results["h3"] = {}
    for set_name, targets in (("final_test", t_final), ("risk_cert", t_rc)):
        with timer.stage(f"h3_{set_name}"):
            results["h3"][set_name] = _h3(
                targets=targets,
                x_q=query(targets),
                x_train=x_train,
                y_train=y_train,
                groups_train=groups_train,
                texts=texts,
                train_idx=train_idx,
                tf=tf,
                vocab=vocab,
                words_of=words_of,
                fitted=fitted,
                base=base,
                y=y,
                prior=prior,
                n_lab=n_lab,
                n_jobs=n_jobs,
                timer=timer,
            )
    exact = next(
        r
        for r in results["h3"]["risk_cert"]["seeds"]["0"]["table"]
        if (r["kind"], r["rate"], r["system"]) == ("exact", 0.0, "C1_strong+knn")
    )
    results["checks"]["rc_exact_C1_risk_targets"] = exact["risk_targets"]
    results["checks"]["protocol_21_C1_risk_targets"] = 0.1631
    results["summary"] = _summary(results)
    results["cost"] = {"stages_s": timer.stages}
    (paths.REPORTS / cfg.RESULTS_FILE).write_bytes(
        orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
    )
    print(orjson.dumps(results["summary"], option=orjson.OPT_INDENT_2).decode())
    return results


def _h4(fitted, fr, y, ft) -> dict:
    dates = fr["publication_date"].iloc[ft].to_numpy()
    split = np.datetime64(cfg.SPLIT_DATE)
    audit_pool = np.flatnonzero(dates < split)  # positions within ft
    evaluation = np.flatnonzero(dates >= split)
    y_ft = y[ft]
    out: dict[str, Any] = {
        "audit_pool": len(audit_pool),
        "evaluation": len(evaluation),
        "seeds": {},
    }
    for seed, systems in fitted.items():
        out["seeds"][str(seed)] = {}
        for name in cfg.H4_SYSTEMS:
            f = systems[name]
            s = f["s_ft"]
            by_alpha = {}
            for a in (cfg.ALPHA, cfg.ALPHA_SECONDARY):
                t0 = f["tau"][a]
                auto0 = s[evaluation] >= t0 if t0 is not None else np.zeros_like(y_ft[evaluation])
                st0 = _doc_stats(y_ft[evaluation], auto0)
                row: dict[str, Any] = {
                    "original": {
                        "risk": round(_risk(st0), 4),
                        "auto_recall": round(_auto_recall(st0), 4),
                    },
                    "audit": {},
                }
                for n in cfg.AUDIT_SIZES:
                    risks, recalls, none = [], [], 0
                    for d in range(cfg.AUDIT_DRAWS):
                        sample = np.random.default_rng(d).choice(audit_pool, n, replace=False)
                        t = policy.certify(
                            s[sample], y_ft[sample], f["grid"], alpha=a, delta=protocol.DELTA
                        ).tau
                        if t is None:
                            none += 1
                            risks.append(float("nan"))
                            recalls.append(0.0)
                            continue
                        st = _doc_stats(y_ft[evaluation], s[evaluation] >= t)
                        risks.append(_risk(st))
                        recalls.append(_auto_recall(st))
                    r = np.asarray(risks)
                    row["audit"][str(n)] = {
                        "violation_share": round(float(np.nansum(r > a) / cfg.AUDIT_DRAWS), 3),
                        "risk_mean": round(float(np.nanmean(r)), 4)
                        if np.isfinite(r).any()
                        else None,
                        "risk_max": round(float(np.nanmax(r)), 4) if np.isfinite(r).any() else None,
                        "auto_recall_mean": round(float(np.mean(recalls)), 4),
                        "not_certified": none,
                    }
                by_alpha[str(a)] = row
            out["seeds"][str(seed)][name] = by_alpha
    return out


def _h3(
    *,
    targets,
    x_q,
    x_train,
    y_train,
    groups_train,
    texts,
    train_idx,
    tf,
    vocab,
    words_of,
    fitted,
    base,
    y,
    prior,
    n_lab,
    n_jobs,
    timer,
) -> dict:
    _, _, _, top1 = provenance.knn_both(x_q, x_train, y_train, k=protocol.KNN_K, groups=None)
    sources = np.unique(top1)
    members = [np.flatnonzero(top1 == s) for s in sources]
    boots = _clustered_boots(members, np.random.default_rng(cfg.BOOTSTRAP_SEED))
    # candidate sources of copies: each source and its nearest train documents
    sim = (x_train[sources] @ x_train.T).toarray()
    sim[np.arange(len(sources)), sources] = 2.0  # the source itself is always a candidate
    cands = np.argpartition(-sim, cfg.ATTRIBUTION_CANDIDATES, axis=1)[
        :, : cfg.ATTRIBUTION_CANDIDATES + 1
    ]
    del sim
    src_texts = [texts[train_idx[s]] for s in sources]
    m = cfg.COPIES
    copy_src_slot = np.repeat(np.arange(len(sources)), m)
    copy_src = sources[copy_src_slot]
    y_pool = np.vstack([y_train, y_train[copy_src]])

    def stats_for(name: str, seed: int, votes: np.ndarray, top: np.ndarray, tau: float | None):
        f = fitted[seed][name]
        d = dict(base[f["kind"]], p_strong=f["p_strong"])
        d["knn_vote"] = d["knn_vote"].copy()
        d["knn_top"] = d["knn_top"].copy()
        d["knn_vote"][targets] = votes
        d["knn_top"][targets] = top
        s = f["model"].predict_proba(_features(targets, f["blocks"], d, prior, n_lab))[:, 1]
        s = s.reshape(len(targets), n_lab)
        auto = s >= tau if tau is not None else np.zeros((len(targets), n_lab), bool)
        return _doc_stats(y[targets], auto)

    # clean (m = 0) statistics
    clean_stats = {}
    for seed in fitted:
        for name in SYSTEMS:
            f = fitted[seed][name]
            clean_stats[seed, name] = stats_for(
                name,
                seed,
                base[f["kind"]]["knn_vote"][targets],
                base[f["kind"]]["knn_top"][targets],
                f["tau"][cfg.ALPHA],
            )

    scenarios = [("exact", 0.0)] + [(k, r) for k in cfg.EDIT_KINDS for r in cfg.EDIT_RATES]
    table: dict[str, list] = {str(s): [] for s in fitted}
    attribution_rows = []
    for kind, rate in scenarios:
        with timer.stage(f"  {kind}{rate}"):
            if kind == "exact":
                x_cp = x_train[copy_src]
                copy_texts = None
            else:
                rng = np.random.default_rng(
                    [cfg.EDIT_SEED, cfg.EDIT_KINDS.index(kind), int(rate * 1000)]
                )
                copy_texts = [
                    _edit(src_texts[slot], kind, rate, rng, vocab) for slot in copy_src_slot
                ]
                x_cp = tf.transform(
                    textmodel.counts(copy_texts, n_features=x_train.shape[1], n_jobs=n_jobs)
                )
                x_cp = x_cp.astype(np.float32).tocsr()
            # candidate = nearest train document among the source's candidates
            cand = np.empty(len(copy_src), np.int64)
            cos = np.empty(len(copy_src), np.float32)
            for slot in range(len(sources)):
                rows = slice(slot * m, (slot + 1) * m)
                c = cands[slot]
                sims = (x_cp[rows] @ x_train[c].T).toarray()
                j = sims.argmax(axis=1)
                cand[rows], cos[rows] = c[j], sims[np.arange(m), j]
            if copy_texts is None:
                jac = np.ones(len(copy_src), np.float32)
                cont = np.ones(len(copy_src), np.float32)
            else:
                uniq = np.unique(cand)
                sig_c = dedup.signatures([texts[train_idx[i]] for i in uniq], mask_digits=False)
                sig_cp = dedup.signatures(copy_texts, mask_digits=False)
                jac = (sig_cp == sig_c[np.searchsorted(uniq, cand)]).mean(axis=1).astype(np.float32)
                cont = np.array(
                    [
                        len((w := _words(t)) & words_of(int(c))) / max(len(w), 1)
                        for t, c in zip(copy_texts, cand, strict=True)
                    ],
                    np.float32,
                )
            score = {"minhash": jac, "cosine": cos, "containment": cont}
            correct = groups_train[cand] == groups_train[copy_src]
            x_pool = sp.vstack([x_train, x_cp], format="csr")
            votes: dict[str, np.ndarray] = {}
            row_attr: dict[str, Any] = {"kind": kind, "rate": rate}
            nv = tp = np.empty(0)
            for method, thr in cfg.ATTRIBUTION.items():
                attributed = score[method] >= thr
                g_cp = np.where(
                    attributed,
                    groups_train[cand],
                    np.array([f"copy:{i}" for i in range(len(copy_src))], dtype=object),
                )
                nv, pv, tp, _ = provenance.knn_both(
                    x_q,
                    x_pool,
                    y_pool,
                    k=protocol.KNN_K,
                    groups=np.concatenate([groups_train, g_cp]),
                    candidates=v21.KNN_CANDIDATES,
                    adaptive=True,
                )
                assert pv is not None
                votes[method] = pv
                row_attr[method] = {
                    "attributed": round(float(attributed.mean()), 4),
                    "attributed_to_source_group": round(float((attributed & correct).mean()), 4),
                }
            row_attr["median_cosine"] = round(float(np.median(cos)), 3)
            attribution_rows.append(row_attr)
            for seed in fitted:
                variants = [("C1_strong+knn", "naive", nv)] + [
                    ("C1p_strong+knn_prov", method, votes[method]) for method in cfg.ATTRIBUTION
                ]
                for name, method, v in variants:
                    st = stats_for(name, seed, v, tp, fitted[seed][name]["tau"][cfg.ALPHA])
                    base_st = clean_stats[seed, name]
                    table[str(seed)].append(
                        {
                            "kind": kind,
                            "rate": rate,
                            "system": name,
                            "attribution": method,
                            "risk_targets": round(_risk(st), 4),
                            "auto_recall_targets": round(_auto_recall(st), 4),
                            "risk_change": round(_risk(st) - _risk(base_st), 4),
                            "risk_change_ci95": _ci(
                                [_risk(st[b]) - _risk(base_st[b]) for b in boots]
                            ),
                        }
                    )
    out: dict[str, Any] = {
        "targets": len(targets),
        "distinct_sources": len(sources),
        "attribution": attribution_rows,
        "seeds": {},
    }
    for seed in fitted:
        rows = table[str(seed)]
        dels = [
            r
            for r in rows
            if r["kind"] == "del"
            and r["system"] == "C1p_strong+knn_prov"
            and r["attribution"] == "containment"
        ]
        out["seeds"][str(seed)] = {
            "clean_risk_targets": {n: round(_risk(clean_stats[seed, n]), 4) for n in SYSTEMS},
            "table": rows,
            "H3_met": bool(all(r["risk_change_ci95"][1] <= cfg.INVARIANCE_MARGIN for r in dels)),
        }
    return out


def _summary(results: dict) -> dict:
    h3 = results["h3"]["final_test"]["seeds"]
    h4 = results["h4"]["seeds"]
    n = str(1000)
    a = str(cfg.ALPHA)
    h4_met = {
        s: h4[s]["C1_strong+knn"][a]["audit"][n]["violation_share"] <= cfg.H4_MAX_VIOLATION_SHARE
        for s in h4
    }
    return {
        "H3_containment_closes_deletion_gap": (
            f"{sum(r['H3_met'] for r in h3.values())} of {len(h3)}"
        ),
        "H4_recertification_N1000": f"{sum(h4_met.values())} of {len(h4_met)}",
        "H4_violation_share_C1_N1000": {
            s: h4[s]["C1_strong+knn"][a]["audit"][n]["violation_share"] for s in h4
        },
        "check_rc_exact_C1": results["checks"],
    }


if __name__ == "__main__":
    t0 = time.perf_counter()
    run()
    print(f"{time.perf_counter() - t0:.0f}s")
