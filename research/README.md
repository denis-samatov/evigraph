# EviGraph research code

Everything needed to reproduce the study, from raw data to paper figures:

1. MultiEURLEX (English, EuroVoc `level_2`, 127 concepts) with original dates and CELEX ids;
2. act-to-act relations from EUR-Lex Cellar (`cites`, `amends`, `repeals`, `based_on`, …);
3. exact, near and template duplicates;
4. a grouped five-way split and its manifest;
5. the graph go/no-go report: coverage, label homophily, neighbour-vote signal;
6. baselines, the strong text model (LEGAL-BERT), retrieval and graph features, stackers,
   isotonic calibration and Learn-then-Test certification (Clopper–Pearson);
7. protocol runners: H1 (`compare`) and H2 (`h2 --version 2.0|2.1`);
8. provenance-aware aggregation for kNN and graph votes.

Results and conclusions: [`reports/`](reports) — start with
[`PROTOCOL_V21_RESULTS.md`](reports/PROTOCOL_V21_RESULTS.md) and
[`PROTOCOL_V1_RESULTS.md`](reports/PROTOCOL_V1_RESULTS.md); the first exploratory pass is
[`SPIKE_REPORT.md`](reports/SPIKE_REPORT.md). The protocol is in
[`../docs/PROTOCOL.md`](../docs/PROTOCOL.md).

## Running

```bash
make dev        # dependencies (uv)
make all        # download → prepare → cellar → dedup → splits → graph → baseline
make test lint
```

Then, in order:

```bash
uv run evigraph-research strong-text          # LEGAL-BERT fine-tuning, ~6 h on Apple MPS
uv run evigraph-research compare              # protocol 1.0 (H1)
uv run evigraph-research h2 --version 2.1     # protocol 2.1 (H2); 2.0 is also reproducible
uv run python -m evigraph_research.figures h2_results_v21.json
```

`make all` takes about 12 minutes on a laptop (12 cores, 16 GB), mostly the download:

| Step | What it does | Time |
|---|---|---|
| `download` | 2.77 GB archive from Hugging Face (`coastalcph/multi_eurlex`), sha256 checked | ~5 min |
| `prepare` | English text + level 1–3 labels → `data/interim/corpus_en.parquet` | ~1.5 min |
| `cellar` | 325 SPARQL queries of 200 CELEX ids, cached in `data/cache/cellar/` | ~3.5 min |
| `dedup` | MinHash LSH over word 5-grams, threshold 0.9 | ~25 s |
| `baseline` | TF-IDF, 127 models, stackers, certification; see `reports/baseline.json` → `cost` | ~1.5 min |

`dedup`, `baseline`, `compare` and `h2` use process pools. Inside a sandbox that forbids them,
`dedup` falls back to a single process; the others must run outside the sandbox. Model weights
are downloaded from Hugging Face; set `HF_HUB_DISABLE_XET=1` if the Xet transfer client cannot
reach its servers through a proxy.

## Splits

| Split | Source | Purpose |
|---|---|---|
| `train` | official train, up to 2007-10-29 | model fitting; the only labels in the reference graph |
| `model_dev` | official train, latest ~5,000 | feature and hyper-parameter choice, stackers |
| `calib_fit` | official dev, half of the groups | calibrator and threshold grid |
| `risk_cert` | official dev, the other half | policy certification |
| `final_test` | official test | **sealed** until the system is frozen |
| `excluded_overlap` | 102 documents | late members of early groups, excluded to keep chronology |

A split group is a connected component over exact copies, near copies (Jaccard ≥ 0.9) and
`corrects` relations. Manifest: `data/interim/split_manifest.parquet`; summary and sha256 in
`reports/split_manifest.json`.

## Leakage rules

* Model inputs are text only. EuroVoc, `subject-matter` and `directory-code` from Cellar never
  enter the features: only act-to-act relations are kept (the object must have a CELEX id).
* Graph features use `train` labels only; a document's own labels never take part.
* `final_test` is not tokenised, vectorised or evaluated; opening it requires
  `EVIGRAPH_OPEN_FINAL_TEST=1` and is logged.
