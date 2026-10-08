"""Provenance-aware aggregation: a provenance group is one source, however many copies it has.

Naive label propagation counts every pool document as an independent vote, so m copies of
one source get m votes. Here votes are cast by provenance groups:

* kNN: retrieve `candidates` nearest pool documents, collapse them to groups (group similarity
  = max over its retrieved members, group labels = mean labels of all its pool members) and
  vote with the top-k groups;
* graph: a document's neighbours are collapsed to the groups they belong to; each group
  contributes its mean label vector once.

Exact copies that join their source's group leave both votes unchanged (tests check this).
"""

import numpy as np
import scipy.sparse as sp

from evigraph_research import graphfeat

CHUNK = 512


def group_index(groups: np.ndarray) -> tuple[np.ndarray, int]:
    """Map arbitrary group labels to 0..n_groups-1."""
    _, codes = np.unique(groups, return_inverse=True)
    return codes.astype(np.int64), int(codes.max()) + 1 if len(codes) else 0


def group_label_means(codes: np.ndarray, n_groups: int, y: np.ndarray) -> np.ndarray:
    m = sp.csr_matrix(
        (np.ones(len(codes), np.float32), (codes, np.arange(len(codes)))), (n_groups, len(codes))
    )
    sizes = np.asarray(m.sum(axis=1)).ravel()
    return (m @ y.astype(np.float32)) / np.maximum(sizes, 1)[:, None]


def knn_scores(
    x_query: sp.csr_matrix,
    x_pool: sp.csr_matrix,
    y_pool: np.ndarray,
    *,
    k: int,
    groups: np.ndarray | None = None,
    candidates: int = 200,
    adaptive: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """kNN label vote, max similarity and top-1 pool index for each query row.

    With `groups=None` every pool document votes (naive). Otherwise votes are cast by the
    top-k provenance groups among the `candidates` nearest documents.
    """
    naive, prov, top, top1 = knn_both(
        x_query, x_pool, y_pool, k=k, groups=groups, candidates=candidates, adaptive=adaptive
    )
    return (naive if prov is None else prov), top, top1


def knn_both(
    x_query: sp.csr_matrix,
    x_pool: sp.csr_matrix,
    y_pool: np.ndarray,
    *,
    k: int,
    groups: np.ndarray | None,
    candidates: int = 200,
    adaptive: bool = False,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]:
    """Naive and (if `groups` is given) provenance-aware votes from one similarity pass.

    With `adaptive`, a row whose candidate window holds fewer than k distinct groups widens
    the window (x4) until it does or covers the whole pool; otherwise copies of a few nearby
    sources can crowd every other group out of a fixed window.
    """
    xt = x_pool.T.tocsr()
    n_q, n_lab = x_query.shape[0], y_pool.shape[1]
    naive = np.zeros((n_q, n_lab), dtype=np.float32)
    prov = np.zeros((n_q, n_lab), dtype=np.float32) if groups is not None else None
    top = np.zeros(n_q, dtype=np.float32)
    top1 = np.zeros(n_q, dtype=np.int64)
    yp = y_pool.astype(np.float32)
    if groups is not None:
        codes, n_groups = group_index(groups)
        gmean = group_label_means(codes, n_groups, y_pool)
    for lo in range(0, n_q, CHUNK):
        sim = (x_query[lo : lo + CHUNK] @ xt).toarray()
        top1[lo : lo + CHUNK] = sim.argmax(axis=1)
        top[lo : lo + CHUNK] = sim.max(axis=1)
        nn = np.argpartition(-sim, k, axis=1)[:, :k]
        w = np.take_along_axis(sim, nn, axis=1)
        naive[lo : lo + CHUNK] = np.einsum("ik,ikl->il", w, yp[nn]) / np.maximum(
            w.sum(axis=1, keepdims=True), 1e-9
        )
        if prov is None:
            continue
        c = min(candidates, sim.shape[1] - 1)
        cand = np.argpartition(-sim, c, axis=1)[:, :c]
        for r in range(sim.shape[0]):
            idx = cand[r]
            width = c
            while True:
                s = sim[r, idx]
                order = np.argsort(-s, kind="stable")
                g_sorted, s_sorted = codes[idx][order], s[order]
                _, first = np.unique(g_sorted, return_index=True)  # best member of each group
                if not adaptive or len(first) >= k or width >= sim.shape[1] - 1:
                    break
                width = min(width * 4, sim.shape[1] - 1)
                idx = np.argpartition(-sim[r], width)[:width]
            first.sort()
            best = first[:k]
            wg = s_sorted[best]
            prov[lo + r] = (wg @ gmean[g_sorted[best]]) / max(wg.sum(), 1e-9)
    return naive, prov, top, top1


def graph_features(
    celex_ids: list[str],
    is_pool: np.ndarray,
    y: np.ndarray,
    edges,
    *,
    groups: np.ndarray | None = None,
    hub_cap: int = graphfeat.HUB_CAP,
) -> graphfeat.GraphFeatures:
    """Graph votes per relation bucket; with `groups`, each provenance group is one neighbour."""
    if groups is None:
        return graphfeat.build(celex_ids, is_pool, y, edges, hub_cap=hub_cap)
    codes, n_groups = group_index(groups)
    n = len(celex_ids)
    pool_codes = codes[is_pool]
    pool_rows = np.flatnonzero(is_pool)
    membership = sp.csr_matrix(
        (np.ones(len(pool_rows), np.float32), (pool_rows, pool_codes)), (n, n_groups)
    )
    gmean = group_label_means(pool_codes, n_groups, y[is_pool])
    has_pool = np.zeros(n_groups, dtype=np.float32)
    has_pool[pool_codes] = 1.0
    votes, degree = {}, {}
    adj = graphfeat.adjacencies(celex_ids, edges, hub_cap=hub_cap, hub_groups=groups)
    for name, a in adj.items():
        a_g = ((a @ membership) > 0).astype(np.float32)
        deg = a_g @ has_pool
        summed = a_g @ gmean
        with np.errstate(invalid="ignore", divide="ignore"):
            votes[name] = np.where(deg[:, None] > 0, summed / deg[:, None], 0.0).astype(np.float32)
        degree[name] = deg
    return graphfeat.GraphFeatures(names=list(votes), votes=votes, degree=degree)
