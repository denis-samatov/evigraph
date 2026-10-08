# Copies Are Not Corroboration: Certified Document Tagging under Source Duplication

*Working draft, 2026-10-08. Numbers are generated from `research/reports/*.json`; every
experiment was pre-registered in `docs/PROTOCOL.md` before it was run.*

## Abstract

Automatic document tagging is deployable only when the error rate of the tags it applies
without review is controlled. Learn-then-Test (LTT) certifies a confidence threshold so that
the risk of auto-applied tags stays below a level α with high probability, assuming that the
data seen at deployment are exchangeable with the certification data. We study what happens
when this assumption is broken in a specific and common way: the reference collection that a
tagger retrieves evidence from receives copies of existing documents. On MultiEURLEX (English,
127 EuroVoc concepts) enriched with 274k act-to-act relations from EUR-Lex, in a sequence of
pre-registered experiments, we find that (i) a citation graph adds no accuracy over a strong
text model once a retrieval control with the same label information is included; (ii) the
best system — LEGAL-BERT with k-nearest-neighbour label propagation — loses its certified
guarantee when sources are duplicated after certification: realised risk on affected
documents grows from 8.3% to 16.3% at a certified 10%; (iii) aggregating evidence by
provenance group restores invariance to detectable copies at no cost on clean data; and
(iv) identifier-based citation links are robust to duplication by construction. The value of
the citation graph in this setting is robustness of guarantees, not accuracy.

## 1. Introduction

Two families of signals are commonly added to a text classifier for tagging documents with
concepts from a controlled vocabulary: *retrieval* — labels of similar documents in a
reference collection — and *structure* — labels of documents linked by citations,
amendments or a shared legal basis. Both are forms of label propagation, and both are usually
evaluated on accuracy.

We evaluate them instead as components of a *certified* tagging policy: a tag is applied
automatically only if the system's score clears a threshold certified by LTT to keep the
error rate of applied tags below α; everything else goes to a human reviewer. The relevant
quantity is the share of correct tags the policy can apply automatically (AutoRecall) at a
given α, and whether the realised risk stays below α in deployment.

The guarantee holds for exchangeable data. In document collections, a frequent violation is
duplication: templated acts, re-published texts, mirrored or slightly edited copies. A
retrieval-based tagger counts each copy as an independent vote. When copies arrive after
certification, the policy becomes over-confident exactly where copies dominate the
neighbourhood — and nothing in the deployed system signals it.

**Contributions.**

1. A pre-registered evaluation protocol for certified multi-label tagging with a frozen
   five-way split, a sealed final test set and explicit decision rules (§3).
2. A negative result on accuracy: EUR-Lex relations carry strong label signal (neighbour
   vote mRP 0.53 vs 0.17 for the prior), but add nothing over a retrieval control with the
   same label information (§4).
3. A positive result on robustness: kNN label propagation breaks certified guarantees under
   post-certification duplication, provenance-aware aggregation provably and empirically
   neutralises detectable copies, and citation links are robust by construction (§5).
4. A methodological note: percentile bootstrap intervals of a *certified* AutoRecall are
   biased downwards because of the fixed-sequence stopping rule (§6).

## 2. Data

* **MultiEURLEX**, English, EuroVoc level 2 (127 concepts), 65k EU acts with publication
  dates (Chalkidis et al., 2021).
* **EUR-Lex relations**: 274,078 edges from the Cellar SPARQL endpoint (cites, amends,
  repeals, based on, and rarer types); 99.96% of documents have at least one. Properties
  that encode the labels or classifications close to them (EuroVoc, subject matter,
  directory code) are excluded.
* **Duplicates**: MinHash LSH over word 5-grams. Exact copies are rare (28 documents), near
  copies (Jaccard ≥ 0.9) cover 4,813 documents, template copies (digits masked) 14,856 (23%).
  Templates change every few years, so under a chronological split copies almost never cross
  split boundaries (0.04–0.06% of calibration/certification/test documents): natural
  duplication cannot test robustness, which motivates the controlled injection of §5.

**Splits.** Official train is split chronologically into *train* (≤ 2007-10, 49,998 docs)
and *model_dev* (4,900); official dev is split by provenance group into *calib_fit* (2,341)
and *risk_cert* (2,659); official test (5,000) is *final_test* and remains sealed.
Split groups join exact copies, near copies and corrigenda.

