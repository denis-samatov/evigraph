/* Local backport of isaacs/minimatch@77a0f5c4; package/advisory identity is retained. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');

const VERSION = '10.2.6';
const HASHES = {
    'dist/commonjs/index.js': ['d224f71f20d7c206fcc5b7e9f747324c7698345a0b2c28d717dd9cf698306783', '6e66b88a80a70158c8a874bd40d8a167fb1eaf09bafe12871de631e7907e89ac'],
    'dist/esm/index.js': ['59821ec2ce0d3df968292036e5c831ad322b33e9c33a949ecbc9dfe125d165be', 'd222bd51a2d4229e5984d7e730a4a5f5f24f14e181398d8c227e4bcb758a094a']
};
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const replacements = [
    ['firstPhasePreProcess(globParts) {\n', 'firstPhasePreProcess(globParts) {\n        const { braceExpandMax = 100_000 } = this.options;\n'],
    ["p2 === '..') {", "p2 === '..' ||\n                        globParts.length >= braceExpandMax) {"],
    ['secondPhasePreProcess(globParts) {\n', 'secondPhasePreProcess(globParts) {\n        if (globParts.length > 1000) return globParts;\n'],
    ['//# sourceMappingURL=index.js.map', '// Local preprocessing bounds: upstream commit 77a0f5c4b80bdc641c3c930a1d9edf5ad2db57f8; original source map detached.']
];

function installedRoots() {
    return [...new Set(['eslint-plugin-import-x', 'opfs-worker'].map(name => {
        const caller = createRequire(require.resolve(name));
        return path.dirname(caller.resolve('minimatch/package.json'));
    }))];
}

function regenerate(roots = installedRoots()) {
    assert.ok(roots.length > 0, 'No reviewed minimatch installations supplied');
    // Plan every installation and entry before writing any. Keep package version,
    // license and makeRe API. Detach stale entry-point source maps rather than
    // linking changed executable code to the original unpatched TypeScript.
    const plans = roots.flatMap(root => {
        const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
        assert.equal(metadata.name, 'minimatch', 'Unexpected minimatch package identity');
        assert.equal(metadata.version, VERSION, 'minimatch changed: review or retire local backport');
        return Object.entries(HASHES).map(([file, [originalHash, patchedHash]]) => {
            const target = path.join(root, file);
            const current = fs.readFileSync(target, 'utf8');
            if (sha256(current) === patchedHash) return { root, file, target, output: current, changed: false };
            assert.equal(sha256(current), originalHash, `Unknown minimatch bytes in ${target}: refusing to overwrite`);
            let output = current;
            for (const [before, after] of replacements) {
                assert.equal(output.split(before).length - 1, 1, `Reviewed minimatch fragment changed in ${file}`);
                output = output.replace(before, after);
            }
            assert.equal(sha256(output), patchedHash, `Unexpected minimatch backport output in ${file}`);
            return { root, file, target, output, changed: true };
        });
    });
    for (const plan of plans) if (plan.changed) fs.writeFileSync(plan.target, plan.output);
    return {
        status: plans.some(plan => plan.changed) ? 'regenerated' : 'already regenerated',
        installations: roots.length,
        sha256: Object.fromEntries(Object.entries(HASHES).map(([file, hashes]) => [file, hashes[1]]))
    };
}

if (require.main === module) console.log(JSON.stringify(regenerate()));
module.exports = { installedRoots, regenerate };
