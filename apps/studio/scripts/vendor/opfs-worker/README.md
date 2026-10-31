# Reviewed OPFS rebuild inputs

These seven runtime TypeScript sources are unchanged source contents recovered
from the integrity-verified npm `opfs-worker@1.3.1` source maps. Original copyright
and MIT license are retained. The upstream project is Maksim Kachurun's:
https://github.com/kachurun/opfs-worker

**Published provenance limitation:** npm metadata names gitHead
`b3da9da8c960005a802b660d90571188e11b7427`, but the package contains two generations
of helper/worker source maps. The maps actually referenced by public entry points
contain older `worker.ts`, `utils/errors.ts`, and `utils/helpers.ts` source content
than that commit. Using the commit directly would add two public exports and
change implementation beyond the matcher fix. Therefore this rebuild uses the
actual published runtime sources, cross-checked between both module formats:

- `index.js` and `raw.js` use `helpers-CKOebsbw.js`;
- `index.cjs` and `raw.cjs` use `helpers-CIiblZ8d.cjs`;
- both inline workers name `assets/worker-BeJaVyBV.js.map`;
- these helper, raw, inline-worker, and facade/index source maps agree on all
  overlapping source contents. Unused helper/worker map generations are ignored.

`provenance.json` records source hashes and their map hashes, the verified npm
tarball hash, all 37 original published files, original public export lists,
reviewed build dependencies, and deterministic rebuilt outputs. `LICENSE`,
`package.json`, and `vite.config.ts` are retained unchanged from the indicated
upstream commit as reference inputs. The gitHead is not a reproducible-source
attestation for the mixed published package.

No generated bundle is maintained here. `../../prepare-opfs.cjs` rebuilds all
four public ESM/CommonJS entry points and inline Web Worker using the existing
pinned esbuild and minimatch 11.0.3. The OPFS source uses only the named
`minimatch(path, pattern, options)` function, which remains available. This is a
local package rebuild, not an upstream fixed release or an authorship claim.

The reference Vite configuration is not executed. Its `raw` entry is
`src/worker.ts`; the published raw module exposes `OPFSWorker`, rather than the
factory in the unused upstream `src/raw.ts`. The rebuild preserves exactly the
published public export sets. Comlink remains external in public entry points
and is bundled inside the inline worker. A local build adapter creates a module
Worker from a Blob and revokes its URL inside the worker. Both module formats
are exercised through real Workers. Original declarations remain unchanged.

The helper validates package identity, every installed dist file, source bytes,
and build inputs before writing. It builds in memory, checks output hashes,
stages the files, then replaces the reviewed generated files. Unknown versions,
bytes, file sets, source changes, or build outputs are rejected. Repeated
execution is idempotent. Source maps use relative paths and contain original
sources. Dependency license texts are regenerated into
`dist/THIRD_PARTY_LICENSES.txt`. This does not claim bit reproduction of the
original Vite output.

When upstream publishes a fixed package, replace this local rebuild only after
reviewing its dependencies, bundled worker, exports, and browser integration.
