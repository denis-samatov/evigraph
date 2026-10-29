# Acceptance boundaries after the 2026-10-29 audit corrections

No new experimental results are claimed. Protocol versions, parameters, historical reports,
final-test access log and figures remain unchanged. The abstract/README now state the same
independence/exchangeability limitation already discussed in the paper and protocol.

## Independent scientific qualification

1. Freeze a new external or later temporal corpus, provenance grouping, annotation rights,
   baselines and decision rules before examining final labels. Reused `final_test` in v4+
   is not an untouched confirmation; three seeds on one test set are training variability.
2. Treat Clopper–Pearson document-label independence as an assumption that is not generally
   satisfied. Report document/source-cluster empirical intervals and realised risk; do not
   claim these intervals prove the original pair-independent finite-sample guarantee.
   A cluster-aware risk bound requires independent statistical derivation/review.
3. Label v4.2 grouped-identical analysis post hoc. A many-distinct-LLM-paraphrase attack
   remains unexecuted; design it prospectively rather than extrapolating five paraphrases
   mirrored many times into a general poisoning defence.
4. Reproduce from immutable code/data/model/package identities under applicable licences;
   retain full commands, failures, fold manifests and new outputs in a separate results
   directory. Do not overwrite historical study outputs to imply a new replay.

## Local product, target infrastructure and external identity

The default supported scope is one trusted local operator. Host/Origin checks are browser
protections; they are not authentication or catalog/tenant authorization. Before remote
use, implement an approved identity/role/catalog policy, bind reviewer to the authenticated
subject, test forbidden read/review/release/certification operations and protect transport.
This IAM decision needs the target organization; no generic shared secret is presented as
complete multi-user authorization.

In separately authorized staging, not on an existing production database:

- Regenerate current execution locks with normal resolver tooling; triage advisory matches
  by runtime/research scope and repeat dependency scan after updates.
- Run research property tests, full Core PostgreSQL tests (including new local boundary
  tests), type/lint and Studio build from the supported lockfiles.
- Build/run the non-root image with a fresh disposable volume. Execute migration service
  once, verify API starts only on success and readiness becomes 503 during DB outage.
  Existing volumes need explicit backed-up ownership preparation for UID/GID10001.
- Back up/restore PostgreSQL and artifact files as one consistent release/certificate unit;
  verify release hashes, provenance groups, review revisions, audit history and suspension
  state before allowing auto-apply. Exercise concurrency/retry/idempotency after restore.
- Define latency, resource, availability and audit-lag objectives from target load and
  reviewed outcomes. Check drift and suspend auto-apply when appropriate; a certificate is
  not a substitute for observed deployment quality.

No services, Docker, database migration, external API, licensed-data download or model
training was performed by the offline patch. These prerequisites cannot be satisfied by
relabeling unit tests as production acceptance.
