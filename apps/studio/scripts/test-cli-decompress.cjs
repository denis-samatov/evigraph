/* Owned, ordinary archives and the actual CLI caller; no remote plugin service. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const zlib = require('node:zlib');
const { regenerate } = require('./prepare-cli-decompress.cjs');

const cliRoot = path.dirname(require.resolve('@theia/cli/package.json'));
const cli = createRequire(path.join(cliRoot, 'package.json'));
const extractorRoot = path.dirname(cli.resolve('decompress'));

function fixture(t) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-cli-archive-'));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    return root;
}

function guardFixture(t) {
    const root = fixture(t);
    const cliCopy = path.join(root, 'cli');
    const extractorCopy = path.join(root, 'extractor');
    fs.mkdirSync(path.join(cliCopy, 'lib'), { recursive: true });
    fs.mkdirSync(extractorCopy);
    for (const name of ['package.json', 'lib/download-plugins.js']) fs.copyFileSync(path.join(cliRoot, name), path.join(cliCopy, name));
    for (const name of ['package.json', 'index.js']) fs.copyFileSync(path.join(extractorRoot, name), path.join(extractorCopy, name));
    return { cliCopy, extractorCopy, target: path.join(cliCopy, 'lib/download-plugins.js') };
}

test('CLI archive bridge is idempotent and resolves the exact maintained extractor', t => {
    const { cliCopy, extractorCopy, target } = guardFixture(t);
    const before = fs.readFileSync(target);
    assert.equal(regenerate(cliCopy, extractorCopy).status, 'already regenerated');
    assert.deepEqual(fs.readFileSync(target), before);
    assert.equal(regenerate(cliRoot, extractorRoot).status, 'already regenerated');
});

test('CLI archive bridge reproducibly transforms the original pinned caller', t => {
    const { cliCopy, extractorCopy, target } = guardFixture(t);
    const patched = fs.readFileSync(target, 'utf8');
    const original = patched.replace(
        "const decompress = (...args) => import('decompress').then(({ default: extract }) => extract(...args));",
        'const decompress = require("decompress");'
    );
    assert.notEqual(original, patched);
    fs.writeFileSync(target, original);
    assert.equal(regenerate(cliCopy, extractorCopy).status, 'regenerated');
    assert.equal(fs.readFileSync(target, 'utf8'), patched);
});

test('CLI archive bridge refuses unknown downloader bytes without overwriting', t => {
    const { cliCopy, extractorCopy, target } = guardFixture(t);
    fs.appendFileSync(target, '\n// unknown vendor change');
    const before = fs.readFileSync(target);
    assert.throws(() => regenerate(cliCopy, extractorCopy), /Unknown Theia downloader bytes/);
    assert.deepEqual(fs.readFileSync(target), before);
});

test('CLI archive bridge refuses upstream version drift', t => {
    const { cliCopy, extractorCopy, target } = guardFixture(t);
    const before = fs.readFileSync(target);
    const manifest = path.join(cliCopy, 'package.json');
    const metadata = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, version: '1.74.4' }));
    assert.throws(() => regenerate(cliCopy, extractorCopy), /Theia CLI changed/);
    assert.deepEqual(fs.readFileSync(target), before);
});

test('CLI archive bridge refuses extractor identity, version and source drift', t => {
    const { cliCopy, extractorCopy, target } = guardFixture(t);
    const before = fs.readFileSync(target);
    const manifest = path.join(extractorCopy, 'package.json');
    const metadata = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, name: 'decompress' }));
    assert.throws(() => regenerate(cliCopy, extractorCopy), /not the reviewed maintained package/);
    fs.writeFileSync(manifest, JSON.stringify({ ...metadata, version: '11.1.5' }));
    assert.throws(() => regenerate(cliCopy, extractorCopy), /CLI extractor changed/);
    fs.writeFileSync(manifest, JSON.stringify(metadata));
    fs.appendFileSync(path.join(extractorCopy, 'index.js'), '\n// changed source');
    assert.throws(() => regenerate(cliCopy, extractorCopy), /Reviewed extractor source hash changed/);
    assert.deepEqual(fs.readFileSync(target), before);
});

// Minimal deterministic, ordinary TAR and stored ZIP fixtures avoid a test-only
// archive dependency. Entries here are fixed owned paths, never supplied by users.
function tar(entries) {
    const chunks = [];
    for (const [name, data] of entries) {
        const body = Buffer.from(data);
        const header = Buffer.alloc(512);
        header.write(name, 0, 100);
        for (const [offset, size, value] of [[100, 8, 0o644], [108, 8, 0], [116, 8, 0], [124, 12, body.length], [136, 12, 0]]) {
            header.write(value.toString(8).padStart(size - 1, '0') + '\0', offset, size);
        }
        header.fill(32, 148, 156);
        header.write('0', 156);
        header.write('ustar\0', 257);
        header.write('00', 263);
        const checksum = header.reduce((sum, byte) => sum + byte, 0);
        header.write(checksum.toString(8).padStart(6, '0') + '\0 ', 148, 8);
        chunks.push(header, body, Buffer.alloc((512 - body.length % 512) % 512));
    }
    return zlib.gzipSync(Buffer.concat([...chunks, Buffer.alloc(1024)]));
}

function crc32(data) {
    let crc = 0xffffffff;
    for (const byte of data) {
        crc ^= byte;
        for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    return (crc ^ 0xffffffff) >>> 0;
}

function zip(entries) {
    const local = [];
    const central = [];
    let offset = 0;
    for (const [name, data] of entries) {
        const filename = Buffer.from(name);
        const body = Buffer.from(data);
        const header = Buffer.alloc(30);
        header.writeUInt32LE(0x04034b50, 0);
        header.writeUInt16LE(20, 4);
        header.writeUInt32LE(crc32(body), 14);
        header.writeUInt32LE(body.length, 18);
        header.writeUInt32LE(body.length, 22);
        header.writeUInt16LE(filename.length, 26);
        const directory = Buffer.alloc(46);
        directory.writeUInt32LE(0x02014b50, 0);
        directory.writeUInt16LE(20, 4);
        directory.writeUInt16LE(20, 6);
        header.copy(directory, 8, 6, 28);
        directory.writeUInt32LE(offset, 42);
        local.push(header, filename, body);
        central.push(directory, filename);
        offset += header.length + filename.length + body.length;
    }
    const directory = Buffer.concat(central);
    const end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50, 0);
    end.writeUInt16LE(entries.length, 8);
    end.writeUInt16LE(entries.length, 10);
    end.writeUInt32LE(directory.length, 12);
    end.writeUInt32LE(offset, 16);
    return Buffer.concat([...local, directory, end]);
}

test('actual Theia downloader preserves TAR, VSIX, Theia ZIP and packed bundle contracts', async t => {
    const root = fixture(t);
    const vsix = zip([['extension/package.json', '{"name":"owned-fixture","version":"1.0.0"}'], ['extension/sentinel.txt', 'SAFE']]);
    const archives = {
        'regular.tar.gz': tar([['package.json', '{"name":"owned-fixture"}'], ['nested/sentinel.txt', 'SAFE']]),
        'one.vsix': vsix,
        'one.theia': vsix,
        'bundle.tar.gz': tar([['one.vsix', vsix], ['two.vsix', vsix]])
    };
    const downloadPlugins = cli('./lib/download-plugins.js').default;
    const prior = process.cwd();
    try {
        for (const [file, packed, excluded] of [
            ['regular.tar.gz', false, []], ['one.vsix', false, []], ['one.theia', false, []],
            ['one.vsix', true, []], ['bundle.tar.gz', false, []], ['bundle.tar.gz', true, ['two']]
        ]) {
            const cwd = path.join(root, `${file}-${packed}`);
            fs.mkdirSync(cwd);
            process.chdir(cwd);
            fs.writeFileSync('package.json', JSON.stringify({ theiaPlugins: { fixture: `https://synthetic.invalid/${file}` }, theiaPluginsExcludeIds: excluded }));
            let requests = 0;
            const requestService = { request: async ({ url }) => {
                assert.equal(url, `https://synthetic.invalid/${file}`);
                requests++;
                return { res: { statusCode: 200 }, buffer: archives[file] };
            } };
            await downloadPlugins({}, { removeTokens: async () => {} }, requestService, { packed, parallel: false });
            assert.equal(requests, 1);
            if (file === 'regular.tar.gz') assert.equal(fs.readFileSync('plugins/fixture/nested/sentinel.txt', 'utf8'), 'SAFE');
            else if (file === 'bundle.tar.gz') {
                assert.deepEqual(packed ? fs.readFileSync('plugins/one.vsix') : fs.readFileSync('plugins/one/extension/sentinel.txt'), packed ? vsix : Buffer.from('SAFE'));
                assert.equal(fs.existsSync(packed ? 'plugins/two.vsix' : 'plugins/two'), !excluded.includes('two'));
            } else if (packed) assert.deepEqual(fs.readFileSync('plugins/fixture.vsix'), vsix);
            else assert.equal(fs.readFileSync('plugins/fixture/extension/sentinel.txt', 'utf8'), 'SAFE');
        }
    } finally {
        process.chdir(prior);
    }
});
