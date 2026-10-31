/* Compatibility contracts resolve dependencies from their actual CommonJS callers. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const vm = require('node:vm');

const cli = createRequire(require.resolve('@theia/cli/package.json'));
const mocha = createRequire(cli.resolve('mocha/package.json'));
const tooltip = createRequire(require.resolve('react-tooltip/package.json'));
const trash = createRequire(require.resolve('trash/package.json'));
const uuidPattern = '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';

test('Mocha and UUID callers resolve the reviewed CommonJS versions', () => {
    assert.equal(mocha('diff/package.json').version, '8.0.3');
    for (const caller of [tooltip, trash]) {
        assert.equal(caller('uuid/package.json').version, '11.1.1');
        const uuid = caller('uuid');
        const value = uuid.v4();
        assert.match(value, new RegExp(`^${uuidPattern}$`));
        assert.equal(uuid.validate(value), true);
        assert.equal(uuid.version(value), 4);
    }
});

test('ReactTooltip renders using its real UUID caller and generated style selector', () => {
    const React = tooltip('react');
    const { renderToStaticMarkup } = tooltip('react-dom/server');
    const html = renderToStaticMarkup(React.createElement(require('react-tooltip'), null, 'tooltip contract'));
    const match = html.match(new RegExp(`id="(t${uuidPattern})"`));
    assert.ok(match, 'tooltip must render a generated UUID v4 identifier');
    assert.ok(html.includes(`.${match[1]} {`), 'generated identifier must match the tooltip style selector');
    assert.ok(html.includes('tooltip contract'));
});

test('Linux trash caller keeps UUID destination and metadata consistent with synthetic I/O', async () => {
    // Execute the installed caller with in-memory collaborators: no files are
    // moved, removed, trashed, or written by this contract on any platform.
    const source = fs.readFileSync(trash.resolve('./lib/linux.js'), 'utf8');
    const writes = [];
    const moves = [];
    const directories = [];
    const collaborators = {
        util: require('node:util'),
        os: { cpus: () => [{}] },
        path: path.posix,
        fs: {
            lstat: (_file, callback) => callback(null, { dev: 42 }),
            writeFile: (file, data, callback) => { writes.push({ file, data }); callback(null); }
        },
        uuid: trash('uuid'),
        'xdg-trashdir': async () => '/fixture/trash',
        'p-map': async (items, mapper) => Promise.all(items.map(mapper)),
        'make-dir': async directory => { directories.push(directory); },
        'move-file': async (from, to) => { moves.push({ from, to }); },
        '@stroncium/procfs': { procfs: { processMountinfo: () => [{ devId: 42, mountPoint: '/fixture' }] } }
    };
    const module = { exports: {} };
    const factory = vm.runInNewContext(`(function(require, module) { ${source}\n})`, {}, { timeout: 1000 });
    factory(name => {
        assert.ok(Object.hasOwn(collaborators, name), `unexpected trash collaborator: ${name}`);
        return collaborators[name];
    }, module);
    const [result] = await module.exports(['/fixture/input sample']);
    assert.equal(moves.length, 1);
    assert.equal(writes.length, 1);
    const identifier = path.basename(result.path);
    assert.match(identifier, new RegExp(`^${uuidPattern}$`));
    assert.equal(result.info, `/fixture/trash/info/${identifier}.trashinfo`);
    assert.deepEqual(moves[0], { from: '/fixture/input sample', to: result.path });
    assert.equal(writes[0].file, result.info);
    assert.match(writes[0].data, /^\[Trash Info\]\nPath=\/fixture\/input%20sample\nDeletionDate=/);
    assert.deepEqual(directories, ['/fixture/trash/files', '/fixture/trash/info']);
});

test('reviewed UUID name and time variants reject undersized output buffers before writing', () => {
    const namespace = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
    for (const caller of [tooltip, trash]) {
        const uuid = caller('uuid');
        for (const name of ['v3', 'v5', 'v6']) {
            const output = new Uint8Array(8).fill(170);
            const call = () => name === 'v6' ? uuid[name]({}, output, 4) : uuid[name]('contract', namespace, output, 4);
            assert.throws(call, RangeError, `${name} must reject an undersized output buffer`);
            assert.deepEqual([...output], Array(8).fill(170));
        }
    }
});

test('Mocha diff preserves ordinary patch round-trips and rejects a small malformed patch', () => {
    const diff = mocha('diff');
    const before = 'first line\nold second line\nlast line\n';
    const after = 'first line\nnew second line\nlast line\n';
    const patch = diff.createPatch('contract.txt', before, after);
    assert.equal(diff.applyPatch(before, patch), after);
    assert.equal(diff.parsePatch(patch).length, 1);
    assert.throws(() => diff.parsePatch('--- a\n+++ b\n@@ -1,1 +1,2 @@\n-a\n+b\n'), /Hunk|invalid|line/);
});

test('real Mocha reports expected unified and inline assertion differences', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-cli-diff-'));
    try {
        const file = path.join(dir, 'diff.cjs');
        fs.writeFileSync(file, "const assert = require('node:assert/strict'); describe('diff contract', () => { it('reports a controlled failure', () => assert.equal('first\\nactual token\\nlast', 'first\\nexpected token\\nlast')); });");
        for (const inline of [false, true]) {
            const args = [mocha.resolve('./bin/mocha.js'), '--no-config', '--no-package', '--no-color', '--reporter', 'spec'];
            if (inline) args.push('--inline-diffs');
            const run = spawnSync(process.execPath, [...args, file], { encoding: 'utf8', cwd: dir, timeout: 30000 });
            assert.ifError(run.error);
            assert.equal(run.status, 1, run.stderr);
            assert.match(run.stdout, /1 failing/);
            assert.match(run.stdout, /actual token/);
            assert.match(run.stdout, /expected token/);
            assert.match(run.stdout, inline ? /actual expected/ : /\+ expected - actual/);
        }
    } finally {
        fs.rmSync(dir, { recursive: true });
    }
});
