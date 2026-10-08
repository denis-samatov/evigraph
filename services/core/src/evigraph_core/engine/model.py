"""Engine models.

* ColdStartEngine — no reviewed data yet: concepts are ranked by TF-IDF cosine between the
  document and the concept's label and definition. Useful for suggest-and-review only.
* TrainedEngine — the research recipe: per-concept text model, provenance-aware kNN over the
  reviewed pool and a logistic stacker over (logit p_text, kNN vote, top similarity,
  logit prior, has-text-model). Text and kNN features for the stacker are produced
  out-of-fold, with folds split by provenance group, so the stacker never sees in-sample
  scores and copies cannot leak across folds.
"""

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from evigraph_core.engine import knn

EPS = 1e-6
TOKEN_PATTERN = r"(?u)\b\w\w+\b"  # noqa: S105  (regex, not a secret)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        sublinear_tf=True,
        ngram_range=(1, 2),
        min_df=1,
        max_features=200_000,
        token_pattern=TOKEN_PATTERN,
        dtype=np.float32,
    )


@dataclass
class Evidence:
    """A reviewed document that voted for the suggestion (one per provenance group)."""

    pool_index: int
    similarity: float
    has_concept: bool


@dataclass
class Scored:
    scores: np.ndarray  # (n_docs, n_concepts)
    evidence: list[list[list[Evidence]]]  # [doc][concept] -> supporting reviewed documents


@dataclass
class ColdStartEngine:
    kind: str = "cold_start"
    vectorizer: TfidfVectorizer | None = None
    concept_matrix: sp.csr_matrix | None = None

    def fit(self, concept_texts: list[str], corpus: list[str]) -> "ColdStartEngine":
        self.vectorizer = _vectorizer().fit(corpus + concept_texts)
        self.concept_matrix = self.vectorizer.transform(concept_texts)
        return self

    def score(self, texts: list[str], exclude: list[int | None] | None = None) -> Scored:
        assert self.vectorizer is not None and self.concept_matrix is not None
        x = self.vectorizer.transform(texts)
        scores = np.asarray((x @ self.concept_matrix.T).todense(), dtype=np.float32)
        empty = [[[] for _ in range(scores.shape[1])] for _ in texts]
        return Scored(scores, empty)

    def passage_scores(self, passages: list[str], concept: int) -> np.ndarray:
        """Cosine of each passage to the concept's label and definition."""
        assert self.vectorizer is not None and self.concept_matrix is not None
        x = self.vectorizer.transform(passages)
        return np.asarray((x @ self.concept_matrix[concept].T).todense()).ravel()


