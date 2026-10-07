"""Five-way split manifest built on top of the official MultiEURLEX splits.

    official train -> train       (older)       model fitting
                   -> model_dev   (most recent)  architecture / feature / hyper-parameter choice
    official dev   -> calib_fit                  calibrator fitting
                   -> risk_cert                  policy certification
    official test  -> final_test                 frozen-system evaluation only

Split groups (never divided between the derived splits) are connected components of
exact duplicates, near duplicates and in-corpus `corrects` relations. The official boundaries
are kept as published; near copies that cross them are flagged, not moved, because recurring
templated acts are part of the real distribution. Evaluation reports results with and without
flagged documents.
"""

import hashlib

import orjson
import pandas as pd

from evigraph_research import paths
from evigraph_research.dedup import UnionFind


def _split_groups(corpus: pd.DataFrame, dups: pd.DataFrame) -> pd.Series:
    idx = {c: i for i, c in enumerate(corpus["celex_id"])}
    uf = UnionFind(len(idx))
    for col in ("exact_group", "near_group"):
        for celex, root in zip(dups["celex_id"], dups[col], strict=True):
            uf.union(idx[celex], idx[root])
    if paths.CELLAR_EDGES.exists():
        edges = pd.read_parquet(paths.CELLAR_EDGES)
        corr = edges[(edges["family"] == "corrects") & edges["dst_in_corpus"]]
        for s, d in zip(corr["src"], corr["dst"], strict=True):
            uf.union(idx[s], idx[d])
    roots = uf.labels()
    return pd.Series([corpus["celex_id"].iloc[r] for r in roots], index=corpus.index)


def _bucket(group: str, seed: int) -> float:
    h = hashlib.sha256(f"{seed}:{group}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def build(*, model_dev_size: int = 5000, seed: int = 20261007) -> pd.DataFrame:
    corpus = pd.read_parquet(
        paths.CORPUS, columns=["celex_id", "publication_date", "official_split"]
    )
    dups = pd.read_parquet(paths.DUPLICATES).set_index("celex_id").loc[corpus["celex_id"]]
    dups = dups.reset_index()
    corpus["split_group"] = _split_groups(corpus, dups)

    split = pd.Series(index=corpus.index, dtype="object")
    split[corpus["official_split"] == "test"] = "final_test"

    dev = corpus["official_split"] == "dev"
    split[dev] = [
        "calib_fit" if _bucket(g, seed) < 0.5 else "risk_cert"
        for g in corpus.loc[dev, "split_group"]
    ]

    # model_dev = the most recent official-train groups; a group goes to model_dev only if
    # all of its official-train members are after the cutoff, so train never holds a copy.
    tr = corpus[corpus["official_split"] == "train"]
    cutoff = tr["publication_date"].sort_values().iloc[-model_dev_size]
    first_seen = tr.groupby("split_group")["publication_date"].min()
    late_groups = set(first_seen[first_seen >= cutoff].index)
    split[tr.index] = ["model_dev" if g in late_groups else "train" for g in tr["split_group"]]
    # Members of early groups published after the cutoff would put labelled documents
    # concurrent with model_dev into train; they are excluded to keep train strictly older.
    overlap = tr.index[(split[tr.index] == "train") & (tr["publication_date"] >= cutoff)]
    split[overlap] = "excluded_overlap"
    corpus["split"] = split

    # Diagnostics: does an evaluation document have a near/template copy among labelled train docs?
    train_ids = set(corpus.loc[corpus["split"] == "train", "celex_id"])
    for col in ("exact_group", "near_group", "template_group"):
        groups_with_train = set(dups.loc[dups["celex_id"].isin(train_ids), col])
        corpus[f"{col.removesuffix('_group')}_copy_in_train"] = (
            dups[col].isin(groups_with_train).to_numpy() & (corpus["split"] != "train").to_numpy()
        )

    # Group integrity across derived splits (official boundaries are allowed to be crossed).
    derived = corpus[corpus["split"].isin(["calib_fit", "risk_cert"])]
    leaks = derived.groupby("split_group")["split"].nunique()
    if (leaks > 1).any():
        msg = "calib_fit / risk_cert share a split group"
        raise AssertionError(msg)

    corpus.to_parquet(paths.SPLITS, index=False)
    digest = hashlib.sha256(
        corpus[["celex_id", "split", "split_group"]].to_csv(index=False).encode()
    ).hexdigest()
    summary = {
        "seed": seed,
        "model_dev_size_target": model_dev_size,
        "model_dev_cutoff": str(cutoff.date()),
        "manifest_sha256": digest,
        "counts": corpus["split"].value_counts().to_dict(),
        "date_ranges": {
            s: [str(g["publication_date"].min().date()), str(g["publication_date"].max().date())]
            for s, g in corpus.groupby("split")
        },
        "copy_in_train_rate": {
            s: {
                k: round(float(g[f"{k}_copy_in_train"].mean()), 4)
                for k in ("exact", "near", "template")
            }
            for s, g in corpus.groupby("split")
            if s != "train"
        },
    }
    (paths.REPORTS / "split_manifest.json").write_bytes(
        orjson.dumps(summary, option=orjson.OPT_INDENT_2)
    )
    print(orjson.dumps(summary, option=orjson.OPT_INDENT_2).decode())
    return corpus
