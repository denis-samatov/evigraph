# Pilot benchmark on Russian legislation (RusLawOD)

How much expert-reviewed data does EviGraph Core need before auto-apply can be certified, and
does the guarantee hold on documents from a later period? Measured with
`evigraph-core benchmark-ruslawod` on 2026-10-08.

## Setup

* **Corpus:** RusLawOD (Saveliev & Kuchakov, 2024; CC BY-NC 4.0 — fine for evaluation, not for
  commercial use of the data), file `ruslawod_11.parquet`: 8,551 federal acts with the official
  classifier of legal acts (`classifierByIPS`), 1990–2026. Text: first 50,000 characters.
* **Catalogs:** level 1 — 21 classifier sections (2.5 per act), the size of a typical pilot
  catalog; level 2 — 132 rubrics with at least 20 acts in the review pool. Concept definitions
  for cold start are built from the most frequent labels under each code in the data.
* **Temporal split:** the 1,000 newest acts (after 2022-12-29) are the evaluation set; reviewed
  documents are sampled from the 7,551 older acts. Gold labels stand in for expert review.
* **Workflow:** exactly the production path — ingestion with provenance groups, review
  completion, training (30% of provenance groups held out), certification at α ∈ {10%, 5%},
  δ = 0.1, then the certified threshold applied to the evaluation set.

## Results

**Level 1 (21 sections)**

| Reviewed | mRP | α = 10%: certified | realised risk on later acts | tags automated | docs fully automatic | α = 5%: certified | realised risk | tags automated |
|---|---|---|---|---|---|---|---|---|
| 300 | 0.637 | no (76 held-out docs) | — | — | — | no | — | — |
| 500 | 0.656 | yes | 2.5% | 20.7% | 5.8% | no | — | — |
| 1,000 | 0.705 | yes | 5.0% | 32.9% | 11.6% | yes | 2.9% | 26.0% |
| 2,000 | 0.738 | yes | 7.2% | 43.3% | 19.3% | yes | 3.1% | 30.7% |
| 4,000 | 0.785 | yes | 6.1% | 45.6% | 21.0% | yes | 2.2% | 33.1% |

**Level 2 (132 rubrics)**

| Reviewed | mRP | α = 10% | realised risk | tags automated | α = 5% | realised risk | tags automated |
|---|---|---|---|---|---|---|---|
| 1,000 | 0.572 | yes | 5.3% | 22.9% | yes | 1.4% | 17.0% |
| 4,000 | 0.667 | yes | 6.3% | 28.8% | no | — | — |

In every certified configuration the realised error rate on later acts stayed below α.

## What this means for a pilot

1. **About 500 reviewed documents** are the minimum for certifying α = 10% with a catalog of ~20
   tags; **about 1,000** for α = 5%. A 300-document pilot can run in suggest-and-review mode
   but will not unlock auto-apply.
2. **Automation grows with reviewed data** — from a fifth of the tags at 500 documents to almost
   half at 4,000 (α = 10%). The review effort therefore pays back over the pilot.
3. **Finer catalogs automate less.** With 132 rubrics, 4,000 reviewed documents automate 29% of
   tags at α = 10%, and α = 5% did not certify: the error rate among the most confident
   rubric assignments is already above 5%.
4. **The guarantee transferred across time** (training on acts up to 2022, evaluation on
   2023–2026) — but this is one corpus and one period; production still needs audit monitoring.

## Bug found and fixed by this benchmark

The first run never certified α = 5%. The strictest threshold of the grid was placed to apply
50 out-of-fold pairs on the training part, which on the 2.4× smaller certification part meant
29 pairs — fewer than the 45 that zero errors need to certify 5% at δ = 0.1, so testing stopped
at the first threshold. The grid start now depends on α, δ and the split sizes only
(`policy.grid_start`), which keeps the guarantee intact; α = 5% then certifies from 1,000
reviewed documents.

## Caveats

One random draw of reviewed documents per size and one evaluation period; gold classifier codes
replace real experts (no anchoring, no disagreement); the classifier itself contains easy
sections (personnel acts, issuing bodies) that raise top-1 precision (93–97%), which is why mRP
and automation are the reported measures.
