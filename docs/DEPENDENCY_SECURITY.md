# Dependency security qualification — 2026-10-31

The Monaco sanitizer P1 has a locally maintained, tested security backport. This is
**not a clean dependency audit or a patched upstream Theia release**. Core remains
loopback-only; remote identity, deployment and scientific acceptance are separate gates.

## Why a backport is necessary

Theia 1.74.3 ships `@theia/monaco-editor-core` 1.108.201. Fresh npm metadata for
Theia 1.76.0 still selects the same Monaco release. It contains both an exact npm
DOMPurify 3.2.7 dependency **and a vendored 3.2.7 JavaScript file** used by `domSanitize.js`.
Changing the lock alone therefore leaves the vulnerable code in browser assets.
See the [upstream bundled-library issue](https://github.com/microsoft/monaco-editor/issues/5517).

A Theia 1.76/React 19 migration would not fix this vendor copy. Instead, the build
uses the official [DOMPurify 3.4.17 release](https://github.com/cure53/DOMPurify/tree/3.4.17),
pinned directly in the application and narrowly resolved only below Monaco:
`**/@theia/monaco-editor-core/dompurify`. This deliberate local backport is outside
Monaco's old exact range; Yarn's compatibility warning is retained, not suppressed.
It is not a general dependency override.

`scripts/prepare-monaco-sanitizer.cjs` runs before the Studio bundle:

- requires Monaco 1.108.201, official DOMPurify 3.4.17 and the patched nested resolution;
- checks the exact original vendor SHA256 and the exact official CJS source SHA256;
- reproducibly regenerates the vendor module from that official source, preserving
  its license and Theia's CommonJS/default interoperability; the obsolete source-map
  reference is removed;
- accepts the exact already-regenerated output, and refuses unknown bytes or version
  drift. Reinstall dependencies to recover a partial/unknown local artifact; do not
  broaden the accepted hashes. Review or retire this backport when upstream changes.

No generated dependency/bundle file is committed or hand-edited. Four Node contracts
check hash refusal, version drift, source mutation and idempotence. Chromium executes
six hostile HTML/reparse cases through the **actual Monaco sanitizer module**, verifies
no event-handler execution and preserves benign markup/links. It then checks the actual
`bundle.js` and `secondary-window.js` for the reviewed backport and absence of old code.
These are bounded sanitizer/packaging checks, not proof against every browser exploit.
The generic payloads also passed before the fix: the RED baseline was the old shipped
asset failing the backport assertion, not a demonstrated EviGraph XSS exploit.

## Fresh before/after audit comparison

Same engine and public exact-version inputs were used on both sides. Counts from
separate engines and earlier dates are not interchangeable.

| Engine | Before | After |
|---|---|---|
| Yarn 1.22.22 native audit | 289 path occurrences / 53 unique advisory IDs; 10 critical, 120 high | 39 path occurrences / 4 unique IDs; 0 critical, 0 high; 6 low, 33 moderate |
| OSV exact lock pairs | 1555 pairs; 25 matched versions / 62 unique IDs | 1239 pairs; 13 matched versions / 13 unique IDs |

OSV query times: before `2026-10-31T09:31:19.303492+00:00`, after `2026-10-31T09:31:17.354667+00:00`.
Final lock SHA256: `b206933d1dcd5b6b5b0c2333418305e0e655c1e2bb92717bf66d08c339fe9952`.
The prior 2026-10-30 OSV result was 17 matched versions / 60 IDs. Fresh advisories
changed the baseline; it is retained as history, not used as today's denominator.

Lerna was only used to run the three workspace `clean` scripts. Those same scripts
now run explicitly through Yarn; the unused Lerna config and dependency were removed.
This removes its tar/Nx/pacote/sigstore/js-yaml graph rather than overriding it.
The existing literal-path rimraf command was upgraded to its supported Node 22 CLI.
The owned browser test uses Puppeteer 25.16.0; Theia CLI still pins older test tooling.

The **full audit remains nonzero**. Native audit exits 6; OSV still reports the
following lock matches, including critical/high build-tool findings absent from the
native response. No advisory IDs, severities or packages are ignored.

| Package | Version | OSV advisory references |
|---|---|---|
| decompress | 4.2.1 | [GHSA-h39j-r5qq-r9mm](https://osv.dev/vulnerability/GHSA-h39j-r5qq-r9mm), [GHSA-hrh2-vp3x-79xf](https://osv.dev/vulnerability/GHSA-hrh2-vp3x-79xf), [GHSA-jwp9-9v96-94mx](https://osv.dev/vulnerability/GHSA-jwp9-9v96-94mx), [GHSA-mp2f-45pm-3cg9](https://osv.dev/vulnerability/GHSA-mp2f-45pm-3cg9) |
| deepmerge | 4.3.1 | [GHSA-gcqx-w48m-w2h4](https://osv.dev/vulnerability/GHSA-gcqx-w48m-w2h4) |
| diff | 7.0.0 | [GHSA-73rr-hh4g-fpgx](https://osv.dev/vulnerability/GHSA-73rr-hh4g-fpgx) |
| glob | 10.5.0 | [GHSA-3g3m-2fjr-6pw4](https://osv.dev/vulnerability/GHSA-3g3m-2fjr-6pw4) |
| glob | 13.0.6 | [GHSA-3g3m-2fjr-6pw4](https://osv.dev/vulnerability/GHSA-3g3m-2fjr-6pw4) |
| minimatch | 10.2.6 | [GHSA-g3hv-75wg-m249](https://osv.dev/vulnerability/GHSA-g3hv-75wg-m249) |
| minimatch | 3.1.5 | [GHSA-g3hv-75wg-m249](https://osv.dev/vulnerability/GHSA-g3hv-75wg-m249) |
| minimatch | 5.1.9 | [GHSA-g3hv-75wg-m249](https://osv.dev/vulnerability/GHSA-g3hv-75wg-m249) |
| minimatch | 9.0.9 | [GHSA-g3hv-75wg-m249](https://osv.dev/vulnerability/GHSA-g3hv-75wg-m249) |
| serialize-javascript | 6.0.2 | [GHSA-5c6j-r48x-rmvq](https://osv.dev/vulnerability/GHSA-5c6j-r48x-rmvq), [GHSA-m5mm-p8h7-m29v](https://osv.dev/vulnerability/GHSA-m5mm-p8h7-m29v), [GHSA-qj8w-gfj5-8c6v](https://osv.dev/vulnerability/GHSA-qj8w-gfj5-8c6v) |
| uuid | 7.0.3 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| uuid | 8.3.2 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| zod | 3.25.76 | [GHSA-mrhx-c7xc-m3w5](https://osv.dev/vulnerability/GHSA-mrhx-c7xc-m3w5) |

## Reachability and remaining gates

- **Archive/plugin installation — unsupported, dependency finding remains open.**
  `decompress` 4.2.1 has critical symlink/path traversal advisories, not a zero-risk
  waiver. Its current source caller is Theia CLI `download:plugins`, including tar
  and VSIX extraction. No workspace manifest declares `theiaPlugins`; the standard
  prepare path only compiles, bundles and checks Theia versions. `@theia/plugin-ext`,
  `plugin-ext-vscode` and `vsx-registry` are absent from the installed graph and generated
  frontend. The shipped Studio has no plugin/archive ingestion command or UI. Do not
  add plugin download/install, invoke the CLI downloader on untrusted archives or claim
  that capability qualified until the dependency is fixed and hostile archive tests pass.
  A patched `@xhmikosr/decompress` has a different package/API; it is not force-aliased here.
- **CLI/test serialization — open.** Old `serialize-javascript` remains under CLI test
  tooling. Its RCE requires an attacker-controlled RegExp/Date-like object being
  serialized and the output executed. No such input flow from Core documents into that
  CLI path was identified. This does not qualify arbitrary third-party test scripts.
- **CLI browser protocol validation — open.** Theia CLI's older Puppeteer/Chromium BiDi
  still carries Zod 3 with collection-memory exhaustion. Our pinned test tool uses the
  supported patched dependency graph and local Chrome/CDP with page requests aborted.
  Remote or attacker-controlled BiDi endpoints are not a supported Studio operation.
- **deepmerge — open low finding.** Theia application-package merges developer-owned
  application manifest/config defaults; the inspected path does not take Core document
  text. Do not treat arbitrary untrusted application manifests as accepted input.
- **uuid — open moderate finding.** React tooltip/GLSP inspected call sites use v4;
  the advisory concerns v3/v5/v6 with a caller-provided output buffer. Other consumers
  and future changes still require review; the package match is not hidden.
- **glob/minimatch/jsdiff — open.** Remaining paths include filesystem/OPFS matching,
  package tooling and CLI test patch handling. Attacker-controlled pattern, huge tree,
  abort budget and patch-input behavior is not qualified by the sanitizer tests.

The current document-to-review path and local controlled CPU workflow are distinct
from those unsupported operations. Remaining supply-chain findings prevent a **full
clean-audit/release** claim, not an invented finding that every text shown in Studio
reaches an archive extractor. Multi-user IAM, deployment, source/data validation and
operational acceptance remain outside this dependency correction.

## Reproduce the maintained gates

From `apps/studio`, use Node >=22.12 and Yarn 1.22.22:

```sh
npx --yes yarn@1.22.22 install --frozen-lockfile
npx --yes yarn@1.22.22 exec puppeteer browsers install chrome
npx --yes yarn@1.22.22 test:security
npx --yes yarn@1.22.22 audit:security
```

The last command is deliberately nonzero while findings remain. For an existing local
Chrome, set `EVIGRAPH_BROWSER_PATH` for the test process only. The browser sandbox is
left enabled; no browser/global security setting is changed. CI performs the actual
bundle/security checks after its frozen install. The full audit is a separate explicit
release gate and is not represented as a passing CI audit job.
Refresh the advisory inventory and inspect new upstream releases before broadening the
input or deployment boundary. A local passing test is not hosted CI or production proof.