**Sanity check against published numbers.** Fine-tuned LEGAL-BERT (T1) reaches mRP 0.735 on
risk_cert and C1 0.754. Chalkidis et al. (2021, Table 8) report mRP 0.736 for XLM-R fine-tuned
end-to-end on English level 2. Their number is on the official test split and ours on a
subset of the official dev split, so this is a plausibility check, not a comparison of models.

## 3. Method and protocol

**Systems.** Every system is the same stacker — logistic regression over (document, concept)
pairs with a prior term — fitted on model_dev (2-fold out-of-fold by split group) over
different feature blocks:

| System | Features |
|---|---|
| T0 | TF-IDF (hashed uni+bigrams) + per-concept SGD logistic regression |
| T1 | LEGAL-BERT base, fine-tuned 4 epochs, first 512 word pieces |
| C1 | T1 + kNN vote: similarity-weighted labels of the 20 nearest train documents |
| C2 | T1 + text model over the document and the text of its graph neighbours (no labels) |
| G1 | T1 + graph votes: mean labels of train neighbours per relation type |

**Certification.** Thresholds on the raw stacker score form a geometric grid fixed on
calib_fit; LTT with fixed-sequence testing and a one-sided Clopper–Pearson bound certifies
the most permissive threshold with risk ≤ α at δ = 0.1 on risk_cert.

**Provenance-aware aggregation.** A provenance group is one source however many members it
has. For kNN, candidates are collapsed to groups (group similarity = max over members, group
labels = mean over members) and the top-k groups vote; the candidate window widens until it
holds k groups (protocol 2.1). For the graph, a document's neighbours are collapsed to groups
and the hub-size cap counts groups. *Property:* exact copies that join their source's group
change neither vote (tested in `tests/test_provenance.py`).

**Protocol discipline.** Protocol 1.0 (H1) was frozen before the strong text model existed;
2.0 (H2) before the duplication experiment; 2.1 after analysing the 2.0 failure, with fresh
targets. Each version is a commit preceding its results.

## 4. H1: does the citation graph add accuracy beyond text?

Certified AutoRecall on risk_cert (δ = 0.1):

| System | α = 0.02 | α = 0.05 | α = 0.10 |
|---|---|---|---|
| T0 TF-IDF | 0 | 4.9% | 40.4% |
| T1 LEGAL-BERT | 0 | 28.2% | 50.5% |
| C1 + kNN | **8.8%** | **34.3%** | **56.3%** |
| C2 + neighbour text | 0 | 26.4% | 50.4% |
| G1 + graph | 0 | 30.6% | 55.4% |

![Automation frontier](../../research/reports/figures/automation_frontier.png)

The pre-registered rule (graph better than both controls, lower CI bound > 0) is not met:
G1 − C1 = −0.9 pp. The graph helps the strong text model (+4.9 pp over T1), but the same
label information is available from retrieval. A strong text model is the main lever:
moving from TF-IDF to LEGAL-BERT + kNN multiplies certified automation at α = 0.05 by seven.

## 5. H2: certified tagging under source duplication

*Scenario.* Policies are fitted and certified on the clean pool. At deployment, each target
document's nearest train document is copied m ∈ {1, 3, 10, 30, 100} times (exact, or with 1%
/ 5% of tokens deleted); copies inherit the source's labels and outgoing EUR-Lex links but
receive no incoming links. Stackers and thresholds stay fixed.

**Protocol 2.0** (500 targets, 361 sources): naive kNN realised risk on targets rises from
8.2% to 10.9% (m = 10) and 15.9% (m ≥ 30), above the certified 10% (H2a met). Provenance kNN
is exactly invariant up to m = 30 but drifts to 9.8% at m = 100 (H2b not met), because the
fixed candidate window was exhausted by copies of nearby sources. Clean cost is nil (H2c
met). Citation-graph votes move by at most 0.3 pp in every scenario.

**Protocol 2.1** (500 fresh targets disjoint from 2.0, adaptive window; confirmatory).
All four rules hold:

| Rule (m = 100 exact copies, α = 0.10) | Result |
|---|---|
| H2a naive kNN realised risk on targets | 8.3% → **16.3%** (95% CI 14.4–18.4%) |
| H2b provenance kNN risk change | **0.0 pp** (95% CI 0.0–0.0) |
| H2c clean AutoRecall, provenance − naive | +0.01 pp |
| H2d citation-graph risk change | −0.1 pp (95% CI −0.4 to +0.3) |

