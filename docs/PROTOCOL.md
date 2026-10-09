# EviGraph evaluation protocol

Version 1.0 frozen on 2026-10-07. Code reads every parameter from
[`research/src/evigraph_research/protocol.py`](../research/src/evigraph_research/protocol.py);
changing any parameter is a new protocol version recorded under "History".

# Part 1. Protocol 1.0: does the citation graph add accuracy beyond text? (H1)

## 1. Data status before the freeze

Version 0 (the research spike, commit `a6467f6`) used `risk_cert` while debugging the
certification procedure: two errors — certifying on isotonic plateaus and a threshold grid
that was too coarse — were found from results on `risk_cert`. Therefore:

* version 0 results on `risk_cert` are exploratory;
* from version 1.0 on, `risk_cert` is used only to certify the systems of section 6, without
  choosing between them and without changing the procedure;
* the main result for the paper is computed once on `final_test`, after the final system is
  frozen.

## 2. Data and splits

| Parameter | Value |
|---|---|
| Corpus | MultiEURLEX, English, EuroVoc `level_2`, 127 concepts |
| Archive | `coastalcph/multi_eurlex`, sha256 `3a2195bc…e83` |
| Split manifest | sha256 `b36fef1d2a5cb410873173f74ee40d7da7359ecd62ebfbd4c4fc01423fef6b01` |
| Split seed | 20261007 |

| Split | Allowed use |
|---|---|
| `train` | model fitting; the only source of labels in the reference graph |
| `train` → early stopping | latest 5% of `train` groups by date; only to pick the epoch of neural models |
| `model_dev` | feature and hyper-parameter choice; stacker fitting (2 folds by split group, seed 1) |
| `calib_fit` | calibrator; threshold grid |
| `risk_cert` | certification of the systems in section 6 |
| `final_test` | once, after the freeze; only through `protocol.open_final_test`, every opening is logged to `reports/final_test_access.log` |

Model inputs are text only. The Cellar properties `work_is_about_concept_eurovoc`,
`resource_legal_is_about_subject-matter` and `resource_legal_is_about_concept_directory-code`
never enter the features.

## 3. Reference graph

* Neighbour labels come from `train` only; a document's own labels never take part.
* Neighbours are documents linked to the document directly by any relation (in either
  direction) or through a shared external act that 2 to 500 corpus documents point to.
* A neighbour is published strictly before the document.
* Graph features: mean label vector of neighbours per relation type (`cites`, `amends`,
  `repeals`, `based_on`, `other`, `hub`) and a flag for the presence of each type.

## 4. Controls: the same materials without the graph

| Control | Sees | Does not see |
|---|---|---|
| C1 `knn` | labels of the 20 nearest `train` documents by TF-IDF cosine, and the maximum similarity | EUR-Lex relations |
| C2 `nbtext` | the document's text and the mean TF-IDF of its graph neighbours (the set of section 3), truncated to its 1,000 heaviest terms and normalised | neighbour labels and relation types |

C2 is trained like the text model (TF-IDF + SGD) on `train`, where every document has its own
earlier neighbours from `train`.

## 5. Strong text model

| Parameter | Value |
|---|---|
| Model | `nlpaueb/legal-bert-base-uncased`, revision `15b570cb…`, 110M parameters |
| Hyper-parameters | 4 epochs, lr 3·10⁻⁵, batch 16, weight decay 0.01 |
| Input | first 512 word pieces of the canonical text |
| Training | BCE, AdamW, 10% linear warm-up, gradient clip 1.0, seed 0 |
| Epoch selection | best mRP on the early-stopping subset of `train` |

Known limitation: LEGAL-BERT was pre-trained (MLM, no labels) on EU legislation from EUR-Lex,
which includes the texts of all splits, `final_test` among them. There is no label leakage, but
the model has seen the texts. The paper states this explicitly.

## 6. Registered systems

Every system is the same stacker: logistic regression over (document, concept) pairs with a
`logit(prior)` feature and the blocks below.

| System | Feature blocks |
|---|---|
| T0_tfidf | `p_tfidf` |
| T1_strong | `p_strong` |
| C1_strong+knn | `p_strong`, `knn` |
| C2_strong+nbtext | `p_strong`, `p_nbtext` |
| G1_strong+graph | `p_strong`, `graph` |
| G2_strong+knn+nbtext+graph | `p_strong`, `knn`, `p_nbtext`, `graph` |

