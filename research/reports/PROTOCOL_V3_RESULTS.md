# Protocol 3.0 results: the single evaluation on `final_test`

Run on 2026-10-09 with three LEGAL-BERT seeds. Protocol registered on 2026-10-08 (part 4 of
[`PROTOCOL.md`](../../docs/PROTOCOL.md)) and amended before opening (§17). The dry run on
`risk_cert` reproduced the certification-time features exactly (max difference 0.0) and the
certified automation of protocols 1.0 and 2.1 for all eight systems (`final_dryrun_v3.json`).
`final_test` was opened four times, all logged in `final_test_access.log`: once per seed for
LEGAL-BERT predictions and once for this evaluation. No code was changed after opening.
Data: `final_results_v3.json`.

**Periods.** Certification (`risk_cert`) covers acts published from 2010-02 to 2012-08;
`final_test` covers 2012-08 to 2016-01 (5,000 acts). The reference pool (`train`) ends in
2007-10.

## Summary

| Question | Rule | Result |
|---|---|---|
| F1 guarantee on a later period, α = 0.10 | holds / violated / inconclusive per system and seed | **violated** in 13 of 15 cases (T1, C1, C1p, G1, G1p × 3 seeds), inconclusive in 2 |
| F2 graph adds beyond text | lower CI bound > 0 for all three contrasts | **not met** in 3 of 3 seeds |
| F3 H2a naive kNN vulnerable | lower CI bound of C1 targeted risk > α | **met** 3 of 3 |
| F3 H2b provenance invariant | upper CI bound of change ≤ 1 pp | **met** 3 of 3 (by construction for exact copies) |
| F3 H2c no clean cost | AutoRecall(C1p) − AutoRecall(C1) ≥ −2 pp | **met** 3 of 3 |
| F3 H2d graph robust | upper CI bound of change ≤ 1 pp | **met** 3 of 3 (by construction) |

## F1: the certificate does not survive temporal drift

Realised risk on `final_test` at the threshold certified on `risk_cert` (seed 0; seeds 1–2 in
the JSON):

| System | mRP risk_cert → final | AutoRecall certified → final | Realised risk, α = 0.10 (95% CI) | Realised risk, α = 0.05 |
|---|---|---|---|---|
| T0 TF-IDF | 0.716 → 0.673 | 40.4% → 27.5% | 9.8% (9.1–10.5) | 3.6% |
| T1 LEGAL-BERT | 0.735 → 0.690 | 50.5% → 42.8% | 11.5% (10.9–12.1) | 3.4% |
| C1 + kNN | 0.754 → 0.701 | 56.3% → 47.6% | 12.2% (11.6–12.8) | 4.1% |
| C1p + provenance kNN | 0.754 → 0.701 | 56.3% → 47.8% | 12.2% (11.7–12.8) | 4.2% |
| C2 + neighbour text | 0.735 → 0.702 | 50.4% → 38.3% | 10.4% (9.8–11.0) | 5.5% |
| G1 + graph | 0.751 → 0.700 | 55.4% → 46.4% | 12.2% (11.7–12.8) | 4.9% |
| G2 + all | 0.740 → 0.707 | 54.1% → 43.6% | 11.6% (11.0–12.2) | 6.8% |

Across seeds, realised risk at α = 0.10 is 10.7–12.3% for T1, C1, C1p, G1 and G1p (G1/G1p
seed 1: 10.3%, inconclusive). At α = 0.05, T1, C1 and C1p stay below 5% in every seed (3.2–4.7%),
G1 in two of three, while C2 and G2 exceed it (5.5–6.8%).

**Reading.** LTT certifies risk under exchangeability. Two to six years after the
certification period, ranking quality drops (mRP −0.03 to −0.05), and the realised risk of the
certified threshold exceeds α = 0.10 by 1–2 pp. Only the weakest system, TF-IDF, stays within α.
A certificate is therefore a statement about the period it was computed on. A deployed system
needs fresh labelled audits and re-certification. EviGraph Core implements this as audit
sampling that suspends auto-apply, but the research protocol had not evaluated it.

## F2: the citation graph still adds nothing beyond retrieval

AutoRecall difference at the fixed certified threshold on `final_test` (α = 0.10):

| Contrast | Seed 0 | Seed 1 | Seed 2 |
|---|---|---|---|
| G1 − C1 | −1.2 pp [−1.7, −0.8] | −5.3 pp [−5.8, −4.9] | −6.5 pp [−7.0, −6.0] |
| G1 − C2 | +8.2 pp [+7.6, +8.6] | +3.1 pp [+2.5, +3.5] | +3.4 pp [+2.9, +3.8] |
| G2 − C1 | −4.0 pp [−4.4, −3.6] | −3.3 pp [−3.7, −2.9] | −9.0 pp [−9.5, −8.5] |

The graph beats the neighbour-text control but loses to retrieval in every seed. The H1
conclusion replicates on held-out data.

## F3: duplication replicates out of sample

500 `final_test` targets (354 distinct sources), copies added after certification, α = 0.10,
seed 0. Seeds 1–2 agree within 0.2 pp:

| Copies (edit level) | C1 naive kNN: targets | C1: all final_test | C1p provenance: targets | G1 graph: targets |
|---|---|---|---|---|
| 0 | 12.2% | 12.2% | 12.2% | 13.4% |
| 10 exact | 15.5% | 12.5% | 12.2% | 13.6% |
| 100 exact | **20.5%** (17.3–24.0) | 13.2% | 12.2% | 13.6% |
| 100, 1% tokens deleted | 19.8% | 13.1% | 11.8% | 13.6% |
| 100, 5% tokens deleted | 19.2% | 13.0% | **19.6%** | 13.6% |

Intervals resample copied sources. With 1% of tokens deleted, MinHash attributes 98.8% of
copies to their source and provenance kNN stays at its clean value. With 5% deleted, it
attributes 2.5%, and provenance kNN fails exactly like naive kNN. Copies add +8.4 pp to the
risk of targeted documents on top of the drift found in F1. The marginal effect over all
`final_test` documents is +1.0 pp, with 10% of documents targeted.

## What changes in the story

1. **New, and the most practically important:** a risk certificate on legal documents does not
   transfer across time. Certified at 10%, the policy runs at 11–12% two to six years later.
   This is a measured violation of the exchangeability assumption under natural drift.
2. H1 replicates: the graph is no substitute for retrieval.
3. H2 replicates out of sample with three seeds. Retrieval-based voting is the most fragile
   component. Provenance grouping helps exactly as far as the copy detector reaches.
