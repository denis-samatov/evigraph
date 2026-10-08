# Protocol 1.0 results

Run date: 2026-10-08. Protocol: [`docs/PROTOCOL.md`](../../docs/PROTOCOL.md), frozen in commit
`c937f31` before these results existed. Machine-readable data: `comparison_v1.json`,
`strong_text.json`. `final_test` has not been opened (no `final_test_access.log`).

## Summary

1. **H1 decision: the graph adds no information beyond text.** The protocol rule requires the
   lower bound of the 95% interval to be above zero in all three contrasts. It is not met in
   any. The conclusion holds without intervals too: by point estimates the graph system is no
   better than retrieval of similar documents (−0.9 pp), and combining all features is worse
   than retrieval (−2.2 pp).
2. **The graph helps a strong text model, but retrieval without a graph gives the same.**
   Adding the graph to LEGAL-BERT raises AutoRecall at α = 0.10 from 50.5% to 55.4%.
   Retrieving the 20 nearest documents by TF-IDF gives 56.3%. Labels of linked acts carry
   signal, but almost all of it is available from textually similar documents.
3. **A strong text model greatly widens safe automation.** At α = 0.05 AutoRecall grows from
   4.9% (TF-IDF) to 28.2% (LEGAL-BERT) and 34.3% (LEGAL-BERT + kNN). The best system, C1, is
   the only one with a certified threshold at α = 0.02 (8.8% of assignments, realised risk
   1.4%).
4. **Methodological finding: bootstrap intervals for certified AutoRecall are biased
   downwards** (section 4). It does not affect the H1 conclusion, but the procedure must be
   replaced in the next protocol version.

## 1. Strong text model

LEGAL-BERT base (`nlpaueb/legal-bert-base-uncased`, 110M parameters), first 512 word pieces,
4 epochs, 6 h 11 min on Apple MPS.

| Epoch | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| mRP on the early-stopping subset (latest 5% of train) | 0.690 | 0.770 | 0.797 | **0.805** |

Epoch 4 is selected. Gains slowed down but did not stop: the model is probably not trained to
convergence.

## 2. Ranking quality

| System | mRP model_dev (OOF) | macro-F1 model_dev | mRP risk_cert | top-10 ECE risk_cert |
|---|---|---|---|---|
| T0_tfidf | 0.791 | 0.500 | 0.716 | 0.028 |
| T1_strong | 0.770 | 0.377 | 0.735 | 0.023 |
| C1_strong+knn | 0.792 | 0.431 | **0.754** | 0.021 |
| C2_strong+nbtext | 0.801 | 0.469 | 0.735 | 0.024 |
| G1_strong+graph | 0.789 | 0.424 | 0.751 | 0.022 |
| G2_strong+knn+nbtext+graph | **0.809** | 0.492 | 0.740 | 0.026 |

On model_dev LEGAL-BERT trails TF-IDF in mRP (0.770 vs 0.791) and clearly in macro-F1 (0.377
vs 0.500): 512 tokens lose the tail of long acts, which hurts rare concepts most. On the later
risk_cert the picture reverses (0.735 vs 0.716): the transformer is more robust to temporal
drift.

## 3. Certified automation on risk_cert

δ = 0.1; 2,659 documents; at α = 0.01 no system is certified.

| System | α = 0.02 | α = 0.05 | α = 0.10 | 95% CI (α = 0.10) | Realised risk (α = 0.10) | Auto tags per document | Documents fully correct |
|---|---|---|---|---|---|---|---|
| T0_tfidf | 0 | 4.9% | 40.4% | 36.6–41.8% | 9.4% | 2.21 | 3.1% |
| T1_strong | 0 | 28.2% | 50.5% | 46.3–51.5% | 9.2% | 2.76 | 9.0% |
| C1_strong+knn | **8.8%** | **34.3%** | **56.3%** | 55.2–57.4% | 8.6% | 3.05 | 11.1% |
| C2_strong+nbtext | 0 | 26.4% | 50.4% | 49.3–54.6% | 8.4% | 2.73 | 10.1% |
| G1_strong+graph | 0 | 30.6% | 55.4% | 48.9–56.3% | 9.6% | 3.03 | 11.2% |
| G2_strong+knn+nbtext+graph | 0 | 24.2% | 54.1% | 49.7–55.1% | 9.4% | 2.96 | 11.1% |

![Automation frontier](figures/automation_frontier.png)

## 4. Hypothesis H1

Primary metric: AutoRecall at α = 0.10; paired bootstrap over risk_cert documents, 1,000
resamples, certification repeated on each.

| Treatment − control | AutoRecall difference | 95% CI | 95% CI of mRP difference (model_dev) |
|---|---|---|---|
| G1_strong+graph − C1_strong+knn | −0.9 pp | −7.0 … −0.5 pp | −0.006 … 0.000 |
| G1_strong+graph − C2_strong+nbtext | +4.9 pp | −3.6 … +5.5 pp | −0.016 … −0.009 |
| G2_strong+knn+nbtext+graph − C1_strong+knn | −2.2 pp | −6.0 … −1.6 pp | +0.014 … +0.019 |

**Decision by the protocol rule — the graph adds information beyond text: no.**

**The intervals are biased downwards.** For most systems the point estimate sits near the upper
end of its interval: for G1 it is 55.4% with an interval of 48.9–56.3%. The likely cause is the
stopping rule of the certification. In a bootstrap resample, a spurious failure at any threshold
cuts the whole sequence short, so resampled AutoRecall is more often too low than too high. A
percentile interval for such a non-smooth quantity is not calibrated. The contrast intervals,
especially the "significantly negative" G1 − C1 and G2 − C1, should not be read literally. The
conclusion "the graph is no better than the control" also rests on point estimates, so it does
not depend on this issue. The next protocol version needs a different procedure, such as
comparing at a threshold certified on the full sample, or a subsampling bootstrap.

## 5. What this means for EviGraph

* **For the product, the graph is useful, but not for accuracy.** In this task automation
  quality is driven by a strong text model and retrieval of similar documents. The graph's
  value in the IDE is explainability (which acts are linked, what derives from what) and
  navigation, not AutoRecall gains.
* **For the paper, H1 in its current form is not supported on MultiEURLEX.** There are three
  honest directions:
  1. Features absent from both text and retrieval: relation type and direction over time,
     changes of an act's status (repealed, amended), a GNN over the typed graph — tested
     against C1 as the main control.
  2. A corpus where text is poorer and links are richer (short documents, support tickets,
     contracts with annexes).
  3. Reframing the contribution: not "the graph improves accuracy" but "the graph does not
     improve accuracy but makes decisions verifiable", which needs experiments with experts
     measuring their time. (Protocol 2.x took a fourth direction: robustness of guarantees.)
* **A strong text model is the main lever for automation.** Moving from TF-IDF to
  LEGAL-BERT + kNN multiplied certified automation at α = 0.05 by seven (4.9% → 34.3%).

## 6. Limitations

* One LEGAL-BERT seed, 4 epochs; the model is probably not fully trained.
* Bootstrap intervals are biased (section 4).
* The Clopper–Pearson bound assumes independent pairs.
* LEGAL-BERT was pre-trained on EUR-Lex texts, including all splits (without labels).
* The reference graph is not extended with model_dev and calib_fit labels.

## 7. Cost

| Stage | Time |
|---|---|
| LEGAL-BERT fine-tuning (4 epochs, MPS) | 6 h 11 min |
| C2 control: neighbour matrices + 127 models | ~3 min |
| C1 control: kNN for 9,900 documents | ~2 min |
| stackers, certification, bootstrap (6 systems × 1,000 resamples) | 26 s |
