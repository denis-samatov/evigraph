import numpy as np
import pandas as pd
import scipy.sparse as sp
from hypothesis import given, settings
from hypothesis import strategies as st

from evigraph_research import provenance


def _pool(rng: np.random.Generator, n: int, d: int, n_lab: int):
    x = sp.random(n, d, density=0.2, random_state=int(rng.integers(1e9)), format="csr")
    x = sp.diags(1 / np.sqrt(np.asarray(x.multiply(x).sum(axis=1)).ravel() + 1e-12)) @ x
    y = rng.uniform(size=(n, n_lab)) < 0.2
    return x.tocsr().astype(np.float32), y


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.integers(1, 40))
def test_provenance_knn_is_invariant_to_exact_copies(seed: int, m: int) -> None:
    rng = np.random.default_rng(seed)
    x, y = _pool(rng, 120, 60, 7)
    q, _ = _pool(rng, 15, 60, 7)
    groups = np.arange(120)
    before, _, _ = provenance.knn_scores(q, x, y, k=5, groups=groups, candidates=80)

    src = int(rng.integers(120))
    x2 = sp.vstack([x, sp.vstack([x[src]] * m)]).tocsr()
    y2 = np.vstack([y, np.repeat(y[src : src + 1], m, axis=0)])
    g2 = np.concatenate([groups, np.full(m, groups[src])])
    after, _, _ = provenance.knn_scores(q, x2, y2, k=5, groups=g2, candidates=80)
    np.testing.assert_allclose(after, before, atol=1e-6)


def test_naive_knn_is_moved_by_copies() -> None:
    rng = np.random.default_rng(0)
    x, y = _pool(rng, 120, 60, 7)
    q = x[:1]
    before, _, top1 = provenance.knn_scores(q, x, y, k=5)
    src = int(top1[0])
    # copy the nearest document's neighbour ranked second, 10 times
    order = np.argsort(-(q @ x.T).toarray().ravel())
    second = int(order[1])
    x2 = sp.vstack([x, sp.vstack([x[second]] * 10)]).tocsr()
    y2 = np.vstack([y, np.repeat(y[second : second + 1], 10, axis=0)])
    after, _, _ = provenance.knn_scores(q, x2, y2, k=5)
    assert src == 0
    assert not np.allclose(after, before)


def _graph(m: int):
    celex = ["a", "b", "c", "q"] + [f"copy{i}" for i in range(m)]
    rows = [
        ("q", "work_cites_work", "a"),
        ("q", "work_cites_work", "b"),
        ("a", "resource_legal_based_on_resource_legal", "EXT1"),
        ("q", "resource_legal_based_on_resource_legal", "EXT1"),
        ("c", "resource_legal_based_on_resource_legal", "EXT1"),
    ]
    # copies of `a` inherit its outgoing edges, so they share the external act with q
    rows += [(f"copy{i}", "resource_legal_based_on_resource_legal", "EXT1") for i in range(m)]
    edges = pd.DataFrame(rows, columns=["src", "predicate", "dst"])
    fam = {
        "work_cites_work": "cites",
        "resource_legal_based_on_resource_legal": "based_on",
    }
    edges["family"] = edges["predicate"].map(fam)
    edges["dst_in_corpus"] = edges["dst"].isin(celex)
    y = np.zeros((len(celex), 3), dtype=bool)
    y[0, 0] = y[1, 1] = y[2, 2] = True
    y[4:, 0] = True
    is_pool = np.array([True, True, True, False] + [True] * m)
    groups = np.array([0, 1, 2, 3] + [0] * m)
    return celex, is_pool, y, edges, groups


def test_provenance_graph_votes_ignore_copies_naive_hub_votes_do_not() -> None:
    base = provenance.graph_features(*_graph(0)[:4], groups=_graph(0)[4])
    with_copies = provenance.graph_features(*_graph(20)[:4], groups=_graph(20)[4])
    for name in base.names:
        np.testing.assert_allclose(with_copies.votes[name][3], base.votes[name][3], atol=1e-6)

    naive_base = provenance.graph_features(*_graph(0)[:4])
    naive_copies = provenance.graph_features(*_graph(20)[:4])
    assert not np.allclose(naive_copies.votes["hub"][3], naive_base.votes["hub"][3])
    # identifier-based links are not copied: the direct `cites` vote is unchanged
    np.testing.assert_allclose(naive_copies.votes["cites"][3], naive_base.votes["cites"][3])


def test_provenance_hub_cap_counts_groups_not_copies() -> None:
    celex, is_pool, y, edges, groups = _graph(30)
    # cap 3: with 30 copies the hub holds 33 documents but only 3 groups
    naive = provenance.graph_features(celex, is_pool, y, edges, hub_cap=3)
    prov = provenance.graph_features(celex, is_pool, y, edges, groups=groups, hub_cap=3)
    assert naive.degree["hub"][3] == 0  # hub dropped: over the cap in documents
    assert prov.degree["hub"][3] == 2  # groups of a and c, each counted once
