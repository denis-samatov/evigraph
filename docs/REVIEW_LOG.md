# Review log

## Review 1 — automated critical review, 2026-10-08

An independent model run with fresh context, instructed to review the project as a skeptical
venue reviewer (read-only access to the repository and reports). **It is not a substitute for
a human expert**; see [`REVIEW_REQUEST.md`](REVIEW_REQUEST.md) for the questions sent to one.
Every numerical claim in the review was checked against `research/reports/*.json` before it
was acted on; all of them were correct.

**Verdict of the review:** workshop — borderline, weak accept if reframed as a careful
negative and replication study; main track — reject.

### Findings and responses

| # | Finding | Response | Status |
|---|---|---|---|
| 1 | H2b (provenance kNN invariant) and H2d (graph unaffected) hold **by construction** for exact copies; pre-registering them adds no evidence about data | Paper reframed: contribution is a measured failure mode and where a simple fix works; "provably neutralises" removed; §5 states the by-construction nature | fixed in paper |
| 2 | The only non-trivial case — edited copies — fails (5% deletion: MinHash attributes 2.9% of copies) | Stated as the main limitation; protocol 3.0 now reports edited copies on `final_test`; similarity-based collapse of candidates is the next experiment | partly addressed, experiment pending |
| 3 | Targets are chosen to be affected, LTT bounds marginal risk | Marginal risk added: over all risk_cert documents, naive kNN goes from 8.7% to 13.8% (still > α); protocol 3.0 reports marginal risk | fixed |
| 4 | H2 measured on risk_cert, the certification split itself (clean risk is in-sample) | Stated in §5; protocol 3.0 repeats the scenario on `final_test` targets | fixed by 3.0 |
| 5 | Clopper–Pearson over dependent pairs | Sensitivity added: the certified C1 bound stays below α even with a 5× smaller effective sample (UCB 0.091 → 0.096); a document-level bound remains future work | partly addressed |
| 6 | C1 was selected among six systems on risk_cert; primary α chosen from version-0 results | Stated in Limitations (union bound needed for the selected system) | documented |
| 7 | G2 (pre-registered) missing from the paper; secondary mRP rule unreported | G2 added to both tables; secondary rule reported (G2 is best on mRP, worse on certified automation) | fixed |
| 8 | G1 − C1 interval [−7.0, −0.5] is entirely negative: "no gain" understates it | Paper now says the graph lowers certified automation relative to retrieval, with the bias caveat of §6 | fixed |
| 9 | Number mismatches: +4.9 → 4.8 pp; +0.01 → 0.02 pp; graph moves ≤ 0.3 → 0.4 pp; RusLawOD range 2.2–7.2% → 1.4–7.2% | Corrected | fixed |
| 10 | Policy docstring says "calibrated score", code uses raw score | Docstring corrected | fixed |
| 11 | "Neighbours published before" enforced for neighbour text, not graph votes; hub sizes and dedup use `final_test` texts | Stated in Limitations (no labels involved; no effect under the chronological split) | documented |
| 12 | Weighted-conformal comparison is unfavourable to the baseline (moves τ only, Kish heuristic, detector iterated after a null result, one seed) | Caveats were in the report; the paper now presents it as exploratory and lists them | documented |
| 13 | Missing prior work: copy detection in truth discovery, certified kNN / RAG robustness, diversity re-ranking, RCPS, adaptive conformal | Added to Related work (Dong et al. 2009; Jia et al. 2022; Xiang et al. 2024; Carbonell & Goldstein 1998; Bates et al. 2021; Gibbs & Candès 2021) | fixed |
| 14 | Missing baselines: index-time dedup, MMR, per-cluster cap, audit-based re-certification | Listed in Limitations; not run | open |
| 15 | Protocol 3.0 gaps: no noise conditions, pool unspecified, no runner, no clustered bootstrap, interpretation if F1 fails | Amendment §17 made before opening; runner `final.py` committed with a dry run | fixed |
| 16 | k = 20 saturation: at m ≥ 20 naive kNN becomes 1-NN (m = 30 and 100 coincide) | Stated in §5 | documented |
| 17 | Registrations are self-timestamped git commits, no third-party registry | Acknowledged; future protocols can be deposited on OSF before running | open |

### What the review changes about the story

The defensible claim is narrower than the first draft: certified thresholds over retrieval
features silently lose their guarantee when the retrieval pool receives copies, and grouping
by provenance fixes this exactly as far as the copy detector reaches. The most valuable next
experiment is therefore a detection-robustness curve (edit level → attribution → risk) for
MinHash, similarity-based candidate collapse and embedding grouping, on realistic duplication
(template families, consolidated versions, paraphrases).
