# Protocol 4.0 results: copy detection under edits (H3), re-certification under drift (H4)

Run on 2026-10-09 with three LEGAL-BERT seeds. The protocol was registered in commit `574cb3d`
(part 5 of [`PROTOCOL.md`](../../docs/PROTOCOL.md)) before the run. `final_test` was opened
once for this run, as logged in `final_test_access.log`. Its labels had already been seen in
aggregate in protocol 3.0. Data: `protocol_v4_results.json`.

**Built-in check.** The exact-copy scenario on the protocol 2.1 `risk_cert` targets reproduces
the 2.1 result for naive kNN: targeted risk 16.31% against 16.31%.

| Rule | Result |
|---|---|
| H3: containment attribution keeps provenance kNN within 1 pp for deletion at every rate | **met** in 3 of 3 seeds (largest upper bound +0.4 pp) |
| H4: re-certification on 1,000 recent labelled acts, C1, α = 0.10, violation share ≤ 0.2 | **met** in 3 of 3 seeds (0.00, 0.05, 0.05) |

## H3: copy detection under edits

Setting: 500 `final_test` targets that were not 3.0 targets, from 344 sources. Each source
gets 100 copies. Each copy is edited independently by deleting a share of tokens or by
substituting tokens with words drawn from train texts. A copy joins the provenance group of
its candidate source (its nearest train document) if the method's score reaches the threshold
fixed in advance.

**Attribution rate** (share of copies attributed to their source's group, `final_test`
targets):

| Edit | Median cosine to source | MinHash ≥ 0.8 | Cosine ≥ 0.92 | Containment ≥ 0.98 |
|---|---|---|---|---|
| exact | 1.00 | 100% | 100% | 100% |
| delete 1% | 0.99 | 99% | 100% | 100% |
| delete 5% | 0.94 | 2% | 86% | 100% |
| delete 10% | 0.88 | 0% | 3% | 100% |
| delete 20–50% | 0.77–0.47 | 0% | 0% | 99–100% |
| substitute 1% | 0.98 | 98% | 100% | 79% |
| substitute 5% | 0.90 | 2% | 11% | 1% |
| substitute 10–50% | 0.80–0.31 | 0% | 0% | 0% |

**Change in realised risk on targets, α = 0.10, seed 0.** The clean targeted risk of C1 is
13.4% on these targets. Intervals resample sources.

| Edit | Naive kNN (harm) | Provenance, MinHash | Provenance, cosine | Provenance, containment |
|---|---|---|---|---|
| exact | +7.2 pp | 0.0 | 0.0 | 0.0 |
| delete 5% | +5.9 pp | +6.3 pp | +1.4 pp | **0.0** [−0.2, +0.2] |
| delete 10% | +5.1 pp | +5.3 pp | +5.1 pp | **0.0** [−0.1, +0.2] |
| delete 30% | +3.2 pp | +3.5 pp | +3.5 pp | **0.0** |
| delete 50% | +1.1 pp | +1.1 pp | +1.1 pp | **0.0** |
| substitute 1% | +6.4 pp | −0.1 pp | 0.0 | +4.5 pp |
| substitute 5% | +5.0 pp | +5.2 pp | +5.3 pp | +5.3 pp |
| substitute 10% | +3.9 pp | +4.3 pp | +4.3 pp | +4.3 pp |
| substitute 30% | +1.1 pp [+0.1, +2.3] | +1.2 pp | +1.2 pp | +1.2 pp |
| substitute 50% | +0.5 pp [−0.1, +1.1] | +0.5 pp | +0.5 pp | +0.5 pp |

Seeds 1 and 2 agree. The naive harm is +6.7 to +7.5 pp for exact copies and +1.1 to +2.1 pp at
30% substitution. The `risk_cert` targets show the same pattern (secondary analysis in the
JSON).

**Findings.**

1. **Containment closes the deletion gap completely** (H3). A deleted copy's words are a
   subset of its source's, so containment stays at 1.0 however much is deleted. No genuine
   `risk_cert` document reaches 0.98.
2. **There is a danger zone the three detectors cannot see.** Substituting 5–30% of tokens
   defeats all three methods (≤ 11% attribution), but the copies still raise the targeted
   risk by +1 to +5 pp. Only at about 50% substitution do copies become too dissimilar to
   matter (+0.5 pp, interval includes 0).
3. **The methods are complementary.** Containment catches deletions and misses light
   substitution (79% at 1%); cosine and MinHash do the opposite. A union of cosine and
   containment would attribute every scenario that any single method does, but the risk of
   the union was not run.

## H4: re-certification from a recent labelled audit

`final_test` was split by date into an audit pool (acts published before 2014-01-01, 2,203)
and an evaluation period (from 2014-01-01, 2,797). For each audit size, 20 random audit
samples were drawn. The threshold was re-certified on each sample with the same grid and δ,
then applied to the evaluation period.

**C1 (LEGAL-BERT + kNN), α = 0.10.** Original certificate from `risk_cert` (2010–2012)
vs re-certification on recent audits:

| Seed | Original: risk / AutoRecall | N = 250 | N = 500 | N = 1,000 | N = 2,000 |
|---|---|---|---|---|---|
| 0 | 12.1% / 46.0% | 7.8% (5% viol.) / 33% | 8.2% (0%) / 34% | 8.8% (0%) / 35% | 9.2% (0%) / 36% |
| 1 | 12.1% / 45.1% | 7.8% (0%) / 34% | 8.3% (0%) / 36% | 8.9% (5%) / 37% | 9.0% (0%) / 37% |
| 2 | 12.0% / 46.5% | 8.4% (5%) / 35% | 8.5% (5%) / 36% | 8.6% (5%) / 36% | 8.5% (0%) / 36% |

Each cell gives the mean realised risk over 20 draws, the share of draws with risk > α (in
parentheses), and the mean AutoRecall. T1 behaves the same way: original 10.9–11.5%,
re-certified 8.3–8.9% at N = 1,000, no violations.

**At α = 0.05 (reported without a rule) re-certification does not help.** The original
certificates already ran at 4.8–5.3% on the evaluation period. Thresholds re-certified on
2012–2013 audits run at 4.8–5.5% for C1 at N = 1,000, and the share of draws above α is 0.70,
0.15 and 0.95 in the three seeds. At a tight α, the residual drift between the audit period
and the evaluation period (one to two years) is as large as the margin the bound leaves.

**Findings.**

1. **A modest recent audit restores the α = 0.10 guarantee.** 500–1,000 labelled acts from
   the preceding period bring the realised risk from 12% back to 8–9%, with violations in at
   most 5% of draws.
2. **It costs automation.** AutoRecall falls from 46% to about 36%. Part of the original
   automation was bought with risk above α.
3. **At α = 0.05 a one-off audit is not enough.** The drift that remains between the audit
   and the evaluation period consumes the margin, so a tight α needs a rolling audit,
   re-certification close to the period it covers, or a drift-aware method. Adaptive
   conformal inference (Gibbs & Candès, 2021) is one candidate, not evaluated here.

## What this adds to the paper

* The copy-detection failure flagged by the review is resolved for deletions (containment),
  and its true boundary is mapped. Moderate substitution (5–30%) evades every detector tested
  yet still inflates risk. This is the remaining open problem, and the scenario an adversary
  would use.
* Temporal drift, the main new finding of protocol 3.0, has a working operational remedy at
  α = 0.10: periodic re-certification on a recent labelled audit of about 1,000 documents. This
  is the mechanism EviGraph Core implements, and it is now measured.
