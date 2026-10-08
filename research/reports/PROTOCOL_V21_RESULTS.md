# Protocol 2.1 results: confirming H2

Run date: 2026-10-08. Protocol: [`docs/PROTOCOL.md`](../../docs/PROTOCOL.md), part 3,
registered in the commit preceding the run and after the 2.0 results. Data:
`h2_results_v21.json`. 500 **fresh** targeted `risk_cert` documents (overlap with the 2.0
targets: 0 documents), 361 distinct sources. `final_test` has not been opened.

## Decision by the protocol rules

| Rule | Value | Threshold | Met |
|---|---|---|---|
| H2a: naive kNN risk on targets, 100 exact copies | **16.3%** (95% CI 14.4–18.4%) | lower bound > 10% | yes |
| H2b: change in provenance kNN risk | **0.0 pp** (95% CI 0.0…0.0) | upper bound ≤ 1 pp | yes |
| H2c: AutoRecall C1p − C1 on the clean pool | +0.01 pp (56.32% vs 56.31%) | ≥ −2 pp | yes |
| H2d: change in citation-graph risk | −0.1 pp (95% CI −0.4…+0.3) | upper bound ≤ 1 pp | yes |

**H2 is supported**; robustness of the citation graph (H2d) is confirmed separately.

## Realised risk on targeted documents (α = 0.10)

| Copies per source | 0 | 1 | 3 | 10 | 30 | 100 |
|---|---|---|---|---|---|---|
| **Exact copies** | | | | | | |
| C1 (naive kNN) | 8.3% | 8.3% | 9.3% | **11.6%** | **16.3%** | **16.3%** |
| C1p (provenance kNN) | 8.3% | 8.3% | 8.3% | 8.3% | 8.3% | 8.3% |
| G1 (naive graph) | 9.4% | 9.4% | 9.4% | 9.3% | 9.4% | 9.3% |
| **1% of tokens deleted** | | | | | | |
| C1 | 8.3% | 8.3% | 9.3% | 11.4% | 15.6% | 15.7% |
| C1p | 8.3% | 8.4% | 8.4% | 8.4% | 8.3% | 8.4% |
| **5% of tokens deleted** | | | | | | |
| C1 | 8.3% | 8.3% | 9.4% | 11.2% | 14.8% | 15.2% |
| C1p | 8.3% | 8.4% | 9.6% | 11.0% | 14.4% | 15.1% |
| G1 | 9.4% | 9.4% | 9.4% | 9.3% | 9.4% | 9.3% |

The no-pool control (T1) is at 8.5% on these targets in every scenario.

![Realised risk vs copies](figures/risk_vs_copies.png)

**MinHash copy recognition** (Jaccard threshold 0.8): exact — 100%, 1% noise — 98.6%,
5% noise — 2.9% (mean Jaccard 0.66).

## Copies with another document's labels (100 per source)

| System | Risk on targets | AutoRecall on targets |
|---|---|---|
| C1 | 8.3% → **15.7%** | 55.9% → **23.7%** |
| C1p | 8.3% → 7.6% | 55.9% → 51.6% |
| G1 | 9.4% → 9.3% | 55.1% → 54.9% |

The adaptive window also improved this scenario: in 2.0 C1p kept the guarantee at the cost of
AutoRecall falling to 43.5%, in 2.1 only to 51.6%.

## What is confirmed

1. **Retrieval of similar documents breaks the certified guarantee when copies enter the
   collection.** Risk exceeds α at 10 copies and almost doubles at 30.
2. **Provenance-aware aggregation restores the guarantee** for copies that can be recognised
   (exact and 1% noise) and costs nothing on clean data.
3. **The citation graph is robust with no protection at all:** a copy with a new identifier
   receives no incoming links and so cannot become a "neighbour" of a new document. It is the
   only pool-based system robust to copies that MinHash fails to recognise.
4. **Limit:** at 5% noise copies are not recognised and the retrieval defence fails.
   Robustness to paraphrased copies needs stronger provenance recognition, or reliance on
   identifiers as in the graph.
