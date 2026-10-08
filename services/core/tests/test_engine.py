import numpy as np
import scipy.sparse as sp

from evigraph_core.engine import knn
from evigraph_core.engine.model import ColdStartEngine, TrainedEngine

TOPICS = {
    0: "incident notification security breach report hours supplier",
    1: "personal data processing subject consent controller privacy",
    2: "termination notice contract period expiry renewal",
}


def corpus(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    texts, y = [], []
    filler = "the parties agree that this clause applies under the governing law".split()  # noqa: SIM905
    for _ in range(n):
        labels = rng.uniform(size=3) < 0.4
        if not labels.any():
            labels[rng.integers(3)] = True
        words = list(rng.choice(filler, 20))
        for j in np.flatnonzero(labels):
            words += list(rng.choice(TOPICS[j].split(), 8))
        rng.shuffle(words)
        texts.append(" ".join(words))
        y.append(labels)
    return texts, np.array(y)


def test_trained_engine_ranks_true_concepts_first() -> None:
    texts, y = corpus(120)
    groups = np.arange(len(texts))
    engine = TrainedEngine(k=10, candidates=50, min_positives=5, folds=5).fit(texts, y, groups)
    test_texts, test_y = corpus(40, seed=1)
    scores = engine.score(test_texts).scores
    top1 = scores.argmax(axis=1)
    assert test_y[np.arange(len(test_y)), top1].mean() > 0.9


def test_engine_scores_are_invariant_to_copies_in_the_pool() -> None:
    texts, y = corpus(80)
    groups = np.arange(len(texts))
    engine = TrainedEngine(k=10, candidates=30, min_positives=5, folds=5).fit(texts, y, groups)
    queries, _ = corpus(10, seed=3)
    before = engine.score(queries).scores

    # add 40 exact copies of pool document 0 to the pool, in its provenance group
    assert engine.pool_x is not None and engine.pool_y is not None
    assert engine.pool_codes is not None
    engine.pool_x = sp.vstack([engine.pool_x, sp.vstack([engine.pool_x[0]] * 40)]).tocsr()
    engine.pool_y = np.vstack([engine.pool_y, np.repeat(engine.pool_y[:1], 40, axis=0)])
    engine.pool_codes = np.concatenate([engine.pool_codes, np.full(40, engine.pool_codes[0])])
    after = engine.score(queries).scores
    np.testing.assert_allclose(after, before, atol=1e-6)


def test_exclusion_removes_the_query_document_from_its_own_evidence() -> None:
    texts, y = corpus(60)
    groups = np.arange(len(texts))
    engine = TrainedEngine(k=5, candidates=20, min_positives=5, folds=3).fit(texts, y, groups)
    scored = engine.score([texts[0]], exclude=[0])
    used = {e.pool_index for per_concept in scored.evidence[0] for e in per_concept}
    assert 0 not in used


def test_knn_handles_empty_pool() -> None:
    q = sp.csr_matrix(np.ones((2, 3), np.float32))
    votes, _, voters = knn.vote(
        q,
        sp.csr_matrix((0, 3), dtype=np.float32),
        np.zeros((0, 2), bool),
        np.zeros(0, int),
        k=3,
        candidates=5,
    )
    assert votes.shape == (2, 2) and not votes.any() and voters == [[], []]


def test_cold_start_ranks_by_definition() -> None:
    concepts = [TOPICS[0], TOPICS[1], TOPICS[2]]
    engine = ColdStartEngine().fit(concepts, corpus(10)[0])
    scored = engine.score(["the supplier must report a security breach within 24 hours"])
    assert scored.scores[0].argmax() == 0
