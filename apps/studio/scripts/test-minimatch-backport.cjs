/* Bounded count-based contracts; never run an unbounded hostile pattern. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { pathToFileURL } = require('node:url');
const { installedRoots, regenerate } = require('./prepare-minimatch.cjs');
const roots = installedRoots();
const files = ['dist/commonjs/index.js', 'dist/esm/index.js'];

function fixtures(t) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-minimatch-'));
    t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
    return roots.map((root, index) => {
        const copy = path.join(directory, String(index));
        for (const file of ['package.json', ...files]) {
            const target = path.join(copy, file);
            fs.mkdirSync(path.dirname(target), { recursive: true });
            // Reconstruct original bytes only in owned fixtures for guard tests.
            const original = fs.readFileSync(path.join(root, file), 'utf8')
                .replace('        const { braceExpandMax = 100_000 } = this.options;\n', '')
                .replace("p2 === '..' ||\n                        globParts.length >= braceExpandMax) {", "p2 === '..') {")
                .replace('        if (globParts.length > 1000) return globParts;\n', '')
                .replace('// Local preprocessing bounds: upstream commit 77a0f5c4b80bdc641c3c930a1d9edf5ad2db57f8; original source map detached.', '//# sourceMappingURL=index.js.map');
            fs.writeFileSync(target, original);
        }
        return copy;
    });
}

function snapshot(directories) {
    return directories.flatMap(root => files.map(file => fs.readFileSync(path.join(root, file))));
}

test('minimatch backport regenerates both module formats and is idempotent', t => {
    const copies = fixtures(t);
    const first = regenerate(copies);
    assert.equal(first.status, 'regenerated');
    assert.equal(first.installations, roots.length);
    assert.deepEqual(regenerate(copies), { ...first, status: 'already regenerated' });
    assert.equal(regenerate().status, 'already regenerated');
    for (const root of roots) {
        assert.equal(JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version, '10.2.6');
        for (const file of files) assert.equal(fs.readFileSync(path.join(root, file), 'utf8').includes('sourceMappingURL='), false);
    }
});

test('minimatch drift in the final entry prevents writes to every installation', t => {
    const copies = fixtures(t);
    fs.appendFileSync(path.join(copies.at(-1), files.at(-1)), '\n// unknown change');
    const before = snapshot(copies);
    assert.throws(() => regenerate(copies), /Unknown minimatch bytes/);
    assert.deepEqual(snapshot(copies), before);
});

test('minimatch identity and version drift fail before writing any installation', t => {
    const copies = fixtures(t);
    const manifest = path.join(copies.at(-1), 'package.json');
    const metadata = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    const before = snapshot(copies);
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, name: 'other-matcher' }));
    assert.throws(() => regenerate(copies), /Unexpected minimatch package identity/);
    assert.deepEqual(snapshot(copies), before);
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, version: '10.2.7' }));
    assert.throws(() => regenerate(copies), /minimatch changed/);
    assert.deepEqual(snapshot(copies), before);
});

for (const [index, root] of roots.entries()) for (const file of files) {
    const label = `installation ${index + 1} ${file}`;
    const module = file.includes('/commonjs/') ? Promise.resolve(require(path.join(root, file))) : import(pathToFileURL(path.join(root, file)).href);
    test(`${label}: expansion stops at a small explicit braceExpandMax`, async () => {
        const { Minimatch } = await module;
        const matcher = new Minimatch(Array(4).fill('**/../a/b').join('/'), { optimizationLevel: 2, braceExpandMax: 4 });
        assert.equal(matcher.set.length, 4);
        const ordinary = new Minimatch('**/../a/b/**/../c/d', { optimizationLevel: 2 });
        assert.equal(ordinary.set.length, 4);
        assert.equal(ordinary.match('../a/b/../c/d'), true);
        assert.equal(ordinary.match('x/a/b/y/c/d'), true);
    });
    test(`${label}: pairwise preprocessing is skipped above 1000 without timing assertions`, async () => {
        const { Minimatch } = await module;
        const matcher = new Minimatch('owned');
        matcher.partsMatch = () => assert.fail('large sets must skip pairwise comparisons');
        const large = Array.from({ length: 1001 }, (_, value) => [`owned${value}`]);
        assert.equal(matcher.secondPhasePreProcess(large), large);
        let comparisons = 0;
        matcher.partsMatch = () => { comparisons++; return false; };
        matcher.secondPhasePreProcess([['one'], ['two']]);
        assert.equal(comparisons, 1, 'small-set preprocessing remains active');
    });
    test(`${label}: makeRe and ordinary matching options retain the 10.x contract`, async () => {
        const { minimatch, Minimatch, makeRe, defaults } = await module;
        assert.equal(makeRe('owned-package/*').test('owned-package/internal'), true);
        assert.equal(makeRe('owned-package/*').test('other/internal'), false);
        assert.equal(minimatch('src/deep/app.ts', '**/*.{ts,js}'), true);
        assert.equal(minimatch('src/app.test.ts', '**/!(*.test).ts'), false);
        assert.equal(minimatch('src/app.ts', '**/!(*.test).ts'), true);
        assert.equal(new Minimatch('**/*', { dot: true }).match('.config/file'), true);
        assert.equal(new Minimatch('**/*').match('.config/file'), false);
        assert.equal(new Minimatch('**/*.TS', { nocase: true }).match('src/app.ts'), true);
        assert.equal(new Minimatch('src/*.ts', { windowsPathsNoEscape: true, platform: 'win32' }).match('src/app.ts'), true);
        assert.equal(defaults({ nocase: true })('APP.TS', '*.ts'), true);
    });
}

test('legacy callable and fixed modern matcher boundaries remain unchanged', () => {
    const legacy = createRequire(require.resolve('globby/package.json'));
    assert.equal(legacy('minimatch/package.json').version, '3.1.5');
    assert.equal(typeof legacy('minimatch'), 'function');
    assert.equal(require('minimatch/package.json').version, '11.0.3');
});
