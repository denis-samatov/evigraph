"""Text-only baseline: hashed TF-IDF (uni+bigrams) + one logistic model per label.

Design for a laptop:
* the TF-IDF matrices are cached on disk, keyed by their parameters and the split manifest;
* worker processes open the cached matrices as memory maps instead of receiving copies;
* each task fits one label with SGD (log loss) and returns only the probabilities on the
  evaluation rows, so no 127 x 2M weight matrix is ever held in memory;
* progress is printed per label.
"""

import hashlib
import time
from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.linear_model import SGDClassifier

from evigraph_research import paths

MAX_CHARS = 50_000  # ~1% of documents are longer; their tails are dropped
SGD_ALPHA = 5e-6  # ~ 1 / (C * n_train) for C = 4
SGD_EPOCHS = 15


def _vectorize_chunk(texts: list[str], n_features: int) -> sp.csr_matrix:
    hv = HashingVectorizer(
        n_features=n_features,
        ngram_range=(1, 2),
        alternate_sign=False,
        norm=None,
        dtype=np.float32,
    )
    return hv.transform(texts)


def counts(texts: list[str], *, n_features: int, n_jobs: int) -> sp.csr_matrix:
    """Raw uni+bigram hashed counts of the first MAX_CHARS characters, in parallel."""
    texts = [t[:MAX_CHARS] for t in texts]
    step = max(1, len(texts) // (n_jobs * 4))
    parts = joblib.Parallel(n_jobs=n_jobs)(
        joblib.delayed(_vectorize_chunk)(texts[i : i + step], n_features)
        for i in range(0, len(texts), step)
    )
    return sp.vstack(parts).tocsr()


def _cache_dir(cache_key: str, n_features: int) -> Path:
    key = hashlib.sha256(f"{cache_key}:{n_features}:{MAX_CHARS}".encode()).hexdigest()[:16]
    return paths.CACHE / "tfidf" / key


def tfidf(
    train_texts: list[str],
    eval_texts: list[str],
    *,
    n_features: int,
    cache_key: str,
    n_jobs: int,
) -> tuple[Path, Path]:
    """Return paths of cached (x_train, x_eval) CSR matrices, building them if needed."""
    out_dir = _cache_dir(cache_key, n_features)
    tr_path, ev_path = out_dir / "x_train.joblib", out_dir / "x_eval.joblib"
    if tr_path.exists() and ev_path.exists():
        return tr_path, ev_path
    out_dir.mkdir(parents=True, exist_ok=True)
    tf = TfidfTransformer(sublinear_tf=True)
    x_train = tf.fit_transform(counts(train_texts, n_features=n_features, n_jobs=n_jobs))
    x_eval = tf.transform(counts(eval_texts, n_features=n_features, n_jobs=n_jobs))
    joblib.dump(x_train.astype(np.float32).tocsr(), tr_path)
    joblib.dump(x_eval.astype(np.float32).tocsr(), ev_path)
    joblib.dump(tf, out_dir / "transformer.joblib")
    return tr_path, ev_path


def transformer(
    train_texts: list[str], *, n_features: int, cache_key: str, n_jobs: int
) -> TfidfTransformer:
    """The IDF fitted on train, to vectorise new pool documents exactly like train ones."""
    path = _cache_dir(cache_key, n_features) / "transformer.joblib"
    if path.exists():
        return joblib.load(path)
    tf = TfidfTransformer(sublinear_tf=True).fit(
        counts(train_texts, n_features=n_features, n_jobs=n_jobs)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(tf, path)
    return tf


def _fit_label(
    tr_path: Path, ev_path: Path, y: np.ndarray, j: int
) -> tuple[int, np.ndarray, float]:
    t0 = time.perf_counter()
    x_train = joblib.load(tr_path, mmap_mode="r")
    x_eval = joblib.load(ev_path, mmap_mode="r")
    if y.min() == y.max():  # label absent (or always present) in train
        return j, np.full(x_eval.shape[0], float(y[0]), np.float32), time.perf_counter() - t0
    clf = SGDClassifier(
        loss="log_loss",
        alpha=SGD_ALPHA,
        max_iter=SGD_EPOCHS,
        tol=None,
        random_state=j,
    ).fit(x_train, y)
    p = clf.predict_proba(x_eval)[:, 1].astype(np.float32)
    return j, p, time.perf_counter() - t0


def fit_predict(tr_path: Path, ev_path: Path, y_train: np.ndarray, *, n_jobs: int) -> np.ndarray:
    """Probabilities (n_eval, n_labels) on the cached evaluation matrix."""
    n_eval = joblib.load(ev_path, mmap_mode="r").shape[0]
    n_lab = y_train.shape[1]
    out = np.zeros((n_eval, n_lab), dtype=np.float32)
    started = time.perf_counter()
    tasks = (
        joblib.delayed(_fit_label)(tr_path, ev_path, y_train[:, j].astype(np.int8), j)
        for j in range(n_lab)
    )
    gen = joblib.Parallel(n_jobs=n_jobs, return_as="generator_unordered")(tasks)
    for done, (j, p, secs) in enumerate(gen, 1):
        out[:, j] = p
        if done % 8 == 0 or done == n_lab:
            elapsed = time.perf_counter() - started
            eta = elapsed / done * (n_lab - done)
            print(
                f"  label {done}/{n_lab}  last fit {secs:.1f}s  "
                f"elapsed {elapsed:.0f}s  eta {eta:.0f}s",
                flush=True,
            )
    return out
