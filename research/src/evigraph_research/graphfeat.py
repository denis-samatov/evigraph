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


def build(
    celex_ids: list[str],
    is_train: np.ndarray,
    y: np.ndarray,
    edges: pd.DataFrame,
    *,
    hub_cap: int = HUB_CAP,
) -> GraphFeatures:
    n = len(celex_ids)
    idx = {c: i for i, c in enumerate(celex_ids)}
    y_train = sp.csr_matrix(np.where(is_train[:, None], y, False).astype(np.float32))

    votes, degree = {}, {}
    inner = edges[edges["dst_in_corpus"]].copy()
    inner["bucket"] = inner["family"].map(_family_bucket)
    for bucket in (*FAMILIES, "other"):
        e = inner[inner["bucket"] == bucket]
        r = e["src"].map(idx).to_numpy()
        c = e["dst"].map(idx).to_numpy()
        a = sp.coo_matrix((np.ones(len(e), np.float32), (r, c)), shape=(n, n)).tocsr()
        a = ((a + a.T) > 0).astype(np.float32)
        a.setdiag(0)
        a.eliminate_zeros()
        votes[bucket], degree[bucket] = _vote(a, y_train)

    ext = edges[~edges["dst_in_corpus"]][["src", "dst"]].drop_duplicates()
    hub_size = ext.groupby("dst")["src"].transform("size")
    ext = ext[(hub_size >= 2) & (hub_size <= hub_cap)]
    hubs = {h: j for j, h in enumerate(ext["dst"].unique())}
    b = sp.coo_matrix(
        (
            np.ones(len(ext), np.float32),
            (ext["src"].map(idx).to_numpy(), ext["dst"].map(hubs).to_numpy()),
        ),
        shape=(n, len(hubs)),
    ).tocsr()
    a_hub = ((b @ b.T) > 0).astype(np.float32)
    a_hub.setdiag(0)
    a_hub.eliminate_zeros()
    votes["hub"], degree["hub"] = _vote(a_hub, y_train)

    return GraphFeatures(names=list(votes), votes=votes, degree=degree)
