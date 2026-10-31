/* Controlled objects and owned temporary inputs; no remote services. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { regenerate } = require('./prepare-deepmerge.cjs');

const root = path.dirname(require.resolve('deepmerge/package.json'));
const files = ['index.js', 'dist/cjs.js', 'dist/umd.js'];
const merge = require('deepmerge');

function fixture(t) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-deepmerge-'));
    t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
    return directory;
}

function guardFixture(t) {
    const directory = fixture(t);
    for (const file of ['package.json', ...files]) {
        const target = path.join(directory, file);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        // Reconstruct original bytes only in the owned fixture, never the install.
        const original = fs.readFileSync(path.join(root, file), 'utf8').replace(
            /Object\.defineProperty\(destination, key, \{ value: ([^\n]+), enumerable: true, configurable: true, writable: true \}\)/g,
            'destination[key] = $1'
        );
        fs.writeFileSync(target, original);
    }
    return directory;
}

test('deepmerge hardening regenerates all entry points and is idempotent', t => {
    const directory = guardFixture(t);
    const first = regenerate(directory);
    assert.equal(first.status, 'regenerated');
    assert.equal(Object.keys(first.sha256).length, 3);
    assert.deepEqual(regenerate(directory), { ...first, status: 'already regenerated' });
    assert.equal(regenerate(root).status, 'already regenerated');
});

test('deepmerge guard rejects changed bytes before writing any entry point', t => {
    const directory = guardFixture(t);
    fs.appendFileSync(path.join(directory, 'dist/umd.js'), '\n// unknown vendor change');
    const before = files.map(file => fs.readFileSync(path.join(directory, file)));
    assert.throws(() => regenerate(directory), /Unknown deepmerge bytes/);
    files.forEach((file, index) => assert.deepEqual(fs.readFileSync(path.join(directory, file)), before[index]));
});

test('deepmerge guard rejects identity and version drift', t => {
    const directory = guardFixture(t);
    const manifest = path.join(directory, 'package.json');
    const metadata = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    const before = files.map(file => fs.readFileSync(path.join(directory, file)));
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, name: 'other-merge' }));
    assert.throws(() => regenerate(directory), /Unexpected deepmerge package identity/);
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, version: '4.3.2' }));
    assert.throws(() => regenerate(directory), /deepmerge changed/);
    files.forEach((file, index) => assert.deepEqual(fs.readFileSync(path.join(directory, file)), before[index]));
});

function assertOrdinaryPrototype(output) {
    assert.equal(Object.getPrototypeOf(output), Object.prototype);
    assert.equal(output.diagnosticMarker, undefined);
    assert.equal(Object.prototype.diagnosticMarker, undefined);
}

test('copying target own prototype-shaped data keeps the returned prototype ordinary', () => {
    const output = merge(JSON.parse('{"__proto__":{"diagnosticMarker":true},"ordinary":1}'), {});
    assertOrdinaryPrototype(output);
    assert.equal(Object.hasOwn(output, '__proto__'), true);
    assert.equal(output.__proto__.diagnosticMarker, true);
    assert.equal(output.ordinary, 1);
});

test('null-prototype targets cannot introduce inherited marker values', () => {
    const output = merge(Object.create(null), JSON.parse('{"__proto__":{"diagnosticMarker":true}}'));
    assertOrdinaryPrototype(output);
    assert.equal(Object.hasOwn(output, '__proto__'), true);
});

test('nested null and undefined targets preserve ordinary result prototypes', () => {
    for (const placeholder of [null, undefined, 1, false]) {
        const output = merge({ nested: placeholder }, JSON.parse('{"nested":{"__proto__":{"diagnosticMarker":true}}}'));
        assertOrdinaryPrototype(output.nested);
    }
});

test('both distributed CommonJS and UMD entries enforce the same invariant', () => {
    for (const file of ['dist/cjs.js', 'dist/umd.js']) {
        const entry = require(path.join(root, file));
        const output = entry(JSON.parse('{"__proto__":{"diagnosticMarker":true}}'), {});
        assertOrdinaryPrototype(output);
    }
});

test('ordinary nested merges, arrays, and all retain existing contracts', () => {
    const target = { config: { one: 1 }, list: [{ one: 1 }] };
    const source = { config: { two: 2 }, list: [{ two: 2 }] };
    const output = merge(target, source);
    assert.deepEqual(output, { config: { one: 1, two: 2 }, list: [{ one: 1 }, { two: 2 }] });
    assert.notEqual(output.config, target.config);
    assert.notEqual(output.list[0], target.list[0]);
    assert.deepEqual(merge.all([{ one: 1 }, { two: 2 }]), { one: 1, two: 2 });
    assert.throws(() => merge.all({}), /first argument should be an array/);
});

test('customMerge, arrayMerge and clone:false retain existing contracts', () => {
    const target = { config: { one: 1 }, list: [1] };
    const source = { config: { two: 2 }, list: [2] };
    const output = merge(target, source, {
        customMerge: key => key === 'config' ? (left, right) => ({ keys: Object.keys(left).concat(Object.keys(right)) }) : undefined,
        arrayMerge: (_left, right) => right
    });
    assert.deepEqual(output, { config: { keys: ['one', 'two'] }, list: [2] });
    assert.equal(output.list, source.list);
    const shared = { nested: true };
    assert.equal(merge({}, { shared }, { clone: false }).shared, shared);
});

test('symbols, descriptors, special values and custom mergeability retain contracts', () => {
    const symbol = Symbol('own');
    const ignored = Symbol('nonenumerable');
    const date = new Date('2026-01-01T00:00:00Z');
    const expression = /owned/;
    const source = { [symbol]: { value: 1 }, date, expression };
    Object.defineProperty(source, ignored, { value: 'hidden' });
    const output = merge({}, source);
    assert.deepEqual(output[symbol], { value: 1 });
    assert.equal(output[ignored], undefined);
    assert.equal(output.date, date);
    assert.equal(output.expression, expression);
    assert.deepEqual(Object.getOwnPropertyDescriptor(output, symbol), {
        value: { value: 1 }, enumerable: true, configurable: true, writable: true
    });
    const instance = new (class Configuration { constructor() { this.value = 2; } })();
    const custom = merge({}, { instance }, { isMergeableObject: value => value !== null && Object.getPrototypeOf(value) === Object.prototype });
    assert.equal(custom.instance, instance);
});

test('own constructor and prototype data remain data; inherited target keys stay blocked', () => {
    const source = JSON.parse('{"constructor":{"option":2},"prototype":{"option":3}}');
    const output = merge({ constructor: { existing: 1 } }, source);
    assert.deepEqual(output.constructor, { existing: 1, option: 2 });
    assert.deepEqual(output.prototype, { option: 3 });
    assert.equal(Object.getPrototypeOf(output), Object.prototype);
    const target = Object.create({ inherited: { one: 1 } });
    Object.defineProperty(target, 'hidden', { value: 1 });
    assert.deepEqual(merge(target, { inherited: { two: 2 }, hidden: 2, visible: 3 }), { visible: 3 });
});

test('actual Theia ApplicationPackage props merge keeps defaults and overrides', () => {
    const { ApplicationPackage } = require('@theia/application-package/lib/application-package');
    const app = new ApplicationPackage({ projectPath: path.resolve(__dirname, '..') });
    app._pck = { theia: { frontend: { config: { applicationName: 'Owned fixture' } }, backend: { config: { singleInstance: false } } } };
    assert.equal(app.props.frontend.config.applicationName, 'Owned fixture');
    assert.equal(app.props.frontend.config.defaultTheme.dark, 'dark');
    assert.equal(app.props.backend.config.singleInstance, false);
    assert.equal(app.props.backend.config.configurationFolder, '.theia');
    const caller = createRequire(require.resolve('@theia/application-package/package.json'));
    assert.equal(caller.resolve('deepmerge'), require.resolve('deepmerge'));
});

test('actual Theia localization extraction merges two files and existing translations', async t => {
    const directory = fixture(t);
    const output = path.join(directory, 'localization.json');
    fs.writeFileSync(path.join(directory, 'one.ts'), "nls.localize('owned/one', 'One');\n");
    fs.writeFileSync(path.join(directory, 'two.ts'), "nls.localize('owned/two', 'Two');\n");
    fs.writeFileSync(output, JSON.stringify({ owned: { existing: 'Existing' } }));
    const { extract } = require('@theia/localization-manager/lib/localization-extractor');
    await extract({ root: directory, files: ['one.ts', 'two.ts'], output, merge: true });
    assert.deepEqual(JSON.parse(fs.readFileSync(output, 'utf8')), { owned: { existing: 'Existing', one: 'One', two: 'Two' } });
    const caller = createRequire(require.resolve('@theia/localization-manager/package.json'));
    assert.equal(caller.resolve('deepmerge'), require.resolve('deepmerge'));
});
