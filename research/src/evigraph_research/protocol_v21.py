"""Frozen protocol 2.1: confirmation of H2 after the 2.0 failure analysis.

Registered after the 2.0 results (commit 4199fc5) and before any 2.1 run. Changes vs 2.0:

* provenance kNN widens its candidate window until it holds KNN_K distinct provenance groups
  (2.0 used a fixed window of 200 that copies of nearby sources could exhaust);
* fresh targets: TARGETS risk_cert documents drawn with TARGET_SEED from those not used as
  2.0 targets, so the fix is not confirmed on the data that motivated it;
* H2d (graph robustness) becomes a confirmatory rule; in 2.0 it was an observation.

Everything else is inherited from protocol 2.0.
"""

from evigraph_research.protocol_v2 import (  # noqa: F401  (re-exported settings)
    ALPHA,
    ALPHA_SECONDARY,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    COPIES,
    COST_MARGIN,
    INVARIANCE_MARGIN,
    KNN_CANDIDATES,
    MISLABEL_COPIES,
    MISLABEL_SEED,
    NOISE,
    NOISE_SEED,
    PROVENANCE_THRESHOLD,
    SYSTEMS,
    TARGETS,
)
from evigraph_research.protocol_v2 import TARGET_SEED as EXCLUDED_TARGET_SEED  # noqa: F401

PROTOCOL_VERSION = "2.1"
FROZEN_ON = "2026-10-08"
TARGET_SEED = 6
ADAPTIVE_CANDIDATES = True
RESULTS_FILE = "h2_results_v21.json"

# Decision rules: H2a, H2b, H2c exactly as in 2.0, plus
#   H2d graph robustness: G1 (naive graph) realised-risk change at m = 100 exact copies vs
#                         m = 0, upper bound of the 95% paired bootstrap CI <= INVARIANCE_MARGIN.
# H2 is supported if H2a, H2b and H2c hold; H2d is judged separately.
