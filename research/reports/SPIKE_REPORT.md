# EviGraph — research spike summary

Date: 2026-10-07. Corpus: MultiEURLEX (English, EuroVoc `level_2`, 127 concepts).
Machine-readable data: `graph_report.json`, `split_manifest.json`, `baseline.json`.
`final_test` has not been opened.

> **Update 2026-10-08.** The protocol is frozen (`docs/PROTOCOL.md`, version 1.0) and the
> strong text control is done. Outcome: by the protocol rule the graph adds no information
> beyond text — the graph system (AutoRecall 55.4% at α = 0.10) is no better than
> retrieval of similar documents (56.3%). LEGAL-BERT raised certified automation at α = 0.05
> from 4.9% to 28–34%. Details: [PROTOCOL_V1_RESULTS.md](PROTOCOL_V1_RESULTS.md).
>
> **Update 2026-10-08, H2.** Retrieval of similar documents loses its certified guarantee when
> copies enter the collection (risk 16.3% at a certified 10%); provenance-aware aggregation and
> the citation graph are robust. Details: [PROTOCOL_V21_RESULTS.md](PROTOCOL_V21_RESULTS.md).

## Summary

1. **The graph exists and carries signal.** 99.96% of documents have EUR-Lex relations.
   95% of model_dev documents have a labelled neighbour in train. A neighbour vote without
   text reaches mRP 0.53 against 0.17 for the label prior. The pre-set criterion is met by a
   wide margin.
2. **On top of text the graph adds almost nothing.** Simple graph features add +0.008 mRP
   and +0.02 macro-F1 on model_dev, and +0.2 pp certified AutoRecall on risk_cert — within
   noise. The graph signal mostly duplicates the text. For H1 this means: showing a structural
   contribution needs features absent from text (typed directed relations, time, GNN) and a
   comparison with a strong text control.
3. **Graph coverage decays over time:** 95% in model_dev, 80% in risk_cert, 65% in
   final_test. The reference graph has to be extended with verified labels as evaluation
   proceeds, otherwise the graph contributes less and less towards the end of test.
4. **The provenance hypothesis cannot be tested on natural MultiEURLEX duplication.**
   Template copies cover 23% of the corpus but under a chronological split almost never cross
   split boundaries (0.04–0.06% in calib/cert/test). Synthetic checks remain (repeating a
   source 1/10/100 times); a natural test needs another corpus.
5. **Strict automation is out of reach on this corpus.** At α ≤ 0.02 no threshold is
   certified: even the most confident assignments are 3–5% wrong. At α = 0.05 AutoRecall is
   5%, at α = 0.10 it is 40%. The protocol pipeline (text + calibration + certification) works
   end to end, but "few errors, much automation" is limited by ranking quality and temporal
   drift.

## 1. Data

| | |
|---|---|
| Source | `coastalcph/multi_eurlex`, `data/multi_eurlex.tar.gz`, sha256 `3a2195bc…e83` |
| Documents | 65,000 (55,000 / 5,000 / 5,000 in official train / dev / test) |
| `level_2` concepts | 127 |
| Canonical text | NFC, unified line breaks; evidence offsets in the product are defined over it |

Model inputs are text only. The Cellar properties `work_is_about_concept_eurovoc`,
`resource_legal_is_about_subject-matter` and `resource_legal_is_about_concept_directory-code`
are the labels or close to them and never enter the features.

## 2. EUR-Lex graph

274,078 act-to-act edges from Cellar SPARQL (325 queries, ~3.5 min). Main types: `cites`,
`based_on`, `amends` (including `modifies`), `repeals`; about twenty rare types are grouped as
`other`.

**Share of documents with a labelled neighbour in train**

| Split | `cites` | `amends` | `based_on` | any direct relation | direct or via an external act |
|---|---|---|---|---|---|
| model_dev | 0.41 | 0.30 | 0.69 | 0.88 | **0.95** |
| calib_fit | 0.31 | 0.16 | 0.57 | 0.76 | 0.80 |
| risk_cert | 0.30 | 0.14 | 0.61 | 0.77 | 0.80 |
| final_test | 0.35 | 0.12 | 0.35 | 0.62 | **0.65** |

"Via an external act" means a shared relation target outside the corpus that 2 to 500 corpus
documents point to (larger ones are treaty articles with no topical signal).

**Label homophily** (Jaccard over `level_2`, pairs within train): random pairs 0.075;
`cites` 0.34; `based_on` 0.34; `other` 0.47; `repeals` 0.51; `amends` 0.54.

## 3. Duplicates

MinHash LSH over word 5-grams of the first 20,000 characters, Jaccard threshold 0.9.

| Type | Groups of size > 1 | Documents in them |
|---|---|---|
| exact copies | 14 | 28 |
| near copies | 672 | 4,813 |
| template copies (digits masked) | 2,343 | 14,856 (23%) |

The largest template group is 1,633 "standard import values" regulations from 1999–2007.
The template of these acts changes every few years, so copies cluster in time. Share of
documents with a template copy in train: model_dev 5.5%; calib_fit, risk_cert and final_test
0.04–0.06%.

## 4. Splits

| Split | Documents | Period | Purpose |
|---|---|---|---|
| train | 49,998 | 1958 – 2007-10-27 | models; the only labels of the reference graph |
| model_dev | 4,900 | 2007-10-29 – 2010-02-05 | feature choice, stackers |
| calib_fit | 2,341 | 2010-02-05 – 2012-08-27 | calibrator, threshold grid |
| risk_cert | 2,659 | 2010-02-05 – 2012-08-28 | policy certification |
| final_test | 5,000 | 2012-08-28 – 2016-01-05 | not opened |
| excluded_overlap | 102 | — | late members of early groups, excluded to keep chronology |

