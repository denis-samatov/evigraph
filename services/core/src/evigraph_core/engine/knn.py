"""Provenance-aware kNN label vote (see research/src/evigraph_research/provenance.py).

A provenance group is one source: candidates are collapsed to groups (group similarity = max
over its members, group labels = mean over its members) and the top-k groups vote. The
candidate window widens until it holds k distinct groups, so copies of a few sources cannot
crowd the others out. Exact copies that join their source's group change nothing.
"""

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp


@dataclass
class Neighbour:
    pool_index: int
    group: int
    similarity: float


def group_means(codes: np.ndarray, n_groups: int, y: np.ndarray) -> np.ndarray:
    m = sp.csr_matrix(
        (np.ones(len(codes), np.float32), (codes, np.arange(len(codes)))), (n_groups, len(codes))
    )
    sizes = np.asarray(m.sum(axis=1)).ravel()
    return np.asarray(m @ y.astype(np.float32)) / np.maximum(sizes, 1)[:, None]


def vote(
    x_query: sp.csr_matrix,
    x_pool: sp.csr_matrix,
    y_pool: np.ndarray,
    codes: np.ndarray,
    *,
    k: int,
    candidates: int,
    exclude: list[int | None] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[list[Neighbour]]]:
    """Votes (n_query, n_labels), top similarity (n_query,) and the voting groups per query.

    `exclude[i]` is a pool index to ignore for query i (the query document itself).
    """
    n_q, n_lab = x_query.shape[0], y_pool.shape[1]
    votes = np.zeros((n_q, n_lab), dtype=np.float32)
    top = np.zeros(n_q, dtype=np.float32)
    voters: list[list[Neighbour]] = []
    if x_pool.shape[0] == 0:
        return votes, top, [[] for _ in range(n_q)]
    n_groups = int(codes.max()) + 1
    gmean = group_means(codes, n_groups, y_pool)
    sim_all = (x_query @ x_pool.T).toarray()
    for r in range(n_q):
        sim = sim_all[r]
        if exclude is not None and exclude[r] is not None:
            sim = sim.copy()
            sim[exclude[r]] = -np.inf
        width = min(candidates, len(sim))
        while True:
            idx = (
                np.argpartition(-sim, width - 1)[:width]
                if width < len(sim)
                else np.arange(len(sim))
            )
            idx = idx[np.isfinite(sim[idx])]
            order = idx[np.argsort(-sim[idx], kind="stable")]
            _, first = np.unique(codes[order], return_index=True)
            if len(first) >= k or width >= len(sim):
                break
            width = min(width * 4, len(sim))
        best = order[np.sort(first)[:k]]
        w = np.clip(sim[best], 0, None)
        if w.sum() > 0:
            votes[r] = (w @ gmean[codes[best]]) / w.sum()
        top[r] = float(sim[best].max()) if len(best) else 0.0
        voters.append([Neighbour(int(i), int(codes[i]), float(sim[i])) for i in best])
    return votes, top, voters
