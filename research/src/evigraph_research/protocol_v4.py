"""Frozen protocol 4.0: copy detection under edits (H3) and re-certification under drift (H4).

Registered on 2026-10-09, after the protocol 3.0 results and before any run of this protocol.
`final_test` labels were seen in aggregate in protocol 3.0; this protocol uses them again and
says so. Stackers are those of protocol 3.0 (fitted on model_dev for each LEGAL-BERT seed).

Attribution thresholds were fixed from genuine documents only, never from risk results: on
risk_cert, the largest TF-IDF cosine of a document to its nearest train document is 0.909 and
the largest word containment is 0.968. Each threshold is the next value above the maximum,
so no genuine risk_cert document would be attributed to a train document.
"""

from evigraph_research.protocol_v2 import (  # noqa: F401  (re-exported settings)
    ALPHA,
    ALPHA_SECONDARY,
    BOOTSTRAP_RESAMPLES,
    INVARIANCE_MARGIN,
    KNN_CANDIDATES,
    TARGETS,
)

PROTOCOL_VERSION = "4.0"
FROZEN_ON = "2026-10-09"
SEEDS = (0, 1, 2)
BOOTSTRAP_SEED = 11

# ---- H3: copy detection under edits
# Copies: m = COPIES per source of each target (the target's nearest train document).
# Edits are applied independently to every copy: "del" deletes a share of tokens, "sub"
# replaces a share of tokens with tokens drawn from train texts (EDIT_SEED).
COPIES = 100
EDIT_KINDS = ("del", "sub")
EDIT_RATES = (0.01, 0.05, 0.1, 0.2, 0.3, 0.5)
EDIT_SEED = 12
# Attribution: a copy's candidate is its nearest train document by TF-IDF cosine among the
# source and the source's ATTRIBUTION_CANDIDATES nearest train documents. The copy joins the
# candidate's provenance group if the method's score reaches its threshold; otherwise it is its
# own group.
ATTRIBUTION_CANDIDATES = 200
ATTRIBUTION = {
    "minhash": 0.8,  # MinHash Jaccard of word 5-grams (protocols 2.x)
    "cosine": 0.92,  # TF-IDF cosine
    "containment": 0.98,  # share of the copy's word types present in the candidate
}
# Targets: primary on final_test (TARGETS documents drawn with FINAL_TARGET_SEED from those
# that were not protocol 3.0 targets); secondary on risk_cert (the protocol 2.1 targets).
FINAL_TARGET_SEED = 10
# Decision rule H3 (seed-wise, confirmed with 3 of 3 seeds, primary targets, alpha = ALPHA):
#   for deletion at every rate, the upper bound of the 95% source-clustered bootstrap interval
#   of the change in targeted risk of provenance kNN with containment attribution is
#   <= INVARIANCE_MARGIN.
# Reported without a rule: attribution rates of every method, the risk change of naive kNN
# ("harm") and of provenance kNN with each method, for both edit kinds.

# ---- H4: re-certification from a recent labelled audit
# final_test is split by publication date: the audit pool holds acts published before
# SPLIT_DATE, the evaluation period the acts from SPLIT_DATE on.
SPLIT_DATE = "2014-01-01"
AUDIT_SIZES = (250, 500, 1000, 2000)
AUDIT_DRAWS = 20  # random audit samples per size, seeds 0..AUDIT_DRAWS-1
H4_SYSTEMS = ("T1_strong", "C1_strong+knn")
# Thresholds are re-certified on the audit sample with the protocol 1.0 grid (calib_fit) and
# DELTA. Reported: realised risk and AutoRecall on the evaluation period for the original
# certificate (risk_cert) and for each re-certification; the share of draws whose realised
# risk exceeds alpha.
# Decision rule H4 (seed-wise, 3 of 3): for C1 at N = 1000 and alpha = ALPHA, the share of
# draws with realised risk > alpha on the evaluation period is <= H4_MAX_VIOLATION_SHARE.
# The LTT guarantee is <= delta = 0.1 under exchangeability; 0.2 allows for Monte Carlo error
# with 20 draws and for the drift that continues inside final_test.
H4_MAX_VIOLATION_SHARE = 0.2
RESULTS_FILE = "protocol_v4_results.json"
