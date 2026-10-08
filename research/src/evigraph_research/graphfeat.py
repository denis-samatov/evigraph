"""Simple graph features over the EUR-Lex document graph.

Reference graph rule: only labels of documents in the `train` split may flow into features.
Features of a document never include its own labels.

* direct vote, per relation family: mean level-2 label vector of train documents linked to
  the document in either direction;
* hub vote: mean label vector of train documents that share an external (out-of-corpus) target
  with the document, e.g. the same base regulation. Hubs above `hub_cap` corpus documents are
  ignored (treaty articles and the like carry no topical signal).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp

FAMILIES = ("cites", "amends", "repeals", "based_on")
HUB_CAP = 500


@dataclass
class GraphFeatures:
    names: list[str]
    votes: dict[str, np.ndarray]  # name -> (n_docs, n_labels) float32
    degree: dict[str, np.ndarray]  # name -> (n_docs,) number of contributing train docs


def _family_bucket(family: str) -> str:
    return family if family in FAMILIES else "other"


def _vote(adj: sp.csr_matrix, y_train: sp.csr_matrix) -> tuple[np.ndarray, np.ndarray]:
    summed = (adj @ y_train).toarray().astype(np.float32)
    # number of linked train documents (train rows with at least one label)
    deg = adj @ (y_train.getnnz(axis=1) > 0).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        votes = np.where(deg[:, None] > 0, summed / deg[:, None], 0.0).astype(np.float32)
    return votes, deg


def _symmetric(a: sp.coo_matrix | sp.csr_matrix) -> sp.csr_matrix:
    a = ((a + a.transpose()) > 0).astype(np.float32).tocsr()
    a.setdiag(0)
    a.eliminate_zeros()
    return a


def adjacencies(
    celex_ids: list[str],
    edges: pd.DataFrame,
    *,
    hub_cap: int = HUB_CAP,
    hub_groups: np.ndarray | None = None,
) -> dict[str, sp.csr_matrix]:
    """Undirected document adjacency per relation bucket, plus `hub` (shared external act).

    The hub size compared with `hub_cap` counts documents, or provenance groups when
    `hub_groups` (one label per celex id) is given, so copies cannot push a hub over the cap.
    """
    n = len(celex_ids)
    idx = {c: i for i, c in enumerate(celex_ids)}
    edges = edges[edges["src"].isin(idx)]
    out = {}
    inner = edges[edges["dst_in_corpus"] & edges["dst"].isin(idx)].copy()
    inner["bucket"] = inner["family"].map(_family_bucket)
    for bucket in (*FAMILIES, "other"):
        e = inner[inner["bucket"] == bucket]
        r = e["src"].map(idx).to_numpy()
        c = e["dst"].map(idx).to_numpy()
        out[bucket] = _symmetric(sp.coo_matrix((np.ones(len(e), np.float32), (r, c)), (n, n)))

    ext = edges[~edges["dst_in_corpus"]][["src", "dst"]].drop_duplicates()
    if hub_groups is None:
        hub_size = ext.groupby("dst")["src"].transform("size")
    else:
        ext = ext.assign(group=np.asarray(hub_groups, dtype=object)[ext["src"].map(idx)])
        hub_size = ext.groupby("dst")["group"].transform("nunique")
    ext = ext[(hub_size >= 2) & (hub_size <= hub_cap)]
    hubs = {h: j for j, h in enumerate(ext["dst"].unique())}
    b = sp.coo_matrix(
        (
            np.ones(len(ext), np.float32),
            (ext["src"].map(idx).to_numpy(), ext["dst"].map(hubs).to_numpy()),
        ),
        shape=(n, len(hubs)),
    ).tocsr()
    out["hub"] = _symmetric(b @ b.T)
    return out


def build(
    celex_ids: list[str],
    is_train: np.ndarray,
    y: np.ndarray,
    edges: pd.DataFrame,
    *,
    hub_cap: int = HUB_CAP,
) -> GraphFeatures:
    y_train = sp.csr_matrix(np.where(is_train[:, None], y, False).astype(np.float32))
    votes, degree = {}, {}
    for name, a in adjacencies(celex_ids, edges, hub_cap=hub_cap).items():
        votes[name], degree[name] = _vote(a, y_train)
    return GraphFeatures(names=list(votes), votes=votes, degree=degree)


def reference_neighbours(
    celex_ids: list[str],
    dates: np.ndarray,
    is_train: np.ndarray,
    edges: pd.DataFrame,
    *,
    hub_cap: int = HUB_CAP,
) -> sp.csr_matrix:
    """Row-normalised matrix of the neighbours a document may draw on.

    Same neighbour set as the graph features: train documents linked directly (any relation)
    or through a shared external act, published strictly before the document.
    """
    adj = adjacencies(celex_ids, edges, hub_cap=hub_cap)
    total = sp.csr_matrix(next(iter(adj.values())).shape, dtype=np.float32)
    for m in adj.values():
        total = total + m
    a = total.tocoo()
    keep = is_train[a.col] & (dates[a.col] < dates[a.row])
    a = sp.coo_matrix(
        (np.ones(int(keep.sum()), np.float32), (a.row[keep], a.col[keep])), shape=a.shape
    ).tocsr()
    a.data[:] = 1.0  # duplicates from several relations count once
    deg = np.asarray(a.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros_like(deg), where=deg > 0)
    return (sp.diags(inv.astype(np.float32)) @ a).tocsr()
