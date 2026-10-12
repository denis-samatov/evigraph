# Protocol 4.2 results: LLM-paraphrased copies (H6)

Run on 2026-10-12 with three LEGAL-BERT seeds. The protocol was registered in commit `d141c15`
(part 7 of [`PROTOCOL.md`](../../docs/PROTOCOL.md)). It was amended in `931e549` before any
paraphrase was generated: DeepSeek reasoning was disabled after a smoke test. Data:
`protocol_v42_results.json` (registered run), `protocol_v42_grouped_identical.json`
(post-hoc variant). Paraphrases are cached in `data/cache/paraphrase/deepseek-flash.jsonl`.

**Generation.** `deepseek-flash`, temperature 1.0, reasoning disabled. 3,440 calls (344
sources × 2 levels × 5 variants), none failed, all finished with `stop`. 3.0M input and 2.8M
output tokens; about $2–4 at the published rates, depending on the peak tariff.

**Built-in check.** The exact-copy scenario reproduces protocol 4.0 on the same targets:
naive kNN targeted risk 20.64%.

| Rule | Result |
|---|---|
| H6: full paraphrases evade every attribution method (< 50%) and raise naive kNN risk (lower CI > 0) | **met** in 3 of 3 seeds |

## Attribution and similarity

| Scenario | Median cosine to source | MinHash | Cosine | Containment |
|---|---|---|---|---|
| exact | 1.00 | 100% | 100% | 100% |
| truncated to 6,000 characters | 1.00 | 69% | 69% | 99% |
| paraphrase, light | 0.97 | 64% | 67% | 77% |
| paraphrase, full | 0.74 | 11% | 13% | 15% |

Attribution means the share of copies that joined their source's provenance group. Truncation alone
defeats MinHash and cosine for long sources; containment handles it. A full LLM paraphrase
defeats all three methods.

## Change in targeted risk, α = 0.10 (100 copies per source)

Seeds 0 / 1 / 2. The clean C1 targeted risk is 13.4–14.2%.

| Scenario | Naive kNN (harm) | Provenance kNN, containment: registered run | Provenance kNN, containment: identical copies grouped (post hoc) |
|---|---|---|---|
| exact | +7.2 / +6.7 / +7.5 pp | 0.0 | 0.0 |
| truncated | +6.7 / +6.5 / +7.1 pp | +0.1 / 0.0 / +0.2 pp | 0.0 / 0.0 / 0.0 pp |
| paraphrase, light | +6.2 / +6.3 / +6.9 pp | +3.0 / +2.6 / +3.9 pp | +0.2 / +0.7 / +0.7 pp |
| paraphrase, full | +5.3 / +5.2 / +5.9 pp | +4.3 / +4.2 / +4.8 pp | −0.2 / +0.3 / +0.6 pp |

In the grouped variant the 95% upper bounds reach at most +1.7 pp (full) and +1.6 pp
(light). MinHash and cosine attribution give similar numbers in both runs.

## Findings

1. **LLM paraphrases are a realistic way into the danger zone** (H6). A thorough paraphrase
   keeps the meaning and legal references but leaves only 11–15% of copies recognisable. Naive
   kNN's targeted risk rises by +5 to +6 pp, almost as much as with exact copies.
2. **What hurts provenance-aware kNN is the number of distinct undetected texts, not the
   number of copies.** In the registered run, each of the five paraphrases of a source is
   copied 20 times and every copy is treated as its own source, which allows up to 100 extra
   votes. A pipeline that groups exact duplicates, as EviGraph Core does, collapses them into at
   most five groups per source. The harm then disappears (−0.2 to +0.7 pp). This variant was
   chosen after seeing the registered results and is post hoc.
3. **The remaining threat is many distinct paraphrases.** An adversary who generates a new
   paraphrase for every copy defeats grouping. In protocol 4.0 every randomly edited copy was
   unique, and the harm persisted. LLM paraphrases make this cheap: about $0.001 per copy here.
   This scenario was not run (≈ 34,000 calls).

## What this means

* For accidental duplication — mirrors, re-publications, consolidated texts, light
  rewording — the defences in EviGraph Core suffice: identical texts, near copies,
  containment and provenance-aware aggregation.
* For deliberate poisoning with many unique paraphrases, text-based attribution is not
  enough. Defences must limit how much of the vote any one cluster of similar documents can
  hold. Candidates are a cap per semantic cluster, source identifiers and trust, or retrieval
  that is certified robust to insertions (Jia et al., 2022; Xiang et al., 2024). They are not
  evaluated here.
