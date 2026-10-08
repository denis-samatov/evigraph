"""Frozen protocol 2.0: robustness of certified tagging to source duplication (H2).

See docs/PROTOCOL.md, part 2. Version 1.0 constants in protocol.py are reused unchanged
(splits, stackers, threshold grid, delta). Changing anything here is a new version.

Scenario: a policy is fitted and certified on the clean reference pool (train). At deployment
the pool receives copies of existing documents. Stackers and certified thresholds stay fixed;
only pool-dependent features (kNN and graph votes) of risk_cert documents are recomputed.
"""

PROTOCOL_VERSION = "2.0"
FROZEN_ON = "2026-10-08"

# Targets and sources: TARGETS risk_cert documents drawn with TARGET_SEED; the source of a
# target is its nearest train document by TF-IDF cosine. Each distinct source is copied.
TARGETS = 500
TARGET_SEED = 2
COPIES = (0, 1, 3, 10, 30, 100)
# Copy text noise: share of tokens deleted at random (0 = exact copy).
NOISE = (0.0, 0.01, 0.05)
NOISE_SEED = 3
# Secondary scenario: copies carry the labels of a random other train document.
MISLABEL_COPIES = (10, 100)
MISLABEL_SEED = 4

# Provenance: a copy joins its source's provenance group when the MinHash-estimated Jaccard
# of word 5-gram shingles is at least this value. Pool groups are the near-duplicate groups.
PROVENANCE_THRESHOLD = 0.8
# Provenance-aware kNN retrieves this many candidates, collapses them to provenance groups
# (group similarity = max member similarity, group labels = mean member labels) and votes
# with the top KNN_K groups.
KNN_CANDIDATES = 200

SYSTEMS = (
    "T1_strong",
    "C1_strong+knn",
    "C1p_strong+knn_prov",
    "G1_strong+graph",
    "G1p_strong+graph_prov",
)

ALPHA = 0.10  # certified on clean risk_cert with protocol 1.0 settings
ALPHA_SECONDARY = 0.05
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 5

# Decision rules, evaluated on the targeted risk_cert documents (realised risk = errors /
# automatically applied pairs among them), at m = 100 exact copies, alpha = ALPHA:
#   H2a vulnerability: C1 realised risk, lower bound of its 95% bootstrap CI > ALPHA.
#   H2b invariance:    C1p realised-risk change vs m = 0, upper bound of the 95% paired
#                      bootstrap CI <= INVARIANCE_MARGIN.
#   H2c cost:          clean AutoRecall(C1p) - AutoRecall(C1) >= -COST_MARGIN (point estimate).
# Secondary (reported, no decision): graph systems, noise levels, mislabelled copies.
INVARIANCE_MARGIN = 0.01
COST_MARGIN = 0.02
