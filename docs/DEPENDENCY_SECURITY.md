# Dependency security qualification — 2026-10-30

Studio is a trusted local development environment. Do not expose it remotely or open
untrusted workspaces/extensions until the remaining dependency issues below are resolved.
Core API remains loopback-only and has no remote multi-user identity policy.

## Verified update boundary

The Studio lock was regenerated with Yarn 1.22.22 `upgrade` within existing manifest
ranges; no major-version override or new direct dependency was introduced. Theia moved
from 1.74.1 to 1.74.3. Full TypeScript, server/browser bundle and Theia dependency-version
checks passed. This is build compatibility evidence, not a browser exploit audit.

An exact-version OSV npm query changed from 1559 pairs/68 matched versions/155 advisory IDs
to 1555 pairs/17 matched versions/60 advisory IDs. Query timestamp: `2026-10-30T07:27:20.431948+00:00`.
Current `apps/studio/yarn.lock` SHA256: `533c59a7ec02e0f24f118e7570f04594a41db4d228ef71693d87542e833ebb22`.

The remaining matches below are not automatically exploitable in EviGraph. They are
also not waived: no vulnerability-ignore option or incompatible forced resolution was used.

## Remaining matches

| Package | Version | Public advisory references |
|---|---|---|
| @sigstore/core | 1.1.0 | [GHSA-jfc7-64v2-mr8c](https://osv.dev/vulnerability/GHSA-jfc7-64v2-mr8c) |
| decompress | 4.2.1 | [GHSA-h39j-r5qq-r9mm](https://osv.dev/vulnerability/GHSA-h39j-r5qq-r9mm), [GHSA-hrh2-vp3x-79xf](https://osv.dev/vulnerability/GHSA-hrh2-vp3x-79xf), [GHSA-jwp9-9v96-94mx](https://osv.dev/vulnerability/GHSA-jwp9-9v96-94mx), [GHSA-mp2f-45pm-3cg9](https://osv.dev/vulnerability/GHSA-mp2f-45pm-3cg9) |
| deepmerge | 4.3.1 | [GHSA-gcqx-w48m-w2h4](https://osv.dev/vulnerability/GHSA-gcqx-w48m-w2h4) |
| diff | 7.0.0 | [GHSA-73rr-hh4g-fpgx](https://osv.dev/vulnerability/GHSA-73rr-hh4g-fpgx) |
| dompurify | 3.2.7 | [GHSA-39q2-94rc-95cp](https://osv.dev/vulnerability/GHSA-39q2-94rc-95cp), [GHSA-55q2-fjhq-7xh7](https://osv.dev/vulnerability/GHSA-55q2-fjhq-7xh7), [GHSA-6688-9rhm-gjv2](https://osv.dev/vulnerability/GHSA-6688-9rhm-gjv2), [GHSA-76mc-f452-cxcm](https://osv.dev/vulnerability/GHSA-76mc-f452-cxcm), [GHSA-c2j3-45gr-mqc4](https://osv.dev/vulnerability/GHSA-c2j3-45gr-mqc4), [GHSA-c6gr-qvv4-5v3f](https://osv.dev/vulnerability/GHSA-c6gr-qvv4-5v3f), [GHSA-cj63-jhhr-wcxv](https://osv.dev/vulnerability/GHSA-cj63-jhhr-wcxv), [GHSA-cjmm-f4jc-qw8r](https://osv.dev/vulnerability/GHSA-cjmm-f4jc-qw8r), [GHSA-cmwh-pvxp-8882](https://osv.dev/vulnerability/GHSA-cmwh-pvxp-8882), [GHSA-crv5-9vww-q3g8](https://osv.dev/vulnerability/GHSA-crv5-9vww-q3g8), [GHSA-gvmj-g25r-r7wr](https://osv.dev/vulnerability/GHSA-gvmj-g25r-r7wr), [GHSA-h7mw-gpvr-xq4m](https://osv.dev/vulnerability/GHSA-h7mw-gpvr-xq4m), [GHSA-h8r8-wccr-v5f2](https://osv.dev/vulnerability/GHSA-h8r8-wccr-v5f2), [GHSA-hpcv-96wg-7vj8](https://osv.dev/vulnerability/GHSA-hpcv-96wg-7vj8), [GHSA-mrv2-3pqr-j5jr](https://osv.dev/vulnerability/GHSA-mrv2-3pqr-j5jr), [GHSA-r47g-fvhr-h676](https://osv.dev/vulnerability/GHSA-r47g-fvhr-h676), [GHSA-rp9w-3fw7-7cwq](https://osv.dev/vulnerability/GHSA-rp9w-3fw7-7cwq), [GHSA-v2wj-7wpq-c8vv](https://osv.dev/vulnerability/GHSA-v2wj-7wpq-c8vv), [GHSA-v9jr-rg53-9pgp](https://osv.dev/vulnerability/GHSA-v9jr-rg53-9pgp), [GHSA-vxr8-fq34-vvx9](https://osv.dev/vulnerability/GHSA-vxr8-fq34-vvx9), [GHSA-x4vx-rjvf-j5p4](https://osv.dev/vulnerability/GHSA-x4vx-rjvf-j5p4) |
| js-yaml | 4.1.0 | [GHSA-2883-xcg3-v3hh](https://osv.dev/vulnerability/GHSA-2883-xcg3-v3hh), [GHSA-52cp-r559-cp3m](https://osv.dev/vulnerability/GHSA-52cp-r559-cp3m), [GHSA-5p4m-2wfm-xmqj](https://osv.dev/vulnerability/GHSA-5p4m-2wfm-xmqj), [GHSA-h67p-54hq-rp68](https://osv.dev/vulnerability/GHSA-h67p-54hq-rp68), [GHSA-mh29-5h37-fv8m](https://osv.dev/vulnerability/GHSA-mh29-5h37-fv8m) |
| minimatch | 3.0.5 | [GHSA-23c5-xmqv-rm74](https://osv.dev/vulnerability/GHSA-23c5-xmqv-rm74), [GHSA-3ppc-4f35-3m26](https://osv.dev/vulnerability/GHSA-3ppc-4f35-3m26), [GHSA-7r86-cg39-jmmj](https://osv.dev/vulnerability/GHSA-7r86-cg39-jmmj) |
| minimatch | 9.0.3 | [GHSA-23c5-xmqv-rm74](https://osv.dev/vulnerability/GHSA-23c5-xmqv-rm74), [GHSA-3ppc-4f35-3m26](https://osv.dev/vulnerability/GHSA-3ppc-4f35-3m26), [GHSA-7r86-cg39-jmmj](https://osv.dev/vulnerability/GHSA-7r86-cg39-jmmj) |
| nx | 20.8.4 | [GHSA-g2r8-wvmj-jf5w](https://osv.dev/vulnerability/GHSA-g2r8-wvmj-jf5w), [GHSA-hrvq-x7jp-36xv](https://osv.dev/vulnerability/GHSA-hrvq-x7jp-36xv), [GHSA-vp3h-ghgh-jr7g](https://osv.dev/vulnerability/GHSA-vp3h-ghgh-jr7g), [GHSA-w2vw-w76x-qr89](https://osv.dev/vulnerability/GHSA-w2vw-w76x-qr89), [GHSA-w3vv-58gj-gw77](https://osv.dev/vulnerability/GHSA-w3vv-58gj-gw77) |
| pacote | 18.0.6 | [GHSA-w4pp-8pjf-rmxw](https://osv.dev/vulnerability/GHSA-w4pp-8pjf-rmxw) |
| serialize-javascript | 6.0.2 | [GHSA-5c6j-r48x-rmvq](https://osv.dev/vulnerability/GHSA-5c6j-r48x-rmvq), [GHSA-m5mm-p8h7-m29v](https://osv.dev/vulnerability/GHSA-m5mm-p8h7-m29v), [GHSA-qj8w-gfj5-8c6v](https://osv.dev/vulnerability/GHSA-qj8w-gfj5-8c6v) |
| sigstore | 2.3.1 | [GHSA-52v5-jr5w-gjxr](https://osv.dev/vulnerability/GHSA-52v5-jr5w-gjxr) |
| tar | 6.2.1 | [GHSA-23hp-3jrh-7fpw](https://osv.dev/vulnerability/GHSA-23hp-3jrh-7fpw), [GHSA-34x7-hfp2-rc4v](https://osv.dev/vulnerability/GHSA-34x7-hfp2-rc4v), [GHSA-83g3-92jg-28cx](https://osv.dev/vulnerability/GHSA-83g3-92jg-28cx), [GHSA-8qq5-rm4j-mr97](https://osv.dev/vulnerability/GHSA-8qq5-rm4j-mr97), [GHSA-8x88-c5mf-7j5w](https://osv.dev/vulnerability/GHSA-8x88-c5mf-7j5w), [GHSA-9ppj-qmqm-q256](https://osv.dev/vulnerability/GHSA-9ppj-qmqm-q256), [GHSA-gvwx-54wh-qm9j](https://osv.dev/vulnerability/GHSA-gvwx-54wh-qm9j), [GHSA-qffp-2rhf-9h96](https://osv.dev/vulnerability/GHSA-qffp-2rhf-9h96), [GHSA-r292-9mhp-454m](https://osv.dev/vulnerability/GHSA-r292-9mhp-454m), [GHSA-r6q2-hw4h-h46w](https://osv.dev/vulnerability/GHSA-r6q2-hw4h-h46w), [GHSA-vmf3-w455-68vh](https://osv.dev/vulnerability/GHSA-vmf3-w455-68vh), [GHSA-w8wr-v893-vjvp](https://osv.dev/vulnerability/GHSA-w8wr-v893-vjvp) |
| uuid | 10.0.0 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| uuid | 7.0.3 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| uuid | 8.3.2 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| zod | 3.25.76 | [GHSA-mrhx-c7xc-m3w5](https://osv.dev/vulnerability/GHSA-mrhx-c7xc-m3w5) |

## Reachability and next gate

- **P1 before untrusted Studio input:** `yarn why dompurify` locates 3.2.7 beneath
  `@theia/monaco-editor-core`. Theia Core uses patched 3.4.17, but that does not replace
  Monaco’s exact nested pin. A supported Monaco/Theia upgrade or a separately tested
  security backport is required; a blanket override is not presented as qualified.
- `decompress` is beneath Theia CLI. `tar 6` and `nx` come from Lerna build tools.
  `zod 3` comes through Puppeteer/Chromium BiDi. Build-tool exposure requires separate
  hostile archive/config/path threat review; it is not attributed to Python Core.
- Other listed dependency paths have not been fully assessed for exploit reachability.
  Treat relevant untrusted-input exposure as an unresolved gate, not a clean scan.
- Current exact Python execution pins were queried separately with no OSV matches.
  This does not attest Git code, image OS packages, models or future advisory state.

Reproduce dependency paths from `apps/studio` with `npx --yes yarn@1.22.22 why dompurify`
and analogous package names. Refresh lock resolution through Yarn, never by hand-editing
the generated lock. Retain the full affected build and browser-security regression gates.

## Local qualification scope

On 2026-10-30 the current Core suite passed 35 tests on a newly initialized PostgreSQL 17
cluster with verified task-owned data-directory identity; the cluster was stopped after
the run. Research property/unit tests passed 20 tests. No new scientific experiment,
untouched holdout, live deployment or unconditional certification guarantee is claimed.