A split group is a connected component over exact copies, near copies and `corrects`
relations. Manifest sha256: `b36fef1d2a5cb410873173f74ee40d7da7359ecd62ebfbd4c4fc01423fef6b01`.

## 5. Baseline

Hashed TF-IDF (uni- and bigrams, 2^21 features, first 50,000 characters) and one logistic
model per label (SGD, α = 5·10⁻⁶, 15 epochs).

**model_dev, text only:** mRP 0.782; micro-F1 0.698; macro-F1 0.369 (threshold 0.5).
Candidate recall: @5 0.707; @10 0.881; @20 **0.947**; @30 0.968. With 127 concepts a candidate
generator is hardly needed: 20 candidates cover 95% of gold assignments.

**Stackers.** Both are logistic regression on model_dev, 2 folds by group, out-of-fold.

| | Text | Text + graph |
|---|---|---|
| mRP (model_dev, OOF) | 0.791 | 0.799 |
| micro-F1 | 0.753 | 0.759 |
| macro-F1 | 0.501 | 0.521 |
| AutoRecall at empirical risk ≤ 0.05 (OOF, uncertified) | 0.285 | 0.298 |
| mRP (risk_cert) | 0.716 | 0.723 |
| ECE over each document's top-10 pairs (risk_cert) | 0.028 | 0.022 |

ECE over all pairs (0.002) is uninformative: hundreds of thousands of easy negative pairs
dominate it, so the report uses top-10 ECE.

## 6. Policy certification

Policy: "apply automatically if the score is ≥ τ". Learn-then-Test with fixed-sequence testing
from the strictest to the most permissive threshold, one-sided Clopper–Pearson bound, δ = 0.1.
The threshold grid is built from calib_fit only: the k-th threshold applies about 500·1.1^k
pairs.

**risk_cert, 2,659 documents**

| α | System | Certified | Applied | Realised risk | 90% CI, document bootstrap | AutoRecall | Per document | Documents fully correct |
|---|---|---|---|---|---|---|---|---|
| 0.01 | both | no | 0 | — | — | 0 | 0 | 0 |
| 0.02 | both | no | 0 | — | — | 0 | 0 | 0 |
| 0.05 | text | yes | 675 | 0.036 | 0.024–0.047 | **0.049** | 0.25 | 0.1% |
| 0.05 | text + graph | yes | 704 | 0.036 | 0.025–0.046 | **0.052** | 0.26 | 0.1% |
| 0.10 | text | yes | 5,883 | 0.094 | 0.088–0.102 | **0.404** | 2.21 | 3.1% |
| 0.10 | text + graph | yes | 5,882 | 0.089 | 0.083–0.096 | **0.407** | 2.21 | 3.6% |

When nothing is applied, risk is undefined and automation is zero. That is a refusal to
automate, not a zero-error system.

**Why so little at α = 0.05.** On model_dev (OOF) 28% of assignments could be automated at an
empirical risk ≤ 5%, but only 5% on risk_cert. Two causes combine: temporal drift (the model is
trained on data up to 2007, risk_cert is 2010–2012, mRP drops from 0.79 to 0.72) and an error
rate of about 3–4% even in the most confident top block, consistent with EuroVoc annotation
noise.

## 7. Cost (MacBook, 12 cores, 16 GB)

| Stage | Time |
|---|---|
| download of the 2.77 GB archive | ~5 min |
| extraction of the English part | 75 s |
| Cellar SPARQL | 213 s |
| duplicates (MinHash, 3 variants) | 25 s |
| TF-IDF (uncached / cached) | 12 s / 0.3 s |
| 127 text models + prediction | 56 s, peak RSS ~2 GB |
| graph features, stackers, certification | < 3 s |

Text model: ~5.7 ms per evaluation document (training and prediction together).

## 8. Limitations of the spike

* **Comparison against weak text.** There is no text control that sees the neighbours' texts;
  without it the contribution of structure cannot be separated from that of extra context.
* **A single run, no confidence intervals for differences** between "text" and
  "text + graph". Gains of 0.2–1 pp are not a result before a paired bootstrap and several
  seeds.
* **The Clopper–Pearson bound assumes independent assignments.** Assignments of one document
  are correlated. A document bootstrap gives similar intervals, but the paper needs a
  document-level treatment.
* **risk_cert was used while debugging the procedure.** The two fixed errors (certifying on
  isotonic plateaus and a grid that was too coarse) were found from risk_cert results. The
  procedure must now be frozen; the numbers in section 6 are exploratory. For the paper the
  final result is computed on final_test after the system is fixed.
* **Pre-training leakage was not checked.** The spike uses no LLM, but an LLM branch would need
  a control on acts published after the model's cut-off date.

## 9. Next steps

1. ~~**Freeze the protocol**~~ — done, `docs/PROTOCOL.md` v1.0.
2. ~~**Strong text control**~~ — done: LEGAL-BERT, kNN and "text + neighbours' text";
   results in `PROTOCOL_V1_RESULTS.md`.
3. **Graph features absent from text:** relation direction and type, neighbour time,
   neighbour labels from a growing reference graph (model_dev → calib → cert in chronological
   order), then a GNN.
4. **Document-level policy:** certify "document processed fully automatically" rather than
   individual pairs. This is closer to the product and removes the pair-dependence issue.
5. **Provenance hypothesis:** ~~synthetic repetitions 1/10/100 on this corpus~~ — done as
   protocol 2.x; a corpus with natural duplicates is still open (Russian pilot, contracts,
   support tickets).
6. **Paired bootstrap and 3–5 seeds** for all comparisons.
