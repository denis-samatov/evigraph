"""Frozen evaluation protocol v1 (see docs/PROTOCOL.md). Changing anything here is a new version.

Code reads its evaluation constants from this module so that a run cannot silently deviate
from the registered protocol, and every report records PROTOCOL_VERSION.
"""

import datetime as dt
import getpass
import hashlib
import os

import orjson
import pandas as pd

from evigraph_research import paths

PROTOCOL_VERSION = "1.0"
FROZEN_ON = "2026-10-07"

# Data
MANIFEST_SHA256 = "b36fef1d2a5cb410873173f74ee40d7da7359ecd62ebfbd4c4fc01423fef6b01"
SPLIT_SEED = 20261007
FOLD_SEED = 1  # stacker 2-fold split by split group

# Reference graph
HUB_CAP = 500
GRAPH_LABEL_SOURCE = ("train",)

# Controls
KNN_K = 20
NBTEXT_TOP_TERMS = 1000  # neighbour TF-IDF mean truncated to its top terms per document

# Strong text model
STRONG_TEXT_MODEL = "nlpaueb/legal-bert-base-uncased"
STRONG_TEXT_REVISION = "15b570cbf88259610b082a167dacc190124f60f6"
STRONG_MAX_TOKENS = 512
STRONG_EPOCHS = 4
STRONG_LR = 3e-5
STRONG_BATCH = 16
STRONG_MICRO_BATCH = 8  # gradient accumulation to fit 16 GB unified memory
STRONG_WARMUP = 0.1
STRONG_SEED = 0
EARLY_STOP_SHARE = 0.05  # latest share of train groups, used only to pick the epoch

# Certification
DELTA = 0.1
ALPHA_PRIMARY = 0.10
ALPHAS = (0.01, 0.02, 0.05, 0.10)
GRID_MIN_APPLIED = 500
GRID_RATIO = 1.1
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 0

# Pre-registered systems: name -> feature blocks given to the stacker (always + logit(prior)).
SYSTEMS: dict[str, tuple[str, ...]] = {
    "T0_tfidf": ("p_tfidf",),
    "T1_strong": ("p_strong",),
    "C1_strong+knn": ("p_strong", "knn"),
    "C2_strong+nbtext": ("p_strong", "p_nbtext"),
    "G1_strong+graph": ("p_strong", "graph"),
    "G2_strong+knn+nbtext+graph": ("p_strong", "knn", "p_nbtext", "graph"),
}
# H1 contrasts: (treatment, control). Graph adds information beyond text if the lower
# bound of the 95% paired bootstrap CI of the AutoRecall difference at ALPHA_PRIMARY is > 0
# for every contrast.
H1_CONTRASTS = (
    ("G1_strong+graph", "C1_strong+knn"),
    ("G1_strong+graph", "C2_strong+nbtext"),
    ("G2_strong+knn+nbtext+graph", "C1_strong+knn"),
)

FINAL_TEST_ENV = "EVIGRAPH_OPEN_FINAL_TEST"
FINAL_TEST_LOG = paths.REPORTS / "final_test_access.log"


class ProtocolError(RuntimeError):
    pass


def manifest_digest(manifest: pd.DataFrame) -> str:
    cols = manifest[["celex_id", "split", "split_group"]]
    return hashlib.sha256(cols.to_csv(index=False).encode()).hexdigest()


def assert_manifest(manifest: pd.DataFrame) -> None:
    digest = manifest_digest(manifest)
    if digest != MANIFEST_SHA256:
        msg = f"split manifest {digest[:12]} differs from protocol {MANIFEST_SHA256[:12]}"
        raise ProtocolError(msg)


def open_final_test(reason: str) -> None:
    """Gate for any code path that reads final_test texts, labels or predictions."""
    if os.environ.get(FINAL_TEST_ENV) != "1":
        msg = f"final_test is sealed; set {FINAL_TEST_ENV}=1 to open it deliberately"
        raise ProtocolError(msg)
    entry = {
        "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "user": getpass.getuser(),
        "protocol": PROTOCOL_VERSION,
        "reason": reason,
    }
    with FINAL_TEST_LOG.open("ab") as f:
        f.write(orjson.dumps(entry) + b"\n")
