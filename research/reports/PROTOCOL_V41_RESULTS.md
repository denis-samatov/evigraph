# Protocol 4.1 results: rolling re-certification under drift (H5)

Run on 2026-10-12 with three LEGAL-BERT seeds. The protocol was registered in commit
`43a478c` (part 6 of [`PROTOCOL.md`](../../docs/PROTOCOL.md)) before the run. `final_test` was
opened once, as logged; its labels had been seen in protocols 3.0 and 4.0. Data:
`protocol_v41_results.json`.

**Built-in check.** The protocol 4.0 preparation was refactored into `v4.prepare`. Recomputing
H4 from it reproduces the stored protocol 4.0 results exactly.

**Setting.** Six evaluation quarters, 2013Q4–2015Q1 (461–739 acts each). For each quarter, a
threshold is certified on acts published before it and applied to the quarter's acts. The
one-off scheme is certified on the 1,464 acts published before 2013-10-01.

| Rule | Result |
|---|---|
| H5: C1, α = 0.05, rolling 6-month pooled realised risk ≤ α | **met** in 3 of 3 seeds (4.06–4.19%) |

**Caveat on the rule.** At α = 0.05, the original certificate also has a pooled risk below
α over these quarters (4.4–5.0%). H5 therefore shows that rolling re-certification keeps the
guarantee, not that only it does. The differences between schemes show in the margin and in
the quarters above α (tables below).

## C1 (LEGAL-BERT + kNN): pooled over six quarters

Pooled realised risk / pooled AutoRecall / quarters above α (of 6); seeds 0, 1, 2.

**α = 0.10**

| Scheme | Seed 0 | Seed 1 | Seed 2 |
|---|---|---|---|
| original (2010–2012) | 12.1% / 47% / **6** | 12.1% / 46% / **6** | 12.1% / 48% / **6** |
| one-off (before 2013Q4) | 9.3% / 37% / 1 | 9.0% / 38% / 1 | 8.4% / 37% / 0 |
| rolling 6 months | 8.6% / 36% / 0 | 8.5% / 38% / 1 | 8.4% / 37% / 0 |
| rolling 12 months | 8.9% / 36% / 1 | 9.0% / 38% / 1 | 8.4% / 37% / 0 |
| rolling 6 months, 500 sampled | 8.3% / 35% / 0.3 | 8.2% / 37% / 0.8 | 8.4% / 37% / 0.4 |

**α = 0.05**

| Scheme | Seed 0 | Seed 1 | Seed 2 |
|---|---|---|---|
| original (2010–2012) | 4.4% / 26% / 2 | 4.6% / 26% / 4 | 5.0% / 26% / 4 |
| one-off (before 2013Q4) | 5.4% / 29% / 4 | 4.6% / 26% / 4 | 5.0% / 26% / 4 |
| rolling 6 months | **4.2%** / 25% / 1 | **4.1%** / 25% / 1 | **4.1%** / 24% / 2 |
| rolling 12 months | 4.9% / 27% / 2 | 4.4% / 26% / 3 | 4.6% / 25% / 2 |
| rolling 6 months, 500 sampled | 3.8% / 22% / 0.6 | 3.8% / 22% / 1.0 | 3.8% / 20% / 1.0 |

For the sampled scheme the values are means over 20 draws. With 500 acts, no threshold is
certified at α = 0.05 in 0.25–0.55 quarters on average, and nothing is auto-applied there.

## Findings

1. **At α = 0.10 the original certificate fails in every quarter** (10–13% per quarter, all
   seeds). Any re-certification on acts from 2012–2015 fixes it: pooled risk 8.2–9.3%, with at
   most one quarter above α. Automation falls from about 47% to 36–38%.
2. **At α = 0.05 recency matters.** The rolling 6-month scheme has the lowest pooled risk among
   the schemes that review every act (4.1–4.2%) and the fewest quarters above α (1–2 of 6). The
   one-off and the original certificates exceed α in 2–4 quarters, and so does the 12-month
   window (2–3 quarters). Its AutoRecall stays close to the original (24–25% vs 26%).
3. **Quarterly exceedances do not vanish.** Even rolling 6-month certification exceeds 5% in
   one or two quarters of six, more often than δ = 0.1 would allow if quarters were
   exchangeable with their windows. Part of this is sampling noise in quarters of about 500
   acts; part is drift within six months.
4. **An audit budget of 500 acts per quarter** keeps the pooled risk lowest (3.8%), but it is
   conservative. It automates less (20–22%), and at α = 0.05 some quarters get no certified
   threshold at all.
5. **T1 (LEGAL-BERT alone)** shows the same pattern at α = 0.10 (original 10.7–11.3%,
   re-certified 6.8–8.9%). At α = 0.05 its original certificate is already conservative
   (3.5–3.6%).

## Operational reading

For a deployed tagger under drift: re-certify every quarter on the last six months of
reviewed documents. At α = 0.10 this keeps the guarantee with margin. At α = 0.05 it keeps the
pooled risk below α but not every quarter. A tight α needs a buffer, for example certifying at
a slightly lower α. It also needs per-period monitoring, which EviGraph Core's audit
suspension provides.
