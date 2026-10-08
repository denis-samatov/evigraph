"""Risk certification of a threshold policy ("auto-apply if score >= tau").

The score is the raw stacker output; calibrated scores are used only for display and ECE.

Learn-then-Test with fixed-sequence testing (Angelopoulos et al., 2021): the candidate
thresholds and their order are fixed *before* looking at the certification data (here: from
the calibration split), then tested from strictest to most permissive. For each tau the null
hypothesis "risk(tau) > alpha" is rejected when the one-sided Clopper-Pearson upper bound
on the error rate among applied assignments is <= alpha. Testing stops at the first
non-rejection; the most permissive rejected tau is certified. Family-wise error <= delta.

Assumption that the bound relies on: applied assignments are exchangeable/independent.
Assignments of one document are correlated, so `cluster_bootstrap_risk` is reported next to it
as a sanity check. A document-level bound is a follow-up item in the protocol.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import beta


def clopper_pearson_upper(k: int, n: int, delta: float) -> float:
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    return float(beta.ppf(1 - delta, k + 1, n - k))


def candidate_thresholds(
    calib_scores: np.ndarray, *, min_applied: int, ratio: float = 1.1
) -> np.ndarray:
    """Descending thresholds from calibration data only.

    The k-th threshold applies about min_applied * ratio**k calibration pairs, so the grid is
    fine where few pairs are applied. Quantiles over all pairs would be far too coarse there,
    because almost all pairs are easy negatives.
    """
    s = np.sort(calib_scores.ravel())[::-1]
    if s.size < min_applied:
        return np.array([])
    counts, c = [], float(min_applied)
    while c <= s.size:
        counts.append(round(c))
        c *= ratio
    grid = s[np.unique(counts) - 1]
    return np.unique(grid)[::-1]


@dataclass
class Certification:
    alpha: float
    delta: float
    tau: float | None
    tested: list[dict] = field(default_factory=list)


def certify(
    scores: np.ndarray, y: np.ndarray, thresholds: np.ndarray, *, alpha: float, delta: float
) -> Certification:
    s, yy = scores.ravel(), y.ravel().astype(bool)
    cert = Certification(alpha=alpha, delta=delta, tau=None)
    for tau in thresholds:
        applied = s >= tau
        n = int(applied.sum())
        k = int((applied & ~yy).sum())
        ucb = clopper_pearson_upper(k, n, delta)
        cert.tested.append({"tau": float(tau), "n": n, "errors": k, "ucb": ucb})
        if ucb > alpha:
            break
        cert.tau = float(tau)
    return cert


def cluster_bootstrap_risk(
    auto: np.ndarray, y: np.ndarray, *, n_boot: int = 1000, seed: int = 0, level: float = 0.9
) -> tuple[float, float]:
    """Percentile CI of the applied-error rate, resampling documents."""
    rng = np.random.default_rng(seed)
    applied = auto.sum(axis=1)
    errors = (auto & ~y).sum(axis=1)
    n = auto.shape[0]
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        a = applied[idx].sum()
        if a:
            stats.append(errors[idx].sum() / a)
    if not stats:
        return (float("nan"), float("nan"))
    lo, hi = np.quantile(stats, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)