@dataclass
class TrainedEngine:
    k: int
    candidates: int
    min_positives: int
    folds: int
    kind: str = "trained"
    vectorizer: TfidfVectorizer | None = None
    text_models: dict[int, LogisticRegression] = field(default_factory=dict)
    prior: np.ndarray | None = None
    pool_x: sp.csr_matrix | None = None
    pool_y: np.ndarray | None = None
    pool_codes: np.ndarray | None = None
    stacker: LogisticRegression | None = None
    oof_scores: np.ndarray | None = None  # stacker scores on training docs, out-of-fold

    # ---- text model -------------------------------------------------------------------
    def _fit_text(self, texts: list[str], y: np.ndarray):
        vec = _vectorizer().fit(texts)
        x = vec.transform(texts)
        models = {}
        for j in range(y.shape[1]):
            pos = int(y[:, j].sum())
            if pos >= self.min_positives and pos < len(texts):
                models[j] = LogisticRegression(C=4.0, solver="liblinear", max_iter=1000).fit(
                    x, y[:, j]
                )
        return vec, x, models

    def _p_text(self, vec, models, texts: list[str], prior: np.ndarray):
        x = vec.transform(texts)
        p = np.tile(prior, (len(texts), 1)).astype(np.float32)
        has = np.zeros(len(prior), dtype=bool)
        for j, m in models.items():
            p[:, j] = m.predict_proba(x)[:, 1]
            has[j] = True
        return x, p, has

    def _features(self, p_text, has, votes, top, prior) -> np.ndarray:
        n, n_lab = p_text.shape
        return np.column_stack(
            [
                _logit(p_text).ravel(),
                votes.ravel(),
                np.repeat(top, n_lab),
                np.tile(_logit(prior), n),
                np.tile(has.astype(np.float32), n),
            ]
        ).astype(np.float32)

    # ---- training ---------------------------------------------------------------------
    def fit(self, texts: list[str], y: np.ndarray, groups: np.ndarray) -> "TrainedEngine":
        _, codes = np.unique(groups, return_inverse=True)
        n_splits = min(self.folds, len(np.unique(codes)))
        if n_splits < 2:
            msg = "need documents from at least two provenance groups"
            raise ValueError(msg)
        oof_feats = np.zeros((len(texts) * y.shape[1], 5), dtype=np.float32)
        rows = np.arange(len(texts))
        for tr, te in GroupKFold(n_splits=n_splits).split(rows, groups=codes):
            tr_texts = [texts[i] for i in tr]
            prior = y[tr].mean(axis=0)
            vec, x_tr, models = self._fit_text(tr_texts, y[tr])
            x_te, p_te, has = self._p_text(vec, models, [texts[i] for i in te], prior)
            votes, top, _ = knn.vote(
                x_te, x_tr, y[tr], codes[tr], k=self.k, candidates=self.candidates
            )
            feats = self._features(p_te, has, votes, top, prior)
            pair_rows = (te[:, None] * y.shape[1] + np.arange(y.shape[1])).ravel()
            oof_feats[pair_rows] = feats
        self.stacker = LogisticRegression(C=1.0, max_iter=2000).fit(oof_feats, y.ravel())
        self.oof_scores = self.stacker.predict_proba(oof_feats)[:, 1].reshape(y.shape)

        self.prior = y.mean(axis=0)
        self.vectorizer, self.pool_x, self.text_models = self._fit_text(texts, y)
        self.pool_y = y.astype(bool)
        self.pool_codes = codes
        return self

    # ---- scoring ----------------------------------------------------------------------
    def score(self, texts: list[str], exclude: list[int | None] | None = None) -> Scored:
        assert self.vectorizer is not None and self.stacker is not None
        assert self.pool_x is not None and self.pool_y is not None and self.prior is not None
        assert self.pool_codes is not None
        x, p, has = self._p_text(self.vectorizer, self.text_models, texts, self.prior)
        votes, top, voters = knn.vote(
            x,
            self.pool_x,
            self.pool_y,
            self.pool_codes,
            k=self.k,
            candidates=self.candidates,
            exclude=exclude,
        )
        feats = self._features(p, has, votes, top, self.prior)
        scores = self.stacker.predict_proba(feats)[:, 1].reshape(len(texts), -1)
        evidence = [
            [
                [
                    Evidence(
                        n.pool_index, round(n.similarity, 4), bool(self.pool_y[n.pool_index, j])
                    )
                    for n in voters[i][:3]
                ]
                for j in range(self.pool_y.shape[1])
            ]
            for i in range(len(texts))
        ]
        return Scored(scores.astype(np.float32), evidence)

    # ---- evidence ---------------------------------------------------------------------
    def passage_scores(self, passages: list[str], concept: int) -> np.ndarray:
        """Contribution of each passage to the concept.

        With a text model: the linear contribution x_passage . w_concept. Without one: cosine
        between the passage and the centroid of reviewed documents carrying the concept.
        """
        assert self.vectorizer is not None and self.pool_x is not None and self.pool_y is not None
        x = self.vectorizer.transform(passages)
        model = self.text_models.get(concept)
        if model is not None:
            return np.asarray(x @ model.coef_.ravel()).ravel()
        members = np.flatnonzero(self.pool_y[:, concept])
        if not len(members):
            return np.zeros(len(passages))
        centroid = np.asarray(self.pool_x[members].mean(axis=0)).ravel()
        norm = np.linalg.norm(centroid)
        return np.asarray(x @ (centroid / norm if norm else centroid)).ravel()
