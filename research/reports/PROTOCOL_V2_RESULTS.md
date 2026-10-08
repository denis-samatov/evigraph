# Protocol 2.0 results: source duplication (H2)

Run date: 2026-10-08. Protocol: [`docs/PROTOCOL.md`](../../docs/PROTOCOL.md), part 2,
registered in commit `ad7bcc0` before the run; the method is in the commit preceding the run.
Data: `h2_results.json`. 500 targeted `risk_cert` documents, 361 distinct sources.
`final_test` has not been opened.

## Decision by the protocol rules

| Rule | Value | Threshold | Met |
|---|---|---|---|
| H2a: C1 risk on targets at 100 exact copies | 15.9% (95% CI 14.3–17.9%) | lower bound > 10% | yes |
| H2b: change in C1p risk at 100 exact copies | +1.5 pp (95% CI +0.8…+2.2) | upper bound ≤ 1 pp | **no** |
| H2c: AutoRecall C1p − C1 on the clean pool | +0.01 pp (56.32% vs 56.31%) | ≥ −2 pp | yes |

**H2 is not supported under protocol 2.0**: the invariance rule fails.

## Realised risk on targeted documents (α = 0.10, exact copies)

| Copies per source | 0 | 1 | 3 | 10 | 30 | 100 |
|---|---|---|---|---|---|---|
| T1 (no pool) | 9.1% | 9.1% | 9.1% | 9.1% | 9.1% | 9.1% |
| C1 (naive kNN) | 8.2% | 8.6% | 8.9% | **10.9%** | **15.9%** | **15.9%** |
| C1p (provenance kNN) | 8.3% | 8.3% | 8.3% | 8.3% | 8.3% | **9.8%** |
| G1 (naive graph) | 9.0% | 9.0% | 8.8% | 8.8% | 8.9% | 8.9% |
| G1p (provenance graph) | 8.9% | 8.9% | 8.9% | 8.9% | 8.9% | 8.9% |

For C1 at m ≥ 30 all 20 neighbour slots are taken by copies, so the growth stops. Over all of
`risk_cert`, C1's risk at 30 copies is 14.1%.

## Why H2b fails

C1p is exactly invariant up to and including 30 copies and breaks only at 100. The cause is
the window of 200 candidates: when several sources near a target have 100 copies each, the
copies fill the window and fewer than 20 groups remain after collapsing. The principle holds,
but the implementation uses a fixed candidate window that should widen until it holds k
distinct groups. The fix is tested in protocol 2.1 on fresh targets.

## Secondary results (no decision rule)

**Noise in copies.** With 1% of tokens deleted, MinHash attributes 98.8% of copies to their
source's group, and C1p behaves as with exact copies. With 5%, only 2.9% (mean Jaccard
0.66 < 0.8): C1p becomes naive and its risk at 100 copies is 14.8%. Provenance awareness works
only when a copy can be recognised.

**The citation graph is robust without provenance.** G1's risk moves by at most 0.3 pp in every
scenario, including 5% noise. EUR-Lex links point to a specific identifier, and a copy with a new
identifier receives no incoming links; it can only act through shared external acts.

**Copies with another document's labels** (100 per source):

| System | Risk on targets | AutoRecall on targets |
|---|---|---|
| C1 | 7.5% → **14.1%** | 56.4% → **21.7%** |
| C1p | 8.3% → 8.9% | 56.5% → 43.5% |
| G1 | 9.0% → 8.9% | 55.9% → 55.2% |

Naive retrieval loses both accuracy and automation; provenance retrieval keeps the guarantee
but loses part of the automation (one group out of 20 votes wrongly); the graph is unaffected.

## Takeaways

1. **A certified guarantee does not survive copies entering the pool** if the system relies on
   retrieval of similar documents: at 10 copies the risk exceeds α, at 30 it is almost double.
2. **The citation graph provides robustness, not accuracy.** In version 1.0 the graph added no
   accuracy beyond retrieval, but here it is the only pool-based system that ignores both exact
   and noisy copies.
3. **Provenance-aware retrieval is free on clean data** and protects against recognisable
   copies; its limit is the quality of recognition.
