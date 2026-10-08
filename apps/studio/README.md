# EviGraph Studio

The IDE of EviGraph: an [Eclipse Theia](https://theia-ide.org) application with an
[Eclipse GLSP](https://eclipse.dev/glsp/) diagram, working on top of the EviGraph Core API
(`services/core`). Built from the GLSP `node-json-theia` project template (see
`TEMPLATE_ORIGIN`); template-derived files keep their original license headers.

![Review editor: an act of the State Duma (2026) with suggested classifier sections, the certified
policy chip, and the evidence quotes for section 080 highlighted](../../docs/images/studio-review.jpg)

![Local graph: the document, its concepts (✓ accepted, auto applied) and the reviewed documents
supporting them](../../docs/images/studio-graph.jpg)

## What it does

* **EviGraph panel** (left): project → published catalog version → documents; a ×N badge marks
  documents that share a provenance group with others.
* **Review editor** (main area), one per document version:
  * the canonical text; selecting a suggestion highlights its evidence quotes (offsets come from
    Core in Unicode code points and are converted to UTF-16 in the browser);
  * suggestions with score, the decision of the active policy (`auto` under a certified
    threshold, `review` otherwise) and the review state;
  * accept / reject / withdraw (sent with `expected_revision`, so a concurrent change by another
    expert is reported instead of overwritten), add a missed concept, complete the review;
  * a header chip shows whether auto-apply is certified (α, δ) for the active release.
* **Local graph** (`Open graph`): a read-only GLSP diagram of the document, its strongest
  concepts (✓ accepted, ✕ rejected, `auto` auto-applied), the reviewed documents that support
  them and the other members of its provenance group. Moving nodes changes nothing in Core:
  domain changes only happen through review commands.

The terminal and extension installation are not included (MVP security decision).

Known limitation: evidence quotes are passages ranked by their contribution to the concept;
short heading-like lines can rank high (e.g. "Рекомендовать Правительству Российской
Федерации:"). The deletion score shown with the quotes tells how much they actually matter.

## Running

Requirements: Node ≥ 22; yarn 1 is used through `npx`.

```bash
npx yarn@1.22.22 install          # installs and builds all packages
npx yarn@1.22.22 start            # http://localhost:3000, workspace in ./workspace
```

Core must be running (default `http://127.0.0.1:8000`; change it with the command
**EviGraph: Set Core API URL**, and the reviewer name with **EviGraph: Set Reviewer Name**).
Core allows the Studio origin through CORS (`EVIGRAPH_CORS_ORIGINS`).

## Packages

| Package | Role |
|---|---|
| `evigraph-glsp-server` | GLSP node server: reads a `.evigraph` descriptor, loads the graph from Core, radial layout |
| `evigraph-glsp-client` | diagram views and styles |
| `evigraph-theia` | Theia extension: GLSP integration, EviGraph panel, review editor, commands |
| `evigraph-studio-app` | the Theia browser application |
