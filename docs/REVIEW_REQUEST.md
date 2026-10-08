# Request for external review

Thank you for looking at this project. It takes about 30–45 minutes to read the essentials.
Critical comments are the most useful kind.

## What it is, in five sentences

EviGraph studies **certified document tagging**: a tag from a controlled vocabulary is
applied without review only when a Learn-then-Test (LTT) certified threshold guarantees,
with probability 1 − δ, that the error rate among automatic tags is at most α. On MultiEURLEX
with 274k EUR-Lex act-to-act relations, the citation graph adds no accuracy beyond retrieval
of similar documents. Retrieval-based tagging, however, **loses its guarantee when copies of
sources enter the collection after certification**: risk rises from 8.3% to 16.3% at a
certified 10%. Aggregating evidence by provenance group restores the guarantee for detectable
copies, and identifier-based citation links are robust by construction. All experiments were
pre-registered; the final test split is opened once, in protocol 3.0.

## What to read

1. [`docs/paper/draft.md`](paper/draft.md) — the paper draft (≈ 10 min).
2. [`docs/PROTOCOL.md`](PROTOCOL.md) — pre-registered protocols 1.0 → 3.0 and their history.
3. Results: [`PROTOCOL_V1_RESULTS.md`](../research/reports/PROTOCOL_V1_RESULTS.md),
   [`PROTOCOL_V21_RESULTS.md`](../research/reports/PROTOCOL_V21_RESULTS.md),
   [`WEIGHTED_CONFORMAL.md`](../research/reports/WEIGHTED_CONFORMAL.md).
4. Optional — the service built on the results:
   [`services/core/README.md`](../services/core/README.md) and the Russian-legislation
   benchmark [`RUSLAWOD_BENCHMARK.md`](../services/core/reports/RUSLAWOD_BENCHMARK.md).

## Questions we would most like answered

**Statistics (conformal / risk control)**

1. Certification uses a one-sided Clopper–Pearson bound over (document, concept) pairs, which
   are not independent within a document. Is the guarantee still meaningful? Would you
   require a document-level loss (e.g. per-document error rate with a Hoeffding–Bentkus bound)
   instead?
2. We evaluate realised risk at a fixed certified threshold with a document bootstrap and
   report that bootstrapping the *certified* AutoRecall is biased downward. Is this known, and
   is our workaround sound?
3. Is the comparison with weighted conformal re-certification (Tibshirani et al., 2019) fair,
   and which non-exchangeable method would you compare against (e.g. Barber et al., 2023)?

**Experimental design**

4. Copies are injected, not observed. Is the scenario — the nearest training document of a
   target copied m times after certification — a convincing model of real duplication
   (templated acts, mirrors, re-publication)? Which real-world dataset with natural
   duplication over time would you use?
5. With exact copies, provenance-aware aggregation is invariant by construction. Is the
   contribution then the *measurement* of the failure and the boundary of detection
   (5% token noise defeats MinHash), or is something more needed?
6. Is the negative H1 result (graph ≈ retrieval) interesting enough to report, given the
   controls used?

**Positioning**

7. Which venue fits: a workshop on distribution-free uncertainty or reliable ML, a legal-NLP
   workshop, or a main track after more datasets? What related work is missing?

## Practical details

* Code: Apache-2.0; data are not redistributed (MultiEURLEX CC BY-SA, RusLawOD CC BY-NC).
* Reproduction: `cd research && make dev && make all` (CPU) plus LEGAL-BERT fine-tuning
  (≈ 6 h per seed on Apple MPS).
* An automated critical review was run before this request; its findings and our responses
  are in [`REVIEW_LOG.md`](REVIEW_LOG.md). It does not replace a human expert's opinion.

Comments can be left as GitHub issues, as review comments on any file, or by email to the
author.
