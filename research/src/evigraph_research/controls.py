"""Text controls that see the same materials as the graph system, minus the graph itself.

C1 `knn`    - label vote of the KNN_K most similar train documents by TF-IDF cosine: label
              propagation through retrieval instead of through EUR-Lex relations.
C2 `nbtext` - a text model whose input is [x_doc ; mean x over reference neighbours]: the
              neighbours' *text* without their labels or relation types. The neighbour set is
              exactly the one the graph features use (graphfeat.reference_neighbours).
"""

import time
from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp

from evigraph_research import paths, textmodel

CHUNK = 512


def knn_votes(
    tr_path: Path, ev_path: Path, y_train: np.ndarray, *, k: int
) -> tuple[np.ndarray, np.ndarray]:
    """(votes (n_eval, n_labels), max cosine (n_eval,)). Rows of x are L2-normalised."""
    x_train = joblib.load(tr_path, mmap_mode="r")
    x_eval = joblib.load(ev_path, mmap_mode="r")
    xt = x_train.T.tocsr()
    yt = y_train.astype(np.float32)
    votes = np.zeros((x_eval.shape[0], y_train.shape[1]), dtype=np.float32)
    top = np.zeros(x_eval.shape[0], dtype=np.float32)
    started = time.perf_counter()
    for lo in range(0, x_eval.shape[0], CHUNK):
        sim = (x_eval[lo : lo + CHUNK] @ xt).toarray()
        nn = np.argpartition(-sim, k, axis=1)[:, :k]
        w = np.take_along_axis(sim, nn, axis=1)
        votes[lo : lo + CHUNK] = np.einsum("ik,ikl->il", w, yt[nn]) / np.maximum(
            w.sum(axis=1, keepdims=True), 1e-9
        )
        top[lo : lo + CHUNK] = w.max(axis=1)
    print(f"  knn: {x_eval.shape[0]} docs in {time.perf_counter() - started:.0f}s", flush=True)
    return votes, top


def _neighbour_text(nb: sp.csr_matrix, x_train: sp.csr_matrix, top_terms: int) -> sp.csr_matrix:
    """Mean neighbour TF-IDF per row, truncated to its top terms and L2-normalised.

    Averaging over dozens of neighbours makes rows nearly dense (8 GB for train); truncation
    keeps the matrix the size of the plain TF-IDF one. Computed in row chunks.
    """
    parts = []
    for lo in range(0, nb.shape[0], 256):
        m = (nb[lo : lo + 256] @ x_train).tocsr()
        rows, cols, vals = [], [], []
        for i in range(m.shape[0]):
            a, b = m.indptr[i], m.indptr[i + 1]
            v, c = m.data[a:b], m.indices[a:b]
            if len(v) > top_terms:
                keep = np.argpartition(-v, top_terms)[:top_terms]
                v, c = v[keep], c[keep]
            norm = np.sqrt((v * v).sum())
            if norm > 0:
                rows.append(np.full(len(v), i))
                cols.append(c)
                vals.append(v / norm)
        if rows:
            r, c, v = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
        else:
            r = c = np.array([], dtype=np.int64)
            v = np.array([], dtype=np.float32)
        parts.append(sp.csr_matrix((v.astype(np.float32), (r, c)), shape=m.shape))
    return sp.vstack(parts, format="csr")


def nbtext_matrices(
    tr_path: Path,
    ev_path: Path,
    nb_train: sp.csr_matrix,
    nb_eval: sp.csr_matrix,
    *,
    cache_key: str,
    top_terms: int,
) -> tuple[Path, Path]:
    """Cache [x ; neighbour text] for train and eval rows.

    nb_train: (n_train, n_train) row-normalised neighbour matrix among train rows.
    nb_eval:  (n_eval, n_train) row-normalised neighbour matrix from eval rows to train rows.
    """
    out_dir = paths.CACHE / "nbtext" / f"{cache_key}_top{top_terms}"
    tr_out, ev_out = out_dir / "x_train.joblib", out_dir / "x_eval.joblib"
    if tr_out.exists() and ev_out.exists():
        return tr_out, ev_out
    out_dir.mkdir(parents=True, exist_ok=True)
    x_train = joblib.load(tr_path)
    x_eval = joblib.load(ev_path)
    started = time.perf_counter()
    nbx_train = _neighbour_text(nb_train, x_train, top_terms)
    nbx_eval = _neighbour_text(nb_eval, x_train, top_terms)
    print(f"  nbtext matrices in {time.perf_counter() - started:.0f}s", flush=True)
    joblib.dump(sp.hstack([x_train, nbx_train], format="csr", dtype=np.float32), tr_out)
    joblib.dump(sp.hstack([x_eval, nbx_eval], format="csr", dtype=np.float32), ev_out)
    return tr_out, ev_out


def nbtext_predict(tr_path: Path, ev_path: Path, y_train: np.ndarray, *, n_jobs: int) -> np.ndarray:
    return textmodel.fit_predict(tr_path, ev_path, y_train, n_jobs=n_jobs)
