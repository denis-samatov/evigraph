# EviGraph Core

The service that turns the research results into a working tagging workflow: documents are
ingested with provenance, an engine suggests concepts with supporting evidence, experts review
them, and once enough reviewed data exists a threshold is **certified** so that confident tags
can be applied automatically — with audit-based monitoring that switches auto-apply off when
the guarantee no longer holds.

## Workflow

1. **Ingest.** Every document version is immutable and joins a *provenance group*: same
   source identifier, identical text, or a near copy (MinHash LSH, Jaccard ≥ 0.8). Copies count
   as one source wherever evidence is aggregated.
2. **Suggest and review** (works from day one). Without reviewed data a cold-start release
   ranks concepts by their label and definition. Experts accept, reject or add concepts and
   mark a document as fully reviewed; only fully reviewed documents provide gold labels.
3. **Train.** A release combines per-concept text models, provenance-aware kNN over reviewed
   documents and a stacker trained on out-of-fold features. 30% of provenance groups are held
   out from training for certification.
4. **Certify.** Learn-then-Test on the held-out documents finds the most permissive threshold
   whose error rate among auto-applied tags is ≤ α with probability ≥ 1 − δ. The certification
   belongs to that release; retraining requires a new certification.
5. **Auto-apply and monitor.** Suggestions above the certified threshold are applied
   automatically (`decision: auto_applied`); a share of them goes to expert audit. When the
   lower confidence bound of the audited error rate exceeds α, the certification is suspended
   and everything goes back to review.

## Demo on real data

`evigraph-core demo-multieurlex` runs the whole workflow on MultiEURLEX (127 EuroVoc concepts;
the corpus is built by `research/`). With 2,000 reviewed documents (1,377 for training in 1,305
provenance groups, 623 held out):

| | |
|---|---|
| Certified threshold at α = 10%, δ = 0.1 | τ = 0.906; upper bound of risk 8.5%; 26.7% of tags automated on held-out data |
| 200 new documents from a later period | top-1 suggestion correct 83%; 221 tags auto-applied with a **realised error rate of 6.3%**; 21% of all correct tags automated |
| Runtime on a laptop | 76 s end to end |

**Russian legislation (RusLawOD, 21 classifier sections, evaluation on acts from 2023–2026):**
auto-apply certifies at α = 10% from ~500 reviewed documents and at α = 5% from ~1,000; with
4,000 reviewed documents 46% of tags are automated at α = 10% with a realised error rate of
6.1% on later acts. Details: [`reports/RUSLAWOD_BENCHMARK.md`](reports/RUSLAWOD_BENCHMARK.md).

## Running

```bash
scripts/dev_db.sh start                       # local PostgreSQL 17 on 127.0.0.1:54329
uv run evigraph-core migrate
uv run evigraph-core serve                    # http://127.0.0.1:8000/docs
uv run pytest -q                              # tests run on a throw-away database
```

Or with Docker, from the repository root: `docker compose up --build` (set `EVIGRAPH_PORT` if
port 8000 is taken).

Configuration is read from `EVIGRAPH_*` environment variables (see `settings.py`), e.g.
`EVIGRAPH_DATABASE_URL`, `EVIGRAPH_ARTIFACT_DIR`, `EVIGRAPH_AUDIT_RATE`.

## API

| Method and path | Purpose |
|---|---|
| `POST /projects` | create a project |
| `POST /projects/{id}/catalogs`, `POST /catalogs/{id}/versions`, `POST /catalog-versions/{id}/publish` | versioned catalogs of concepts |
| `POST /projects/{id}/documents`, `POST /documents/{id}/versions` | ingest with provenance |
| `POST /catalog-versions/{id}/releases` | train and activate a release |
| `POST /document-versions/{id}/suggestions` | ranked concepts with supporting reviewed documents and a decision |
| `GET /assertions/{id}/evidence` | exact quotes (code-point offsets, hash-verified) with a deletion-based faithfulness score |
| `GET /catalog-versions/{id}/review-queue` | documents with undecided suggestions, most uncertain first |
| `POST /assertions/{id}/review` | accept / reject / withdraw (`expected_revision`, `idempotency_key`) |
| `POST /document-versions/{id}/assertions` | add a concept the engine missed |
| `POST /document-versions/{id}/review-completions` | mark a document fully reviewed |
| `POST /releases/{id}/certifications` | certify a release at α, δ |
| `GET /certifications/{id}/monitor` | audit statistics; suspends on evidence of violation |
| `GET /planning/certification` | reviewed documents needed for a certification |

## Guarantees and their limits

* The guarantee is **marginal over documents like the certification data**. It holds only while
  incoming documents resemble the reviewed ones; audit monitoring is the safeguard against drift.
* Certification uses reviewed documents; if experts were influenced by earlier suggestions
  (anchoring), gold labels and therefore the guarantee inherit that bias.
* The Clopper–Pearson bound treats (document, concept) pairs as independent.
* MinHash does not recognise paraphrased copies; source identifiers should be supplied at
  ingestion wherever the source system has them.

## Not implemented yet

Authentication and per-project access control, background workers for training (training
runs inside the request), and LLM-based evidence extraction (quotes are currently selected by
the engine's own passage contributions).
