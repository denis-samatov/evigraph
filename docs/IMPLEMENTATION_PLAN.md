# EviGraph Core — implementation plan

Goal: turn the research results into a service that is useful from day one in
**suggest-and-review** mode and can switch to **certified auto-apply** per catalog once enough
reviewed data exists, with monitoring that suspends auto-apply when the guarantee no longer
holds.

Research decisions carried over (see `research/reports/`):

* tagging score = stacker over a text model and **provenance-aware** kNN over reviewed
  documents (naive kNN breaks the guarantee under copies; provenance kNN does not);
* auto-apply only through a threshold certified with Learn-then-Test (Clopper–Pearson,
  fixed-sequence testing on a geometric grid);
* provenance is recorded at ingestion: exact hash, MinHash near-duplicate groups, and source
  identifiers (source system + source id), because MinHash misses paraphrased copies;
* nothing is certified on data the policy was tuned on; certification data are split by
  provenance group.

## Stack

FastAPI + Pydantic (strict), SQLAlchemy 2.0 + Alembic, PostgreSQL 17 (pgvector image for
deployment), scikit-learn/scipy for the engine. Model artifacts on the filesystem behind an
interface (S3 later). Package: `services/core`.

## Milestones

| # | Milestone | Done when | Status |
|---|---|---|---|
| M1 | Core skeleton: settings, DB schema and migration, health endpoint, test harness on a local PostgreSQL cluster | `pytest` runs against PostgreSQL; schema created by Alembic | done |
| M2 | Projects, catalogs, documents: immutable document versions with canonical text, exact and near-duplicate provenance groups, source identifiers | re-ingesting a copy joins the source's provenance group; tests cover exact, near and source-id copies | done |
| M3 | Tagging engine and suggestions: training from reviewed data, provenance-aware kNN, stacker, release manifest; `POST /documents/{id}/suggestions` returns ranked concepts with supporting documents | suggestions are invariant to copies of reviewed documents (test) | done |
| M4 | Review commands: accept, reject, add, withdraw; optimistic concurrency (`expected_revision`) and idempotency keys; review queue | concurrent conflicting reviews are rejected; replays are idempotent | done |
| M5 | Certification: dataset from fully reviewed documents, provenance-group split, LTT per catalog, certification records, sample-size planner; auto-apply only with an active certification | auto-apply refused without certification; planner matches the binomial bound | done |
| M6 | Monitoring: audit sampling of auto-applied tags, confidence bounds on the realised risk, automatic suspension when the lower bound exceeds α | an audit stream with risk above α suspends auto-apply (test) | done — no provenance-flood alarm: the kNN pool is frozen inside a release and every retrained release needs a new certification, so post-certification copies cannot change a certified model |
| M7 | Deployment: Docker Compose (API, PostgreSQL), demo on MultiEURLEX | `docker compose up` serves the demo catalog | in progress |

**Demo on real data (M7).** `evigraph-core demo-multieurlex` on 2,000 reviewed MultiEURLEX
documents certifies τ = 0.906 at α = 10% (upper bound 8.5%) and, on 200 later documents,
auto-applies 221 tags with a realised error rate of 6.3%.

The IDE (Theia + GLSP) and evidence extraction with an LLM come after M7; the API is designed
so that both can be added without changing the review and certification model.