Naive kNN exceeds the certified level from m = 10 (11.6%). With 1% of tokens deleted,
provenance kNN stays within 0.1 pp of its clean risk at every m; with 5%, it degrades with
naive kNN (copies are not detected), while the graph does not move.

![Realised risk vs copies](../../research/reports/figures/risk_vs_copies.png)

**Limits of detection.** With 5% of tokens deleted, the MinHash Jaccard to the source drops
to 0.66 and only 2.9% of copies are attributed to their source; provenance kNN then behaves
like naive kNN. Citation links stay robust because they do not depend on detecting copies.

**Mislabelled copies** (copies carry another document's labels, m = 100, protocol 2.1):
naive kNN risk on targets rises to 15.7% while its AutoRecall falls from 56% to 24%;
provenance kNN keeps the risk at 7.6% with AutoRecall 52%; the graph is unaffected.

**Can a covariate-shift correction replace provenance?** (exploratory, not pre-registered;
`research/reports/WEIGHTED_CONFORMAL.md`). We re-certify C1 under the 2.1 scenario with
density-ratio weights in the style of Tibshirani et al. (2019). A gradient-boosting classifier
separates certification-time from deployment-time documents using vote and score descriptors.
Its odds weight the labelled certification set, clipped at 20, and the threshold is
re-certified with Kish's effective sample size. No new labels are used.

| Copies | Detector AUC | Clean τ | Weighted re-cert. | Oracle re-cert. (new labels) | Provenance kNN |
|---|---|---|---|---|---|
| 10 | 0.89 | 11.6% | 9.1% | 9.1% | 8.3% |
| 30 | 0.91 | 16.3% | 12.3% | 10.3% | 8.3% |

Weighting detects the shift and repairs moderate duplication, but not heavy duplication.
Copies change P(y | x): a concentrated vote produced by copies looks like consensus yet is
right less often. That violates the assumption under which reweighting is valid. Even
labelled re-certification controls the average risk, not the risk of the affected subgroup.
A first, weaker detector found no shift at all. Provenance-aware aggregation needs neither
labels nor a detector. Caveats: one scenario and one seed; Kish's effective sample size is a
heuristic, not a finite-sample weighted guarantee; the descriptors were designed knowing how
copies act, which favours the weighted method.

**Transfer to another language and catalog** (exploratory; service benchmark,
`services/core/reports/RUSLAWOD_BENCHMARK.md`). The same certification path runs in the
EviGraph Core service on RusLawOD (Saveliev & Kuchakov, 2024): 8,551 Russian federal acts
with the official 21-section classifier, a TF-IDF engine, and the 1,000 newest acts held out
as a later period. α = 10% certifies from about 500 reviewed acts and α = 5% from about 1,000.
In every certified configuration the realised risk on the later acts stayed below α (2.2–7.2%).

## 6. Methodological note: bootstrapping a certified quantity

Percentile bootstrap intervals for certified AutoRecall are skewed: point estimates sit near
the upper end (e.g. 55.4% with interval 48.9–56.3%). Under resampling, any spurious failure
on the threshold path stops the fixed sequence early, so resampled AutoRecall is biased down.
Protocol 2.x therefore evaluates realised risk at a fixed certified threshold.

## 7. Related work

*Distribution-free risk control.* LTT (Angelopoulos et al., 2025) and conformal risk control
(Angelopoulos et al., 2024) certify thresholds under exchangeability; selective
classification (Geifman & El-Yaniv, 2017) is the accuracy–coverage view of the same policy.
Weighted conformal prediction (Tibshirani et al., 2019) and non-exchangeable conformal
prediction (Barber et al., 2023) relax exchangeability under covariate shift or bounded
drift. Duplication of retrieval sources is a shift in P(y | x) for the retrieval features, so
these corrections do not apply directly (§5).

*Duplication.* MinHash resemblance (Broder, 1997) is the standard near-duplicate detector.
Deduplication improves language models and reduces train–test overlap (Lee et al., 2022). We
study duplication in the *retrieval pool* after certification, not in training data.

*Retrieval corruption.* Injecting a few crafted texts into a retrieval corpus can steer
retrieval-augmented generation (Zou et al., 2025). Our setting is benign: copies carry their
source's own labels. Even so, duplication alone breaks certified guarantees.

*Legal classification.* MultiEURLEX (Chalkidis et al., 2021), LexGLUE (Chalkidis et al., 2022)
and LEGAL-BERT (Chalkidis et al., 2020) are the benchmark and model base. Calibration of
neural scores (Guo et al., 2017) motivates certifying on raw scores rather than on
recalibrated ones. Provenance groups follow the W3C PROV-O notion of derivation (Lebo et al.,
2013). Evidence faithfulness for the product follows ERASER (DeYoung et al., 2020).

## 8. Limitations

One seed for LEGAL-BERT; Clopper–Pearson assumes independent pairs; LEGAL-BERT was
pre-trained on EUR-Lex text (no labels); copies are injected, not observed; provenance
detection is MinHash-based; final_test has not been opened.

## 9. Reproducibility

`make all` rebuilds data, splits and baselines; `evigraph-research strong-text`,
`compare`, `h2 --version 2.0|2.1` and `python -m evigraph_research.figures` reproduce every
number and figure. Protocol versions, results and code are separate commits in order.

## References

* Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I., & Lei, L. (2025). Learn then
  Test: Calibrating predictive algorithms to achieve risk control. *Annals of Applied
  Statistics*, 19(2), 1641–1662. doi:10.1214/24-AOAS1998. arXiv:2110.01052.
* Angelopoulos, A. N., Bates, S., Fisch, A., Lei, L., & Schuster, T. (2024). Conformal risk
  control. *ICLR 2024*. arXiv:2208.02814.
* Barber, R. F., Candès, E. J., Ramdas, A., & Tibshirani, R. J. (2023). Conformal prediction
  beyond exchangeability. *Annals of Statistics*, 51(2), 816–845. doi:10.1214/23-AOS2276.
* Broder, A. Z. (1997). On the resemblance and containment of documents. *Compression and
  Complexity of Sequences (SEQUENCES '97)*, 21–29.
* Chalkidis, I., Fergadiotis, M., Malakasiotis, P., Aletras, N., & Androutsopoulos, I. (2020).
  LEGAL-BERT: The Muppets straight out of Law School. *Findings of EMNLP 2020*, 2898–2904.
* Chalkidis, I., Fergadiotis, M., & Androutsopoulos, I. (2021). MultiEURLEX — A multi-lingual
  and multi-label legal document classification dataset for zero-shot cross-lingual transfer.
  *EMNLP 2021*, 6974–6996. arXiv:2109.00904.
* Chalkidis, I., Jana, A., Hartung, D., Bommarito, M., Androutsopoulos, I., Katz, D. M., &
  Aletras, N. (2022). LexGLUE: A benchmark dataset for legal language understanding in
  English. *ACL 2022*, 4310–4330.
* Clopper, C. J., & Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated
  in the case of the binomial. *Biometrika*, 26(4), 404–413.
* DeYoung, J., Jain, S., Rajani, N. F., Lehman, E., Xiong, C., Socher, R., & Wallace, B. C.
  (2020). ERASER: A benchmark to evaluate rationalized NLP models. *ACL 2020*, 4443–4458.
* Geifman, Y., & El-Yaniv, R. (2017). Selective classification for deep neural networks.
  *NeurIPS 2017*, 4878–4887.
* Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural
  networks. *ICML 2017*, PMLR 70, 1321–1330.
* Lebo, T., Sahoo, S., & McGuinness, D. (Eds.) (2013). PROV-O: The PROV Ontology. W3C
  Recommendation, 30 April 2013.
* Lee, K., Ippolito, D., Nystrom, A., Zhang, C., Eck, D., Callison-Burch, C., & Carlini, N.
  (2022). Deduplicating training data makes language models better. *ACL 2022*, 8424–8445.
* Saveliev, D., & Kuchakov, R. (2024). The Russian Legislative Corpus. arXiv:2406.04855.
* Tibshirani, R. J., Barber, R. F., Candès, E. J., & Ramdas, A. (2019). Conformal prediction
  under covariate shift. *NeurIPS 2019*, 2530–2540.
* Zou, W., Geng, R., Wang, B., & Jia, J. (2025). PoisonedRAG: Knowledge corruption attacks to
  retrieval-augmented generation of large language models. *USENIX Security 2025*.

Bibliographic details were checked against the publishers' pages (ACL Anthology, PMLR,
NeurIPS proceedings, project Euclid, W3C, arXiv) on 2026-10-08. The page ranges for Broder
(1997) and Geifman & El-Yaniv (2017) come from secondary indexes.
