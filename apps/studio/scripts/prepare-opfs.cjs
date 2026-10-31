/* Rebuild reviewed MIT OPFS sources, including its inline worker; never patch minified bytes. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const vendor = path.join(__dirname, 'vendor/opfs-worker');
const provenance = require('./vendor/opfs-worker/provenance.json');
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const studioRequire = createRequire(path.join(__dirname, '../package.json'));

function packageRoot(name) {
    let directory = path.dirname(studioRequire.resolve(name));
    while (!fs.existsSync(path.join(directory, 'package.json')) ||
        JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8')).name !== name) {
        const parent = path.dirname(directory);
        assert.notEqual(parent, directory, `Package identity not found: ${name}`);
        directory = parent;
    }
    return directory;
}

function inputRoots() {
    return Object.fromEntries(Object.entries(provenance.buildInputs).map(([name, version]) => {
        const root = packageRoot(name);
        assert.equal(JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version, version,
            `${name} build input changed: review OPFS rebuild`);
        return [name, root];
    }));
}

function inventory(root) {
    const files = {};
    function visit(directory) {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
            const file = path.join(directory, entry.name);
            assert(!entry.isSymbolicLink(), `Unexpected OPFS symlink: ${file}`);
            if (entry.isDirectory()) visit(file);
            else files[path.relative(root, file).split(path.sep).join('/')] = sha256(fs.readFileSync(file));
        }
    }
    visit(path.join(root, 'dist'));
    for (const name of ['LICENSE', 'README.md', 'package.json']) files[name] = sha256(fs.readFileSync(path.join(root, name)));
    return files;
}

async function buildOutputs() {
    for (const [file, hash] of Object.entries(provenance.upstreamSources)) {
        assert.equal(sha256(fs.readFileSync(path.join(vendor, file))), hash, `Unknown OPFS source bytes: ${file}`);
    }
    const roots = inputRoots();
    const esbuild = studioRequire('esbuild');
    // Only this named minimatch API is used by the unmodified OPFS sources.
    const matcher = path.join(roots.minimatch, 'dist/esm/index.js');
    const resolveMatcher = { name: 'reviewed-matcher', setup(build) {
        build.onResolve({ filter: /^minimatch$/ }, () => ({ path: matcher }));
    } };
    const common = {
        absWorkingDir: vendor, bundle: true, write: false, platform: 'browser', target: 'es2022',
        nodePaths: [path.resolve(__dirname, '../node_modules')],
        legalComments: 'inline', logLevel: 'silent',
        define: { 'process.env.NODE_ENV': JSON.stringify('production') }
    };
    const worker = await esbuild.build({ ...common, entryPoints: ['src/worker.ts'], format: 'esm',
        plugins: [resolveMatcher], outfile: 'dist/worker-inline.js' });
    const workerSource = 'URL.revokeObjectURL(import.meta.url);\n' + worker.outputFiles[0].text;
    const inlinePlugin = { name: 'inline-module-worker', setup(build) {
        build.onResolve({ filter: /\?worker&inline$/ }, () => ({ path: 'opfs-inline-worker', namespace: 'opfs-inline' }));
        build.onLoad({ filter: /.*/, namespace: 'opfs-inline' }, () => ({
            contents: `const source = ${JSON.stringify(workerSource)};
                export default function WorkerCtor(options) {
                    const objectURL = URL.createObjectURL(new Blob([source], { type: 'text/javascript;charset=utf-8' }));
                    try { return new Worker(objectURL, { ...options, type: 'module' }); }
                    catch (error) { URL.revokeObjectURL(objectURL); throw error; }
                }`, loader: 'js'
        }));
    } };
    const output = {};
    for (const [entry, source] of [['index', 'src/index.ts'], ['raw', 'src/worker.ts']]) {
        for (const [format, extension] of [['esm', 'js'], ['cjs', 'cjs']]) {
            const result = await esbuild.build({ ...common, entryPoints: [source], format, sourcemap: 'external',
                sourcesContent: true, outfile: `dist/${entry}.${extension}`, external: ['comlink'],
                plugins: [resolveMatcher, inlinePlugin] });
            for (const file of result.outputFiles) {
                const name = path.relative(vendor, file.path).split(path.sep).join('/');
                output[name] = file.contents;
                if (name.endsWith('.map')) {
                    const map = JSON.parse(file.text);
                    assert(map.sources.every(source => !path.isAbsolute(source)), 'Absolute source map path refused');
                }
            }
        }
    }
    // Preserve the redistributed dependencies' licenses alongside the generated bundles.
    const licenses = [];
    for (const name of ['minimatch', '@isaacs/nonrecursive-glob-match', 'brace-expansion', 'balanced-match', 'comlink']) {
        const root = name in roots ? roots[name] : packageRoot(name);
        const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
        const licenseFile = fs.readdirSync(root).find(file => /^licen[sc]e(?:\.md|\.txt)?$/i.test(file));
        assert(licenseFile, `${name}: license text unavailable`);
        licenses.push(`${name}@${metadata.version}\n${fs.readFileSync(path.join(root, licenseFile), 'utf8')}`);
    }
    output['dist/THIRD_PARTY_LICENSES.txt'] = Buffer.from(licenses.join('\n\n'));
    return output;
}

async function regenerate(root = packageRoot('opfs-worker')) {
    const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
    assert.equal(metadata.name, 'opfs-worker', 'Unexpected OPFS package identity');
    assert.equal(metadata.version, '1.3.1', 'OPFS changed: review or retire local source rebuild');
    const current = inventory(root);
    const preserved = Object.fromEntries(Object.entries(provenance.originalFiles).filter(([name]) =>
        !/\.(?:js|cjs)(?:\.map)?$/.test(name)));
    const rebuilt = { ...preserved, ...provenance.generatedFiles };
    const original = JSON.stringify(Object.entries(current).sort()) === JSON.stringify(Object.entries(provenance.originalFiles).sort());
    const known = JSON.stringify(Object.entries(current).sort()) === JSON.stringify(Object.entries(rebuilt).sort());
    assert(original || known, 'Unknown OPFS bytes or file set: refusing to overwrite');
    const output = await buildOutputs();
    assert.deepEqual(Object.fromEntries(Object.entries(output).map(([name, bytes]) => [name, sha256(bytes)])),
        provenance.generatedFiles, 'OPFS regenerated bytes changed: review build inputs');
    if (!original) return { status: 'already regenerated', sha256: provenance.generatedFiles, buildInputs: provenance.buildInputs };
    // Build and verify all outputs before touching the installation. Stage on the same filesystem.
    const stage = fs.mkdtempSync(path.join(root, '.opfs-rebuild-'));
    try {
        for (const [name, bytes] of Object.entries(output)) {
            const file = path.join(stage, name); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, bytes);
        }
        for (const name of Object.keys(provenance.originalFiles).filter(name => /\.(?:js|cjs)(?:\.map)?$/.test(name))) fs.unlinkSync(path.join(root, name));
        for (const name of Object.keys(output)) fs.renameSync(path.join(stage, name), path.join(root, name));
    } finally { fs.rmSync(stage, { recursive: true, force: true }); }
    assert.deepEqual(inventory(root), rebuilt, 'Installed OPFS rebuild did not match manifest');
    return { status: 'regenerated', sha256: provenance.generatedFiles, buildInputs: provenance.buildInputs };
}

if (require.main === module) regenerate().then(result => console.log(JSON.stringify(result))).catch(error => {
    console.error(error); process.exitCode = 1;
});
module.exports = { regenerate, buildOutputs, inventory, packageRoot };
