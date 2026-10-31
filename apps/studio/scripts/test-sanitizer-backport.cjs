const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { regenerate } = require('./prepare-monaco-sanitizer.cjs');

function fixture(t) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-sanitizer-'));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const monacoRoot = path.join(root, 'monaco');
    const officialRoot = path.join(root, 'official');
    const target = path.join(monacoRoot, 'esm/vs/base/browser/dompurify/dompurify.js');
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.mkdirSync(path.join(officialRoot, 'dist'), { recursive: true });
    fs.writeFileSync(path.join(monacoRoot, 'package.json'), JSON.stringify({ version: '1.108.201' }));
    fs.writeFileSync(path.join(officialRoot, 'package.json'), JSON.stringify({ version: '3.4.17' }));
    fs.copyFileSync(require.resolve('dompurify'), path.join(officialRoot, 'dist/purify.cjs.js'));
    fs.writeFileSync(target, 'unexpected upstream bytes');
    return { monacoRoot, officialRoot, target };
}

test('unknown vendor bytes fail closed without overwriting', t => {
    const { monacoRoot, officialRoot, target } = fixture(t);
    assert.throws(() => regenerate(monacoRoot, officialRoot), /Unknown Monaco sanitizer bytes/);
    assert.equal(fs.readFileSync(target, 'utf8'), 'unexpected upstream bytes');
});

test('a new upstream version requires a deliberate backport review', t => {
    const { monacoRoot, officialRoot } = fixture(t);
    fs.writeFileSync(path.join(monacoRoot, 'package.json'), JSON.stringify({ version: '1.108.202' }));
    assert.throws(() => regenerate(monacoRoot, officialRoot), /Monaco changed/);
});

test('mutated official source fails its pinned content hash', t => {
    const { monacoRoot, officialRoot } = fixture(t);
    fs.appendFileSync(path.join(officialRoot, 'dist/purify.cjs.js'), '\n// mutation');
    assert.throws(() => regenerate(monacoRoot, officialRoot), /Official DOMPurify source hash changed/);
});

test('the real installed backport is idempotent', () => {
    const monacoRoot = path.dirname(require.resolve('@theia/monaco-editor-core/package.json'));
    const officialRoot = path.dirname(path.dirname(require.resolve('dompurify')));
    assert.equal(regenerate(monacoRoot, officialRoot).status, 'already regenerated');
});
