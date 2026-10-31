# Dependency security qualification — 2026-10-31

The Monaco sanitizer P1 has a locally maintained, tested security backport. This is
**not a clean dependency audit or a patched upstream Theia release**. Core remains
loopback-only; remote identity, deployment and scientific acceptance are separate gates.

## Current closure: compatible matcher bounds and source-rebuilt OPFS

The standard frozen install/build now regenerates the reviewed local fixes before
bundling. `prepare-minimatch.cjs` backports the three preprocessing bounds from
[upstream commit 77a0f5c4](https://github.com/isaacs/minimatch/commit/77a0f5c4b80bdc641c3c930a1d9edf5ad2db57f8)
to both installed minimatch 10.2.6 copies, CJS and ESM. It preserves the `makeRe`
API required by import-x. Identity/version and all four before/after hashes are
validated before any write; stale entry-point source-map directives are detached.
The package versions, licenses and advisory identities remain unchanged.

`prepare-opfs.cjs` rebuilds all four OPFS ESM/CommonJS entry points and the inline
Worker with fixed minimatch 11.0.3, using the existing pinned esbuild toolchain.
Seven actual published TypeScript runtime sources are preserved byte for byte.
The source material comes from cross-agreeing source maps in the SRI-verified npm
1.3.1 package. Its advertised gitHead does not reproduce three of these source
files; blindly building that commit would introduce unrelated implementation and
export changes. This limitation, source/map hashes, all 37 original package file
hashes, exact build inputs and generated hashes are retained in
[sources and provenance](../apps/studio/scripts/vendor/opfs-worker/README.md).
No minified bundle is edited or maintained by hand. Old embedded helper/worker
assets are removed only after complete original-file and generated-output checks.
Relative source maps and redistributed dependency licenses are generated too.
Unknown bytes, versions, file sets, sources or build outputs fail closed.

The public export sets remain exactly 46 index exports and one raw export in both
module formats. Bounded contracts preserve ordinary matching and demonstrate the
backported explicit expansion cap and >1000-entry pairwise preprocessing skip,
without a denial-of-service workload or timing assertions. Real sandboxed Chrome
Workers exercise Unicode/binary reads and writes, sync descriptors, watch
include/exclude, unwatch and the raw byte API in private test contexts. The facade
uses the actual Theia constructor profile: string root, BroadcastChannel instance
and hashing disabled. An owned physical OPFS subdirectory is checked; no user
storage is accessed. The complete maintained suite contains **63 Node contracts,
two OPFS browser profiles and six hostile DOM cases**. Execution receipts determine
which platform has actually passed; these are bounded integration contracts,
not arbitrary-worker resource or full Studio user-flow qualification.

### Source-level advisory disposition

| Version-based match | Current source disposition | Remaining boundary |
|---|---|---|
| deepmerge 4.3.1 / GHSA-gcqx-w48m-w2h4 | Guarded returned-object hardening below; reproduced own-key cases corrected | Upstream description disputed; version scan remains matched |
| minimatch 10.2.6 / GHSA-g3hv-75wg-m249 | Official bounds backported in both installed copies; actual import-x compatibility retained | Local maintained patch; package metadata remains 10.2.6 |
| Embedded OPFS minimatch 10.0.3 | Replaced through reviewed source rebuild with 11.0.3, including inline Worker | Published source-map provenance; original Vite output is not reproduced bit for bit |
| Legacy minimatch 3.1.5 / broad OSV range | The reported optimization-level-2 machinery is absent in this exact legacy implementation | Retain broad scanner match; do not infer general pattern/resource safety |

The [official minimatch advisory](https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249)
describes optimization level >=2. Inspected import-x and original OPFS routes use
default level 1, while the original legacy implementation lacks that mechanism.
The defensive 10.x backport and embedded rebuild additionally remove the reviewed
source mechanism. This is **source-qualified local remediation, not a clean
version-based audit**: no advisory is suppressed, package identity is not renamed
and `audit:security` deliberately preserves its native nonzero result. Arbitrary
hostile patterns, whole-worker resource isolation, deployment and external
operational acceptance remain outside these bounded contracts. Review these local
fixes when upstream releases or pinned bytes change; scheduled review date:
2026-11-14. No background automation is implied by that date.

## Prior follow-up: guarded deepmerge returned-object hardening

`prepare-deepmerge.cjs`, invoked before every standard bundle, regenerates three
reviewed destination assignments in deepmerge 4.3.1's source, CommonJS and UMD
entries with `Object.defineProperty`. Copying an own `__proto__` key now preserves
it as data instead of invoking an inherited setter on the fresh result. The
upstream safe-key policy, arrays, custom merge hooks and ordinary values remain
unchanged. Identity, version and exact before/after SHA-256 checks cover every
entry point before any write; unknown bytes fail the build rather than being
silently patched. No installed vendor file is maintained by hand.

Three controlled cases failed before and passed after this correction. Thirteen
additional Node contracts cover these cases, guard refusal/idempotence, ordinary
merge APIs and actual Theia application configuration/localization callers. The
full maintained suite contains **42 Node contracts plus six DOM cases**; consult
execution receipts for the tested platform and result.

This is a **local defensive backport, not a fixed upstream release**. The package
version remains 4.3.1 and [GHSA-gcqx-w48m-w2h4](https://osv.dev/vulnerability/GHSA-gcqx-w48m-w2h4)
remains in version-based audits. The issue is disputed upstream in
[issue 273](https://github.com/TehShrike/deepmerge/issues/273): these probes show a
changed prototype of the returned object, not global `Object.prototype`
pollution or proven remote exploitation. No advisory is suppressed. The subsequent matcher closure above supersedes its dependency finding;
untrusted-workload resource limits and operational acceptance remain unqualified. Retire or requalify this backport when upstream bytes/version change.

## Prior follow-up: compatible matching, UUID and reporter callers

The current scoped resolutions additionally select `glob` 14.0.3 for the actual
modern CLI/Mocha and rimraf 5/6 callers, `minimatch` 11.0.3 for reviewed named-API
consumers, `diff` 8.0.3 only under Mocha, and CommonJS-compatible `uuid` 11.1.1
only under ReactTooltip and trash. Parent ranges are deliberately exceeded;
Yarn warnings remain visible. The lock is generated by Yarn 1.22.22.

The [glob cancellation advisory](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4),
[jsdiff advisory](https://github.com/advisories/GHSA-73rr-hh4g-fpgx) and
[UUID advisory](https://github.com/advisories/GHSA-w5hq-g745-h8pq) identify the
fixed version boundaries; actual caller compatibility is tested, not inferred
from those version numbers. Callback-style legacy glob/minimatch is not forced
to the modern module shape.

Thirteen new Node contracts exercise actual workspace dependency checking,
Mocha discovery/reporters, named matcher options, glob cancellation, owned
rimraf fixture cleanup, ReactTooltip SSR, and the real Linux trash source with
explicitly synthetic I/O. No user file is moved or trashed. Small malformed
patch/buffer checks do not qualify arbitrary untrusted workloads or stress limits.
The controlled glob cancellation fixture scheduled 13 reads with the old Mocha
caller and only one after the correction, with no descendant read after abort.

Independent review found an incompatible candidate override:
`eslint-plugin-import-x` uses `makeRe`, removed from minimatch 11. It was excluded
before publication. Its actual ESM import and configured `no-internal-modules`
rule now have a regression contract; both the failed candidate and restored
behavior were executed. The plugin retains its supported minimatch 10 dependency
and that advisory remains open. This is not an ignored finding or an invented shim.

Fresh same-engine exact-lock OSV: **1225 actual pairs / 10 affected versions /
5 IDs before; 1209 pairs / 3 affected versions / 2 IDs after**. The remaining
pairs are `deepmerge` 4.3.1 and `minimatch` 3.1.5/10.2.6. Native Yarn audit is
still **exit 6, 17 path occurrences / 2 IDs, 6 low and 11 moderate**. These are
version-based counts from that preceding follow-up; source remediation is described
above. No advisory
suppression or clean overall security/release claim is made.

`opfs-worker` 1.3.1 also embeds matcher code in distributed helper files and
worker text. The inspected lock identifies a minimatch dependency, but does not
prove the embedded implementation's precise version or that any lock override
replaces it. Its bundled matcher provenance and hostile-pattern resource bounds
remain unqualified; this follow-up does not claim to patch that embedded code.

That preceding follow-up qualified 29 Node contracts plus six DOM cases, following
frozen installation and the complete Studio bundle. Local/hosted status must be
read from actual execution receipts. Source API references:
[glob](https://github.com/isaacs/node-glob),
[minimatch 11](https://github.com/isaacs/minimatch/tree/v11.0.3),
[jsdiff 8.0.3](https://github.com/kpdecker/jsdiff/tree/v8.0.3).

## Follow-up: CLI worker and browser dependencies

The application now also narrowly resolves Theia CLI's `puppeteer` and
`puppeteer-core` from its exact 25.1.0 pins to the already qualified 25.16.0
minor release. Mocha's `serialize-javascript` is resolved from 6.0.2 to 7.1.4.
These are deliberate exceptions to the parents' declared ranges, so Yarn's
compatibility warnings remain visible. Other consumers/major versions are not
globally overridden. The lock is regenerated by Yarn 1.22.22, not edited by hand.
See [Yarn's resolution semantics](https://classic.yarnpkg.com/en/docs/selective-version-resolutions/),
the [Puppeteer changelog](https://pptr.dev/CHANGELOG) and
[serializer release](https://github.com/yahoo/serialize-javascript/releases/tag/v7.1.4).

The new contracts resolve dependencies **from the CLI and Mocha callers**. Two
controlled spoofed RegExp/Date options executed a sentinel with the old real
`BufferedWorkerPool.serializeOptions` output in an isolated VM; the patched
serializer prevents that execution. A malformed forged RegExp can still be
rejected with a SyntaxError after unsafe flags are stripped. This is fail-closed
behavior for an invalid native-type impostor, not a promise to accept it.
Ordinary RegExp/Date/nested options and actual two-process Mocha pass/fail
reporting are checked separately. These developer-controlled configuration probes
do not demonstrate an attack from a Core document or a remote Studio user.

The actual CLI `test-page` adapter is also exercised through its resolved
`puppeteer-core`, with sandboxed Chrome and a small synthetic Theia-readiness
fixture. Both successful and failing browser results are asserted. This tests
adapter compatibility, not an interactive whole-IDE E2E or a BiDi endpoint.
The upstream `theia test` command supplies `--no-sandbox`; this harness calls the
adapter with its own sandbox-enabled launch instead of running that command.
No browser/global sandbox settings are changed. CI runs these six contracts in
addition to the four vendor guards and six existing hostile DOM cases.

Historical exact-lock OSV comparison for that CLI-tooling follow-up: **1239 pairs / 13 matched
versions / 13 IDs before; 1229 pairs / 11 matched versions / 9 IDs after**.
The three serializer IDs and the old Zod 3 finding leave the lock; Zod is now
selected through the newer browser graph. This is graph/advisory evidence, not
a hostile remote-BiDi qualification. Current native Yarn audit still reports
39 path occurrences / 4 IDs, 6 low and 33 moderate, exit 6. The former native
result below is historical; no fresh native-before comparison is claimed.
That snapshot still included critical `decompress`; the maintained archive
follow-up below supersedes that package selection. Other findings remain open.

## Follow-up: maintained CLI archive extractor

Theia CLI alone now resolves the old `decompress` 4.2.1 dependency to
[`@xhmikosr/decompress` 11.1.4](https://www.npmjs.com/package/@xhmikosr/decompress/v/11.1.4)
through the scoped npm alias `**/@theia/cli/decompress`. Other consumers are not
broadly overridden. The maintained package is ESM; a bare alias would break the
CLI's CommonJS callable import. `scripts/prepare-cli-decompress.cjs` runs before
bundling and changes that one import to a dynamic-import wrapper, preserving
all existing awaited call sites, upstream code and licensing.

This bridge requires CLI 1.74.3, the maintained package's actual name/version,
and exact SHA256 hashes of both the original caller and reviewed extractor entry
point. It recognizes only the exact reproducible patched output, rejects drift
before writing, and is idempotent. A new upstream version requires review or
retirement of the bridge; do not broaden hashes to accept unknown content.
Generated dependency files are regenerated by this checked build step, never
committed. Yarn regenerates the lock normally, retaining deliberate override
compatibility warnings.

Six Node contracts check original-to-patched reproduction, idempotence, unknown
caller bytes, CLI version drift, extractor identity/version/source drift, and
ordinary archive handling through the **actual installed CLI downloader**. The
last uses owned deterministic TAR/VSIX/Theia-ZIP fixtures, stubbed request service
responses, no remote requests, and checks six variants: ordinary TAR, VSIX,
Theia ZIP, packed VSIX, unpacked VSIX bundle, and packed bundle with exclusion.
These are compatibility and guard checks, not whole-IDE plugin installation,
a general malicious-archive acceptance suite or operational proof.

The shipped Studio still exposes no archive/plugin ingestion UI. This maintenance
removes the old CLI extractor; it does not add that feature or qualify arbitrary
plugin manifests, extension packs, registry access, plugin execution, resource
limits, or installation trust. Refresh exact-lock audits using the alias's actual
package identity `@xhmikosr/decompress`, not the logical name `decompress` paired
with version 11.1.4. The audit counts below describe the preceding CLI-tooling
snapshot and are not evidence of a clean current dependency graph.

Historical archive-follow-up alias-aware OSV audit (2026-10-31): **1226 actual name/version pairs,
11 affected versions / 9 IDs before → 1225 pairs, 10 affected versions / 5 IDs
after**. All four old `decompress` advisory IDs leave the selected graph;
`@xhmikosr/decompress` 11.1.4 has zero matches at query time. The remaining
matches are the ten deepmerge/diff/glob/minimatch/uuid versions listed in the
historical table below. This does not establish a clean dependency audit.

This scanner parses Yarn's lock and resolves npm aliases to actual package names,
then deduplicates actual name/version pairs. Earlier counts used logical alias
names, so their denominators must not be compared with this correction. Both
sides of the archive follow-up use the corrected scanner. That archive snapshot lock SHA256
is `6d5e7beed5c9245b0037bcc160bce0c9d504578dd6991949232cc33cb0bd8445`.
Native Yarn audit remains exit 6, 39 path occurrences / 4 IDs, 6 low and 33
moderate, zero high/critical in that engine. Its narrower advisory response does
not replace the full OSV graph result.

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

## First remediation pass: before/after audit history

Same engine and public exact-version inputs were used on both sides. Counts from
separate engines and earlier dates are not interchangeable.

| Engine | Before | After |
|---|---|---|
| Yarn 1.22.22 native audit | 289 path occurrences / 53 unique advisory IDs; 10 critical, 120 high | 39 path occurrences / 4 unique IDs; 0 critical, 0 high; 6 low, 33 moderate |
| OSV exact lock pairs | 1555 pairs; 25 matched versions / 62 unique IDs | 1239 pairs; 13 matched versions / 13 unique IDs |

OSV query times: before `2026-10-31T09:31:19.303492+00:00`, after `2026-10-31T09:31:17.354667+00:00`.
First-pass lock SHA256: `b206933d1dcd5b6b5b0c2333418305e0e655c1e2bb92717bf66d08c339fe9952`.
The prior 2026-10-30 OSV result was 17 matched versions / 60 IDs. Fresh advisories
changed the baseline; it is retained as history, not used as today's denominator.

Lerna was only used to run the three workspace `clean` scripts. Those same scripts
now run explicitly through Yarn; the unused Lerna config and dependency were removed.
This removes its tar/Nx/pacote/sigstore/js-yaml graph rather than overriding it.
The existing literal-path rimraf command was upgraded to its supported Node 22 CLI.
At that point the owned browser test used Puppeteer 25.16.0 while Theia CLI still
pinned the older test tooling corrected in the follow-up above.

The **preceding full audit was nonzero**. Native audit exited 6; OSV reported the
following lock matches before the maintained archive follow-up, including critical
build-tool findings absent from the native response. This is retained history;
refresh the current graph rather than reusing its counts. No advisory IDs,
severities or packages are ignored.

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
| uuid | 7.0.3 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |
| uuid | 8.3.2 | [GHSA-w5hq-g745-h8pq](https://osv.dev/vulnerability/GHSA-w5hq-g745-h8pq) |

## Reachability and remaining gates

- **Archive/plugin installation — unsupported product capability.** The old CLI
  extractor has been replaced with the maintained, pinned ESM package and guarded
  import bridge described above. Ordinary actual-caller archive compatibility is
  checked. No workspace manifest declares `theiaPlugins`; the standard prepare
  path compiles, bundles and checks Theia versions. `@theia/plugin-ext`,
  `plugin-ext-vscode` and `vsx-registry` are absent from the inspected installed
  graph and generated frontend. The shipped Studio has no plugin/archive ingestion
  command or UI. Do not infer arbitrary plugin installation or execution safety
  from this scoped dependency maintenance.
- **CLI/test serialization — corrected in the qualified worker profile.** The old
  serializer is absent from the lock; actual Mocha worker compatibility and controlled
  RegExp/Date injection probes pass. Arbitrary third-party test scripts are still code,
  and are not made trusted by a serializer update.
- **CLI browser graph — old Zod 3 finding removed.** Theia CLI now uses the same
  reviewed Puppeteer minor release as the owned test harness. Actual adapter/CDP
  compatibility passes; remote or attacker-controlled BiDi endpoints remain unsupported
  and are not qualified by a lock scan or the synthetic adapter fixture.
- **deepmerge — local returned-object hardening; version-based low finding open.**
  The guarded backport above protects the tested destination writes. Theia
  application-package merges developer-owned manifest/config defaults; the inspected
  path does not take Core document text. Arbitrary untrusted manifests remain
  outside the qualified input boundary.
- **UUID/jsdiff/modern glob — corrected in reviewed callers.** UUID v4 remains
  compatible, name/time output-buffer bounds are checked, actual Mocha diff
  reporters pass, and controlled glob cancellation stops new traversal reads.
  These are bounded contracts, not arbitrary input/workload qualification.
- **Legacy/bundled minimatch — source-qualified disposition above.** The makeRe
  caller retains its compatible backported 10.x API; the embedded OPFS matcher is
  rebuilt from sources with 11.0.3. The reported mechanism is absent in legacy3.x,
  while broad version matches remain unsuppressed. Arbitrary hostile patterns,
  huge trees and whole-worker resource isolation remain unqualified.

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
bundle/security checks after its frozen install. Its Studio job uses Ubuntu 24.04
and the runner's packaged `/opt/google/chrome/chrome`, records its exact version,
and sets `EVIGRAPH_BROWSER_PATH` only for the test step. The initial downloaded
Chrome for Testing launch failed with “No usable sandbox” under Ubuntu's AppArmor
user-namespace restrictions. The packaged stable Chrome path has an existing
system sandbox profile, as described in the
[Chromium AppArmor guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md).
No sandbox-disabling flag, AppArmor/sysctl change or skipped browser test is used.
This CI browser follows the recorded runner image rather than a separately
pinned browser download; local runs may use the downloaded browser or the explicit
executable override above. The full audit is a separate explicit
release gate and is not represented as a passing CI audit job.
Refresh the advisory inventory and inspect new upstream releases before broadening the
input or deployment boundary. A local passing test is not hosted CI or production proof.
