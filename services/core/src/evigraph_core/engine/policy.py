"""Learn-then-Test certification of a threshold policy, and binomial bounds.

Same procedure as the research protocol (research/src/evigraph_research/policy.py): thresholds
form a geometric grid fixed on data independent of the certification set; they are tested from
the strictest to the most permissive with a one-sided Clopper-Pearson bound; testing stops at
the first non-rejection; the most permissive rejected threshold is certified. FWER <= delta.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import beta


def cp_upper(k: int, n: int, delta: float) -> float:
    if n == 0 or k >= n:
        return 1.0
    return float(beta.ppf(1 - delta, k + 1, n - k))


def cp_lower(k: int, n: int, delta: float) -> float:
    if n == 0 or k == 0:
        return 0.0
    return float(beta.ppf(delta, k, n - k + 1))


def thresholds(scores: np.ndarray, *, min_applied: int, ratio: float = 1.1) -> np.ndarray:
    s = np.sort(scores.ravel())[::-1]
    if s.size < min_applied:
        return np.array([])
    counts, c = [], float(min_applied)
    while c <= s.size:
        counts.append(round(c))
        c *= ratio
    return np.unique(s[np.unique(counts) - 1])[::-1]


@dataclass
class Certification:
    tau: float | None
    n_applied: int = 0
    n_errors: int = 0
    ucb: float = 1.0
    tested: list[dict] = field(default_factory=list)


def certify(
    scores: np.ndarray, y: np.ndarray, grid: np.ndarray, *, alpha: float, delta: float
) -> Certification:
    s, yy = scores.ravel(), y.ravel().astype(bool)
    out = Certification(tau=None)
    for tau in grid:
        applied = s >= tau
        n = int(applied.sum())
        k = int((applied & ~yy).sum())
        ucb = cp_upper(k, n, delta)
        out.tested.append({"tau": float(tau), "n": n, "errors": k, "ucb": round(ucb, 5)})
        if ucb > alpha:
            break
        out.tau, out.n_applied, out.n_errors, out.ucb = float(tau), n, k, ucb
    return out


def pairs_needed(
    alpha: float, delta: float, expected_risk: float, limit: int = 10**6
) -> int | None:
    """Smallest number of applied pairs whose Clopper-Pearson bound clears alpha at the
    expected risk; None if the expected risk is not below alpha."""
    if expected_risk >= alpha:
        return None
    lo, hi = 1, 1
    while cp_upper(round(expected_risk * hi), hi, delta) > alpha:
        hi *= 2
        if hi > limit:
            return None
    while lo < hi:
        mid = (lo + hi) // 2
        if cp_upper(round(expected_risk * mid), mid, delta) <= alpha:
            hi = mid
        else:
            lo = mid + 1
    return lo
