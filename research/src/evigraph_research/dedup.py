"""Exact, near-duplicate and template-duplicate groups.

* exact    - identical canonical text (sha256);
* near     - estimated Jaccard of word 5-gram shingles >= threshold;
* template - the same, after masking digits, so daily acts that differ only in numbers
             and dates fall into one group.

Exact groups are hard constraints for splitting. Near and template groups are diagnostics:
they measure how much of the evaluation data is a near copy of the training data, which is
the phenomenon the provenance hypothesis is about.

Shingles are taken from the first PREFIX_CHARS characters to keep the pass cheap.
"""

import concurrent.futures as cf
import os
import re
from typing import cast

import numpy as np
import pandas as pd
from datasketch import LeanMinHash, MinHash, MinHashLSH

from evigraph_research import paths

NUM_PERM = 128
SCHEME = "affine32"
SHINGLE = 5
PREFIX_CHARS = 20_000
_TOKEN = re.compile(r"\w+", re.UNICODE)
_DIGIT = re.compile(r"\d+")


def shingles(text: str, *, mask_digits: bool) -> set[bytes]:
    text = text[:PREFIX_CHARS].lower()
    if mask_digits:
        text = _DIGIT.sub("0", text)
    toks = _TOKEN.findall(text)
    if len(toks) < SHINGLE:
        return {" ".join(toks).encode()}
    return {" ".join(toks[i : i + SHINGLE]).encode() for i in range(len(toks) - SHINGLE + 1)}


def _signatures(texts: list[str], mask_digits: bool) -> np.ndarray:
    out = np.empty((len(texts), NUM_PERM), dtype=np.uint64)
    for i, t in enumerate(texts):
        m = MinHash(num_perm=NUM_PERM, seed=1, scheme=SCHEME)
        m.update_batch(list(shingles(t, mask_digits=mask_digits)))
        out[i] = m.hashvalues
    return out


def signatures(texts: list[str], *, mask_digits: bool) -> np.ndarray:
    n_workers = max(1, (os.cpu_count() or 2) - 1)
    chunk = max(1, len(texts) // (n_workers * 8))
    parts = [texts[i : i + chunk] for i in range(0, len(texts), chunk)]
    try:
        with cf.ProcessPoolExecutor(max_workers=n_workers) as pool:
            sigs = list(pool.map(_signatures, parts, [mask_digits] * len(parts)))
    except PermissionError:  # sandboxes that forbid process pools
        sigs = [_signatures(p, mask_digits) for p in parts]
    return np.vstack(sigs)


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def labels(self) -> list[int]:
        return [self.find(i) for i in range(len(self.parent))]


def near_groups(sigs: np.ndarray, threshold: float) -> list[int]:
    lsh = MinHashLSH(threshold=threshold, num_perm=NUM_PERM)
    mins = [LeanMinHash(seed=1, hashvalues=row, scheme=SCHEME) for row in sigs]
    for i, m in enumerate(mins):
        lsh.insert(i, m)
    uf = UnionFind(len(mins))
    for i, m in enumerate(mins):
        for key in lsh.query(m):
            j = cast("int", key)  # keys are the ints inserted above
            if j > i and m.jaccard(mins[j]) >= threshold:
                uf.union(i, j)
    return uf.labels()


def run(*, threshold: float = 0.9) -> pd.DataFrame:
    corpus = pd.read_parquet(paths.CORPUS, columns=["celex_id", "text", "text_sha256"])
    texts = corpus["text"].tolist()

    exact_codes = corpus.groupby("text_sha256").ngroup()
    out = pd.DataFrame({"celex_id": corpus["celex_id"], "exact_group": exact_codes})
    for name, mask in (("near_group", False), ("template_group", True)):
        sigs = signatures(texts, mask_digits=mask)
        roots = near_groups(sigs, threshold)
        out[name] = pd.Series(roots).map(corpus["celex_id"]).to_numpy()
    out["exact_group"] = out.groupby("exact_group")["celex_id"].transform("min")
    out.to_parquet(paths.DUPLICATES, index=False)

    for col in ("exact_group", "near_group", "template_group"):
        sizes = out.groupby(col).size()
        in_multi = int(sizes[sizes > 1].sum())
        print(f"{col}: {int((sizes > 1).sum())} groups of size>1 covering {in_multi} docs")
    return out
