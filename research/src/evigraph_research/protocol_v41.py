"""Frozen protocol 4.1: rolling re-certification under temporal drift (H5).

Registered on 2026-10-12, after the protocol 4.0 results (a one-off audit restores
alpha = 0.10 but not alpha = 0.05) and before any run of this protocol. final_test labels were
seen in aggregate in protocols 3.0 and 4.0. Systems and grids are those of protocol 4.0.

final_test acts are grouped by calendar quarter of publication. Evaluation quarters are those
with at least MIN_QUARTER_DOCS acts and a full 12-month history inside final_test. Each scheme
produces a threshold per evaluation quarter from data published strictly before the quarter,
and the threshold is applied to the quarter's acts.

Schemes:
* original: the protocol 3.0 certificate (risk_cert, 2010-2012), never updated;
* one_off: certified once on every act published before the first evaluation quarter;
* rolling_6m / rolling_12m: re-certified every quarter on every act of the preceding 6 / 12
  months (every act reviewed);
* rolling_6m_sample: re-certified every quarter on SAMPLE_SIZE random acts of the preceding
  6 months (an audit budget), SAMPLE_DRAWS draws.
"""

from evigraph_research.protocol_v2 import ALPHA, ALPHA_SECONDARY  # noqa: F401

PROTOCOL_VERSION = "4.1"
FROZEN_ON = "2026-10-12"
SEEDS = (0, 1, 2)
SYSTEMS = ("T1_strong", "C1_strong+knn")
MIN_QUARTER_DOCS = 300
FIRST_EVALUATION_QUARTER = "2013Q4"  # final_test starts 2012-08-28; first full 12-month history
SCHEMES = ("original", "one_off", "rolling_6m", "rolling_12m", "rolling_6m_sample")
SAMPLE_SIZE = 500
SAMPLE_DRAWS = 20
# Reported per scheme, system, alpha and seed: pooled realised risk and AutoRecall over all
# evaluation quarters, realised risk per quarter, the number of quarters above alpha and of
# quarters where no threshold was certified (nothing auto-applied).
# Decision rule H5 (per seed, confirmed with 3 of 3): for C1 at alpha = ALPHA_SECONDARY (0.05),
# the pooled realised risk of rolling_6m over the evaluation quarters is <= alpha.
RESULTS_FILE = "protocol_v41_results.json"