## 7. Certification

* Policy: apply a pair automatically if the raw stacker score is ≥ τ.
* Grid of τ from `calib_fit`: the k-th threshold applies ≈ 500·1.1^k pairs.
* Learn-then-Test, testing from the strictest threshold to the most permissive, stopping at
  the first non-rejection; one-sided Clopper–Pearson bound; δ = 0.1.
* α ∈ {0.01, 0.02, 0.05, 0.10}. **Primary α = 0.10.** Chosen from version 0: at α ≤ 0.05
  automation on this corpus is a few percent and differences between systems cannot be
  measured. α = 0.05 is secondary.
* Isotonic calibration is used only to display scores and compute ECE.

## 8. Hypothesis H1 and decision rule

Primary metric: certified AutoRecall at α = 0.10 on `risk_cert`.

Contrasts (treatment − control): G1 − C1, G1 − C2, G2 − C1.

95% confidence interval: paired bootstrap over `risk_cert` documents, 1,000 resamples, seed 0.
Each resample repeats the whole certification with the same threshold grid.

**The graph adds information beyond text if the lower bound of the interval is positive for
all three contrasts.** Secondary: mRP difference on `model_dev` (out-of-fold), paired bootstrap.

## 9. Known limitations of version 1.0

* One seed for the strong text model (compute budget).
* The Clopper–Pearson bound assumes independent pairs; the document bootstrap partly
  compensates.
* The reference graph is not extended with `model_dev` and `calib_fit` labels, so coverage
  decays towards `final_test` (65%).

# Part 2. Protocol 2.0: robustness to source duplication (H2)

Frozen on 2026-10-08, before the first run. Parameters in
[`protocol_v2.py`](../research/src/evigraph_research/protocol_v2.py). Splits, stackers,
threshold grid and δ are inherited unchanged from version 1.0. Version 1.0 results are known:
the best system is C1 (LEGAL-BERT + kNN), which is why its vulnerability is tested.

## 10. Scenario

The policy is fitted and certified on the clean reference pool (`train`). At deployment the
pool receives copies of existing documents. Stackers and certified thresholds do not change;
only pool-dependent features (kNN and graph votes) of `risk_cert` documents are recomputed.

* **Targets:** 500 random `risk_cert` documents (seed 2).
* **Source of a target:** its nearest `train` document by TF-IDF cosine.
* **Copies:** each distinct source is copied m ∈ {0, 1, 3, 10, 30, 100} times. Copies get new
  identifiers, the source's labels and its outgoing EUR-Lex links; they have no incoming links.
* **Copy text noise:** share of randomly deleted tokens 0, 1% or 5% (seed 3).
* **Secondary scenario:** copies carry the labels of a random other `train` document
  (m ∈ {10, 100}, seed 4).

## 11. Systems

| System | Difference |
|---|---|
| T1_strong | independent of the pool (scenario control) |
| C1_strong+knn | kNN of version 1.0: every pool document is a separate vote |
| C1p_strong+knn_prov | provenance-aware kNN: 200 candidates are collapsed to provenance groups (group similarity = max over members, labels = mean), the 20 best groups vote |
| G1_strong+graph | graph votes of version 1.0 |
| G1p_strong+graph_prov | graph votes where each provenance group is one neighbour; the hub size compared with the cap of 500 is counted in groups, not documents |

A provenance group in the pool is a near-duplicate group from `dedup` (Jaccard ≥ 0.9). A copy
joins its source's group if the MinHash-estimated Jaccard is ≥ 0.8; otherwise it forms its
own group.

The C1p and G1p stackers are fitted on `model_dev` under the version 1.0 rules; thresholds
are certified on the clean `risk_cert` at α = 0.10 (secondary α = 0.05).

## 12. Metrics and decision rules

Realised risk is the share of errors among automatically applied pairs. It is measured on the
targeted documents at the fixed certified threshold. 95% intervals: document bootstrap, 1,000
resamples, seed 5. The threshold is not recomputed, so the bias found in version 1.0 does not
apply here.

At m = 100 exact copies and α = 0.10:

* **H2a, vulnerability:** the lower bound of the interval for C1's realised risk is above α.
* **H2b, invariance:** the upper bound of the interval for the change in C1p's risk relative
  to m = 0 (paired bootstrap) is at most 1 pp.
* **H2c, cost:** on the clean pool, AutoRecall(C1p) − AutoRecall(C1) ≥ −2 pp.

