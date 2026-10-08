# Can a covariate-shift correction replace provenance? (exploratory)

Not pre-registered; run on `risk_cert` with the protocol 2.1 scenario (500 fresh targets, exact
copies, system C1 = LEGAL-BERT + naive kNN, α = 0.10, δ = 0.1). Code: `weighted.py`, data:
`weighted_conformal.json`.

## Methods compared

* **Clean certification** — the deployed policy, certified before copies arrive.
* **Weighted re-certification** (Tibshirani et al., 2019 style, no new labels): a classifier
  distinguishes certification-time from deployment-time documents (descriptors: top-10 kNN
  votes, top-10 stacker scores, top similarity, vote concentration; gradient boosting); its
  odds give density-ratio weights for the labelled certification documents (clipped at 20);
  the threshold is re-certified on the weighted error rate with Kish's effective sample size.
* **Oracle re-certification** — certification on labelled post-copy data. It needs fresh labels;
  it is an upper reference, not a deployable fix.
* **Provenance-aware kNN (C1p)** — from protocol 2.1, no labels, no detector.

## Realised risk on targeted documents (and share of correct tags automated)

| Copies | Shift detector AUC | Clean | Weighted re-cert. | Oracle (new labels) | C1p (2.1) |
|---|---|---|---|---|---|
| 0 | 0.50 | 8.3% (56.0%) | 8.3% (56.0%) | 8.3% (56.0%) | 8.3% |
| 10 | 0.89 | 11.6% (57.1%) | **9.1%** (53.5%) | 9.1% (53.5%) | 8.3% |
| 30 | 0.91 | 16.3% (59.5%) | **12.3%** (55.2%) | 10.3% (52.5%) | 8.3% |
| 100 | 0.91 | 16.3% (59.5%) | **12.3%** (55.2%) | 10.3% (52.5%) | 8.3% |

## Findings

1. **The shift is detectable** (AUC ≈ 0.9), and weighting moves the threshold in the right
   direction: at 10 copies it matches the oracle and restores the guarantee on targets.
2. **At 30 copies weighting is not enough** (12.3% > 10%). Reweighting assumes P(y | x) is
   unchanged; duplication changes it — a concentrated kNN vote produced by copies looks like
   real consensus but is right less often — so no reweighting of clean data can fully describe
   the deployment risk.
3. **Even labelled re-certification leaves 10.3% on the targets**: certification bounds the
   average risk over all documents, not over the affected subgroup.
4. **The correction is fragile to its own design.** A first, weaker detector (logistic
   regression on per-document averages of the pair features) found no shift (weights ≈ 1) and
   changed nothing: averaging over concepts cancels the change in vote concentration.
5. **Provenance-aware aggregation needs neither labels nor a detector** and keeps the targeted
   risk at its clean value (8.3%), with no automation cost on clean data.

## Caveats

Single scenario and seed; the weighted procedure uses an effective-sample-size heuristic, not a
finite-sample weighted guarantee; descriptors were designed with knowledge of how copies act,
which favours the weighted method.
