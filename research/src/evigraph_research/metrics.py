"""Ranking, classification, calibration and automation metrics.

Conventions: `y` is a boolean (n_docs, n_labels) gold matrix, `scores` a float matrix of the
same shape, `auto` a boolean matrix of automatically applied assignments.
"""

import math

import numpy as np


def r_precision(y: np.ndarray, scores: np.ndarray) -> float:
    """Mean R-Precision over documents with at least one gold label (MultiEURLEX's mRP)."""
    vals = []
    order = np.argsort(-scores, axis=1, kind="stable")
    for i in range(y.shape[0]):
        r = int(y[i].sum())
        if r == 0:
            continue
        vals.append(y[i, order[i, :r]].sum() / r)
    return float(np.mean(vals)) if vals else math.nan


def recall_at_k(y: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Share of all gold assignments that are among the top-k candidates of their document."""
    topk = np.argsort(-scores, axis=1, kind="stable")[:, :k]
    hit = np.take_along_axis(y, topk, axis=1).sum()
    total = y.sum()
    return float(hit / total) if total else math.nan


def f1_scores(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    tp = (y & pred).sum(axis=0).astype(float)
    fp = (~y & pred).sum(axis=0).astype(float)
    fn = (y & ~pred).sum(axis=0).astype(float)
    micro = 2 * tp.sum() / max(2 * tp.sum() + fp.sum() + fn.sum(), 1.0)
    denom = 2 * tp + fp + fn
    per_label = np.divide(2 * tp, denom, out=np.zeros_like(tp), where=denom > 0)
    present = y.sum(axis=0) > 0
    return {"micro_f1": float(micro), "macro_f1": float(per_label[present].mean())}


def automation(y: np.ndarray, auto: np.ndarray) -> dict[str, float]:
    """Risk and coverage of automatically applied assignments.

    risk is undefined (nan) when nothing is applied; auto_recall is then 0. A system that
    applies nothing is not a zero-error system.
    """
    n_auto = int(auto.sum())
    errors = int((auto & ~y).sum())
    correct = n_auto - errors
    gold = int(y.sum())
    fully = np.all(auto == y, axis=1) & (y.sum(axis=1) > 0)
    return {
        "n_auto": n_auto,
        "n_errors": errors,
        "risk": errors / n_auto if n_auto else math.nan,
        "auto_recall": correct / gold if gold else math.nan,
        "auto_per_doc": n_auto / y.shape[0],
        "docs_fully_auto_correct": float(fully.mean()),
    }


def expected_calibration_error_topk(
    prob: np.ndarray, y: np.ndarray, k: int, bins: int = 15
) -> float:
    """ECE over each document's top-k pairs, where decisions actually happen.

    Over all pairs the metric is dominated by easy negatives and looks deceptively small.
    """
    topk = np.argsort(-prob, axis=1, kind="stable")[:, :k]
    return expected_calibration_error(
        np.take_along_axis(prob, topk, axis=1), np.take_along_axis(y, topk, axis=1), bins
    )


def expected_calibration_error(prob: np.ndarray, y: np.ndarray, bins: int = 15) -> float:
    prob, y = prob.ravel(), y.ravel().astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(prob, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            ece += m.mean() * abs(prob[m].mean() - y[m].mean())
    return float(ece)
