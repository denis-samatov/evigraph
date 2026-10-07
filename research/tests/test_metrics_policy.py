import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from evigraph_research import metrics, policy
from evigraph_research.dedup import UnionFind, shingles
from evigraph_research.prepare import normalize_text


def test_r_precision_perfect_and_worst() -> None:
    y = np.array([[1, 1, 0, 0], [0, 0, 0, 1]], dtype=bool)
    assert metrics.r_precision(y, y.astype(float)) == 1.0
    assert metrics.r_precision(y, (~y).astype(float)) == 0.0


def test_r_precision_skips_docs_without_labels() -> None:
    y = np.array([[0, 0], [1, 0]], dtype=bool)
    assert metrics.r_precision(y, np.array([[0.9, 0.1], [0.8, 0.2]])) == 1.0


def test_recall_at_k() -> None:
    y = np.array([[1, 0, 1]], dtype=bool)
    s = np.array([[0.9, 0.8, 0.1]])
    assert metrics.recall_at_k(y, s, 1) == 0.5
    assert metrics.recall_at_k(y, s, 3) == 1.0


def test_automation_nothing_applied_is_undefined_risk_and_zero_recall() -> None:
    y = np.array([[1, 0]], dtype=bool)
    out = metrics.automation(y, np.zeros_like(y))
    assert math.isnan(out["risk"])
    assert out["auto_recall"] == 0.0


def test_automation_counts() -> None:
    y = np.array([[1, 0, 1], [0, 1, 0]], dtype=bool)
    auto = np.array([[1, 1, 0], [0, 1, 0]], dtype=bool)
    out = metrics.automation(y, auto)
    assert out["n_auto"] == 3
    assert out["n_errors"] == 1
    assert out["auto_recall"] == 2 / 3
    assert out["docs_fully_auto_correct"] == 0.5


def test_clopper_pearson_edges() -> None:
    assert policy.clopper_pearson_upper(0, 0, 0.1) == 1.0
    assert policy.clopper_pearson_upper(5, 5, 0.1) == 1.0
    # zero errors in n trials: upper bound = 1 - delta**(1/n)
    assert math.isclose(policy.clopper_pearson_upper(0, 100, 0.1), 1 - 0.1 ** (1 / 100))


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 50), st.integers(1, 400), st.floats(0.01, 0.3))
def test_clopper_pearson_upper_is_above_empirical_rate(k: int, n: int, delta: float) -> None:
    k = min(k, n)
    assert policy.clopper_pearson_upper(k, n, delta) >= k / n


def test_certify_stops_at_first_failure_and_returns_last_success() -> None:
    rng = np.random.default_rng(0)
    scores = rng.uniform(size=20_000)
    y = rng.uniform(size=20_000) < scores  # P(correct | score) = score
    thresholds = np.array([0.99, 0.97, 0.95, 0.9, 0.8, 0.5])
    cert = policy.certify(scores, y, thresholds, alpha=0.05, delta=0.1)
    assert cert.tau in {0.97, 0.95, 0.9}
    assert cert.tested[-1]["ucb"] > 0.05 or cert.tau == thresholds[-1]
    taus = [t["tau"] for t in cert.tested]
    assert taus == sorted(taus, reverse=True)


def test_candidate_thresholds_respect_min_applied() -> None:
    s = np.linspace(0, 1, 1001)
    grid = policy.candidate_thresholds(s, min_applied=100)
    assert (s >= grid[0]).sum() >= 100
    assert np.all(np.diff(grid) < 0)


def test_union_find_groups() -> None:
    uf = UnionFind(5)
    uf.union(0, 3)
    uf.union(3, 4)
    labels = uf.labels()
    assert labels[0] == labels[3] == labels[4]
    assert len(set(labels)) == 3


def test_template_shingles_ignore_numbers() -> None:
    tail = " establishing the standard import values"
    a = "Commission Regulation No 782/2012 of 28 August 2012" + tail
    b = "Commission Regulation No 101/2011 of 3 August 2011" + tail
    assert shingles(a, mask_digits=True) == shingles(b, mask_digits=True)
    assert shingles(a, mask_digits=False) != shingles(b, mask_digits=False)


def test_normalize_text_is_idempotent_and_nfc() -> None:
    raw = "Café \r\nline  \r\n"
    once = normalize_text(raw)
    assert once == "Café\nline"
    assert normalize_text(once) == once


def test_certify_on_tied_scores_cannot_split_a_plateau() -> None:
    # A calibrated score with a single top plateau: the strictest threshold takes the whole block.
    y = np.array([True] * 9000 + [False] * 1000 + [False] * 90_000)
    plateau = np.r_[np.full(10_000, 0.9), np.full(90_000, 0.1)]
    raw = np.r_[np.linspace(1.0, 0.95, 9000), np.linspace(0.949, 0.9, 1000), np.full(90_000, 0.1)]
    grid_plateau = np.array([0.9])
    assert policy.certify(plateau, y, grid_plateau, alpha=0.05, delta=0.1).tau is None
    grid_raw = np.array([0.99, 0.97, 0.95])
    assert policy.certify(raw, y, grid_raw, alpha=0.05, delta=0.1).tau is not None


def test_ece_topk_ignores_easy_negatives() -> None:
    prob = np.array([[0.9, 0.0, 0.0, 0.0]])
    y = np.array([[False, False, False, False]])
    assert metrics.expected_calibration_error_topk(prob, y, 1) > metrics.expected_calibration_error(
        prob, y
    )