H2 is supported if all three rules hold. Graph systems, noise levels and mislabelled copies
are reported without a decision rule.

# Part 3. Protocol 2.1: confirming H2 after the version 2.0 analysis

Registered on 2026-10-08 after the 2.0 results (commit `4199fc5`) and before the first 2.1 run.
Parameters in [`protocol_v21.py`](../research/src/evigraph_research/protocol_v21.py).

## 13. What changed and why

* **Adaptive candidate window in C1p.** In 2.0, rule H2b failed: C1p is invariant up to 30
  copies, but at 100 copies the fixed window of 200 candidates fills up with copies of nearby
  sources and fewer than 20 groups remain. In 2.1 the window widens (×4) until it holds 20
  distinct groups or the whole pool.
* **Fresh targets.** 500 `risk_cert` documents drawn with seed 6 from those that were not 2.0
  targets. The fix is not confirmed on the data that motivated it.
* **H2d becomes a confirmatory rule.** In 2.0 graph robustness was an observation; in 2.1 it
  is a hypothesis with a decision rule.

Everything else is as in 2.0: scenarios, systems, thresholds, bootstrap.

## 14. Decision rules

H2a, H2b and H2c as in section 12. In addition:

* **H2d, graph robustness:** the upper bound of the 95% interval for the change in realised
  risk of G1 (naive graph) at 100 exact copies relative to m = 0 is at most 1 pp.

H2 is supported if H2a, H2b and H2c hold; H2d is judged separately.

# Part 4. Protocol 3.0: the single evaluation on `final_test`

Registered on 2026-10-08, before `final_test` was opened and before LEGAL-BERT seeds 1 and 2
finished training. Parameters in
[`protocol_v3.py`](../research/src/evigraph_research/protocol_v3.py).

## 15. Frozen systems and seeds

* Systems T0, T1, C1, C2, G1, G2 (section 6) and C1p, G1p (section 11), with stackers and
  thresholds fitted and certified exactly as before: stackers on `model_dev`, thresholds on
  `risk_cert` at α = 0.10 (secondary α = 0.05), δ = 0.1, the same grid.
* LEGAL-BERT seeds {0, 1, 2}: identical hyper-parameters, only the seed changes. For each seed
  the stackers and thresholds are refitted with that seed's predictions.
* `final_test` is opened through `protocol.open_final_test` only: once per seed to predict with
  LEGAL-BERT and once for the evaluation run. Each opening is logged. Nothing is changed
  after opening; a fix needed after opening is reported as a deviation.

## 16. Questions and decision rules

* **F1, guarantee on a later period.** Realised risk on `final_test` at the certified
  threshold for T1, C1, C1p, G1 and G1p. The guarantee **holds** if the point estimate is ≤ α,
  is **violated** if the lower bound of the 95% document-bootstrap interval is > α, and is
  **inconclusive** otherwise. `final_test` is the latest period of MultiEURLEX, so this tests
  the guarantee under natural temporal drift, not under exchangeability.
* **F2, replication of H1.** AutoRecall at the fixed certified threshold; contrasts G1 − C1,
  G1 − C2, G2 − C1; paired document bootstrap. The graph adds information beyond text only if
  the lower bound is positive for every contrast.
* **F3, replication of H2.** The protocol 2.1 scenario (exact copies, m ∈ {0, 10, 30, 100},
  adaptive window) with 500 `final_test` targets drawn with seed 8; rules H2a–H2d as in 2.1.

Intervals: 1,000 document-bootstrap resamples, seed 9. Every rule is evaluated per seed and
reported as "holds in k of 3 seeds"; a rule is confirmed only with 3 of 3. If a seed has not
finished training, the verdict uses the available seeds and the report says so.

## 17. Amendment before opening (after an independent review)

Made on 2026-10-08, before `final_test` was opened, in response to the review in
[`REVIEW_LOG.md`](REVIEW_LOG.md). Decision rules are unchanged.

* The reference pool for `final_test` documents is `train` only, as for every earlier split.
* F3 also reports edited copies (1% and 5% of tokens deleted) without a decision rule. The open
  question is the copy detector: for exact copies H2b and H2d hold by construction, so their
  confirmation checks the implementation, not the data.
* F3 intervals resample copied sources: targets that share a source form one cluster.
* Marginal risk over all `final_test` documents is reported next to the targeted risk.
* F3 compares every scenario with m = 0 on the same documents, so it is interpretable even if
  F1 finds temporal drift. Seeds share one test set; they measure training variance, not
  independent replications.
