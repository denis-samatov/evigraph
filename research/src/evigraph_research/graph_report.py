"""Go/no-go report for the graph hypotheses on MultiEURLEX + EUR-Lex relations.

Questions answered:
1. How many relations exist, by family, and how many stay inside the corpus?
2. Coverage: what share of each split has at least one *train* neighbour (the only labels the
   reference graph may use), directly or through a shared external act?
3. Homophily: do linked train documents share level-2 labels more than random pairs?
4. Signal: how good is a neighbour label vote alone, compared with the label prior?
"""

import numpy as np
import orjson
import pandas as pd

from evigraph_research import dataset, graphfeat, metrics, paths

# Preliminary decision rule, fixed before the numbers were seen.
GO_COVERAGE = 0.5  # share of model_dev docs with >= 1 train neighbour (direct or hub)
GO_MRP_GAIN = 0.10  # neighbour vote mRP minus prior mRP on covered model_dev docs


def _homophily(ds: dataset.Dataset, edges: pd.DataFrame, rng: np.random.Generator) -> dict:
    idx = {c: i for i, c in enumerate(ds.frame["celex_id"])}
    train = ds.mask("train")
    y = ds.y

    def jaccard(a: np.ndarray, b: np.ndarray) -> float:
        inter = (y[a] & y[b]).sum(axis=1)
        union = (y[a] | y[b]).sum(axis=1)
        return float(np.mean(np.divide(inter, union, out=np.zeros(len(a)), where=union > 0)))

    tr_idx = np.flatnonzero(train)
    ra, rb = rng.choice(tr_idx, 200_000), rng.choice(tr_idx, 200_000)
    out = {"random_pairs": round(jaccard(ra, rb), 4)}
    inner = edges[edges["dst_in_corpus"]].copy()
    inner["bucket"] = inner["family"].map(graphfeat._family_bucket)
    for bucket, e in inner.groupby("bucket"):
        a = e["src"].map(idx).to_numpy()
        b = e["dst"].map(idx).to_numpy()
        keep = train[a] & train[b]
        if keep.sum() >= 100:
            out[bucket] = round(jaccard(a[keep], b[keep]), 4)
    return out


def run() -> dict:
    ds = dataset.load()
    edges = pd.read_parquet(paths.CELLAR_EDGES)
    edges = edges[edges["src"].isin(set(ds.frame["celex_id"]))]
    rng = np.random.default_rng(0)

    report: dict = {}
    fam = edges.groupby("family").agg(edges=("dst", "size"), in_corpus=("dst_in_corpus", "mean"))
    report["edges_by_family"] = {
        f: {"edges": int(r.edges), "share_in_corpus": round(float(r.in_corpus), 4)}
        for f, r in fam.sort_values("edges", ascending=False).iterrows()
    }
    report["docs_with_any_outgoing_edge"] = round(
        float(ds.frame["celex_id"].isin(set(edges["src"])).mean()), 4
    )

    is_train = ds.mask("train")
    gf = graphfeat.build(ds.frame["celex_id"].tolist(), is_train, ds.y, edges)
    direct = np.zeros(len(ds.frame))
    for b in (*graphfeat.FAMILIES, "other"):
        direct += gf.degree[b]
    any_nb = (direct > 0) | (gf.degree["hub"] > 0)

    coverage = {}
    for split in dataset.SPLIT_ORDER:
        m = ds.mask(split)
        coverage[split] = {
            **{b: round(float((gf.degree[b][m] > 0).mean()), 4) for b in gf.names},
            "any_direct": round(float((direct[m] > 0).mean()), 4),
            "direct_or_hub": round(float(any_nb[m].mean()), 4),
        }
    report["coverage_train_neighbour"] = coverage
    report["label_jaccard"] = _homophily(ds, edges, rng)

    # Neighbour vote vs prior: direct vote where available, then hub vote, then prior.
    prior = ds.y[is_train].mean(axis=0).astype(np.float32)
    direct_vote = sum(gf.votes[b] * gf.degree[b][:, None] for b in (*graphfeat.FAMILIES, "other"))
    with np.errstate(invalid="ignore", divide="ignore"):
        direct_vote = np.where(direct[:, None] > 0, direct_vote / direct[:, None], 0.0)
    vote = np.where((direct > 0)[:, None], direct_vote, gf.votes["hub"])
    vote = vote + 1e-3 * prior  # break ties by prior
    signal = {}
    for split in ("model_dev", "risk_cert"):
        m = ds.mask(split) & any_nb
        signal[split] = {
            "covered_docs": int(m.sum()),
            "prior_mrp": round(metrics.r_precision(ds.y[m], np.tile(prior, (m.sum(), 1))), 4),
            "vote_mrp": round(metrics.r_precision(ds.y[m], vote[m]), 4),
        }
    report["neighbour_vote_signal"] = signal

    cov = coverage["model_dev"]["direct_or_hub"]
    gain = signal["model_dev"]["vote_mrp"] - signal["model_dev"]["prior_mrp"]
    report["decision"] = {
        "rule": f"GO if coverage >= {GO_COVERAGE} and vote mRP - prior mRP >= {GO_MRP_GAIN}",
        "coverage": cov,
        "mrp_gain": round(gain, 4),
        "go": bool(cov >= GO_COVERAGE and gain >= GO_MRP_GAIN),
    }

    (paths.REPORTS / "graph_report.json").write_bytes(
        orjson.dumps(report, option=orjson.OPT_INDENT_2)
    )
    print(orjson.dumps(report, option=orjson.OPT_INDENT_2).decode())
    return report
