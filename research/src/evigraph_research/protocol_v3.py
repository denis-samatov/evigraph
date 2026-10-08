"""Frozen protocol 3.0: the single evaluation on final_test.

Registered on 2026-10-08, before final_test was opened and before LEGAL-BERT seeds 1 and 2
finished training. No system, feature, threshold grid or decision rule may change after
final_test is opened; a code fix needed after opening is reported as a deviation.

Systems are frozen exactly as in protocols 1.0 and 2.1: stackers fitted on model_dev,
thresholds certified on risk_cert. For LEGAL-BERT seeds 1 and 2 the same procedure is
repeated with that seed's predictions; nothing else depends on the seed.
"""

from evigraph_research.protocol_v2 import (  # noqa: F401  (re-exported settings)
    ALPHA,
    ALPHA_SECONDARY,
    BOOTSTRAP_RESAMPLES,
    COST_MARGIN,
    INVARIANCE_MARGIN,
    KNN_CANDIDATES,
    PROVENANCE_THRESHOLD,
    TARGETS,
)

PROTOCOL_VERSION = "3.0"
FROZEN_ON = "2026-10-08"
SEEDS = (0, 1, 2)  # LEGAL-BERT fine-tuning seeds
BOOTSTRAP_SEED = 9
RESULTS_FILE = "final_results_v3.json"

# F1 guarantee on a later period: for T1, C1 and G1 (and the provenance variants C1p, G1p),
#    realised risk on final_test at the threshold certified on risk_cert at ALPHA.
#    "holds" if the point estimate <= ALPHA; "violated" if the lower bound of the 95%
#    document-bootstrap CI > ALPHA; otherwise "inconclusive". final_test is the latest
#    period of MultiEURLEX, so this is a test under natural temporal drift.
# F2 H1 replication: AutoRecall at the fixed certified threshold on final_test, contrasts of
#    protocol.H1_CONTRASTS, paired document bootstrap. The graph adds information beyond text
#    only if the lower CI bound is > 0 for every contrast.
# F3 H2 replication: the protocol 2.1 scenario (adaptive window, exact copies, m in COPIES)
#    with TARGETS final_test documents drawn with FINAL_TARGET_SEED; rules H2a-H2d of 2.1.
FINAL_TARGET_SEED = 8
COPIES = (0, 10, 30, 100)
# Amendment before opening (independent review, 2026-10-08):
# * the reference pool for final_test is train only, as for every earlier split;
# * edited copies (NOISE > 0) are reported without a decision rule: the open question is the
#   copy detector, and H2b / H2d hold by construction for exact copies;
# * F3 intervals resample sources (targets sharing a copied source are one cluster);
# * marginal risk over all final_test documents is reported next to the targeted risk;
# * F3 rules compare each scenario with m = 0 on the same documents, so they are interpretable
#   even if F1 finds temporal drift; seeds share one test set and are not independent
#   replications.
NOISE = (0.0, 0.01, 0.05)
# Seeds: every rule is evaluated per seed and reported as "holds in k of 3 seeds"; a rule is
# confirmed only with 3 of 3. If a seed has not finished training, the verdict uses the
# available seeds and the report says so.