* The runner (`final.py`) is committed before opening and is first run with `--dry-run`,
  where `risk_cert` stands in for `final_test` and the feature path is checked against the
  certification-time features.

# Part 5. Protocol 4.0: copy detection under edits (H3) and re-certification under drift (H4)

Registered on 2026-10-09, after the protocol 3.0 results and before any run of this protocol.
Parameters in [`protocol_v4.py`](../research/src/evigraph_research/protocol_v4.py). The
`final_test` labels were seen in aggregate in protocol 3.0 and are used again here.

## 18. H3: does a better copy detector close the gap left by edited copies?

Protocol 3.0 showed that provenance-aware kNN fails once copies are edited (5% of tokens
deleted: MinHash attributes 2.5% of copies). We compare three attribution methods, each
applied to a copy's candidate source, which is its nearest train document by TF-IDF cosine
among the source and the source's 200 nearest train documents:

| Method | Score | Threshold |
|---|---|---|
| MinHash | Jaccard of word 5-grams | 0.8 (protocols 2.x) |
| Cosine | TF-IDF cosine | 0.92 |
| Containment | share of the copy's word types present in the candidate (Broder, 1997) | 0.98 |

The thresholds were set from genuine documents only. On `risk_cert` the largest cosine of a
document to its nearest train document is 0.909 and the largest containment is 0.968; each
threshold is the next round value above the maximum. No risk result was looked at.

Scenario: 100 copies of the source of each of 500 targets; edits are deletion of a share of
tokens or substitution with tokens drawn from train texts, at 1, 5, 10, 20, 30 and 50%.
Primary targets: 500 `final_test` documents that were not protocol 3.0 targets (seed 10).
Secondary: the protocol 2.1 `risk_cert` targets.

**Rule H3** (per seed, confirmed with 3 of 3): for deletion at every rate, the upper bound of
the 95% source-clustered interval of the change in targeted risk of provenance kNN with
containment attribution is at most 1 pp. Attribution rates, the harm to naive kNN, and every
method under substitution are reported without a rule.

## 19. H4: does re-certification on a recent labelled audit restore the guarantee?

`final_test` is split by date. Acts published before 2014-01-01 form the audit pool (2,203);
acts from 2014-01-01 on form the evaluation period (2,797). For N ∈ {250, 500, 1000, 2000},
20 random audit samples are drawn from the audit pool. The threshold is re-certified on each
sample (same grid, δ = 0.1, α ∈ {0.10, 0.05}). We report realised risk and AutoRecall on the
evaluation period for the original certificate and for each re-certification, for T1 and C1.

**Rule H4** (per seed, 3 of 3): for C1 at N = 1000 and α = 0.10, the share of audit draws whose
realised risk on the evaluation period exceeds α is at most 0.2. Under exchangeability LTT
guarantees at most δ = 0.1; the margin allows for Monte Carlo error with 20 draws and for drift
inside `final_test`.

## History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-07 | first freeze |
| 1.0 | 2026-10-07 | before the first run: LEGAL-BERT base chosen (MPS benchmark: 1.28 s/step, ~4.5 h for 4 epochs; small ~1.3 h); the C2 neighbour vector truncated to 1,000 terms (untruncated, the train matrix took 8 GB) |
| 2.0 | 2026-10-08 | part 2: hypothesis H2, source-duplication scenario, decision rules; registered before the first run |
| 2.0 | 2026-10-08 | before the first run: in G1p the hub size is counted in provenance groups (otherwise copies push a hub over the cap and change features around the grouping) |
| 2.1 | 2026-10-08 | part 3: adaptive candidate window, fresh targets, rule H2d; registered after the 2.0 results and before the 2.1 run |
| — | 2026-10-08 | document translated from Russian to English; no change in substance (the Russian original is in the git history) |
| 3.0 | 2026-10-08 | part 4: single evaluation on `final_test` with three LEGAL-BERT seeds; registered before `final_test` was opened |
| 3.0 | 2026-10-08 | section 17: amendment after an independent review, before `final_test` was opened (edited copies reported, source-clustered bootstrap, marginal risk, pool specified) |
| 4.0 | 2026-10-09 | part 5: copy detection under edits (H3) and re-certification from a recent audit (H4); registered after the 3.0 results and before any 4.0 run |
