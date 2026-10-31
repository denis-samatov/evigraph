/* Verify source rebuild contracts and an isolated real OPFS worker, without user storage. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { regenerate, inventory, packageRoot } = require('./prepare-opfs.cjs');
const provenance = require('./vendor/opfs-worker/provenance.json');
const root = packageRoot('opfs-worker');

function registerContracts() {
    const { test } = require('node:test');
    test('OPFS has only source-rebuilt fixed matcher assets, with relative source maps', () => {
        const actual = inventory(root);
        for (const [file, hash] of Object.entries(provenance.generatedFiles)) assert.equal(actual[file], hash, `Missing reviewed OPFS rebuild: ${file}`);
        for (const name of Object.keys(actual)) assert(!/helpers-|assets\/worker-/.test(name), `Retired embedded matcher remains: ${name}`);
        for (const name of ['index.js.map', 'index.cjs.map', 'raw.js.map', 'raw.cjs.map']) {
            const map = JSON.parse(fs.readFileSync(path.join(root, 'dist', name), 'utf8'));
            assert(map.sources.every(source => !path.isAbsolute(source)));
            assert(map.sources.some(source => source.includes('minimatch/src/index.ts')));
            assert(map.sources.some(source => source.includes('@isaacs/nonrecursive-glob-match/src/index.ts')));
            assert(!map.sourcesContent.some(source => source.includes('function fastTest()')));
        }
    });
    test('OPFS rebuild is deterministic and idempotent; guard refuses unknown bytes before writes', async t => {
        const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-opfs-'));
        t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
        for (const name of Object.keys(inventory(root))) {
            const target = path.join(directory, name); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(path.join(root, name), target);
        }
        assert.equal((await regenerate(directory)).status, 'already regenerated');
        assert.equal((await regenerate()).status, 'already regenerated');
        fs.appendFileSync(path.join(directory, 'dist/raw.cjs'), '\n// unexpected local edit');
        const before = inventory(directory);
        await assert.rejects(regenerate(directory), /Unknown OPFS bytes or file set/);
        assert.deepEqual(inventory(directory), before);
        fs.copyFileSync(path.join(root, 'dist/raw.cjs'), path.join(directory, 'dist/raw.cjs'));
        fs.writeFileSync(path.join(directory, 'dist/unexpected.js'), '// unreviewed');
        const extraFileState = inventory(directory);
        await assert.rejects(regenerate(directory), /Unknown OPFS bytes or file set/);
        assert.deepEqual(inventory(directory), extraFileState);
    });
    test('OPFS version and identity changes are rejected without touching dist', async t => {
        const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-opfs-identity-'));
        t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
        fs.cpSync(path.join(root, 'dist'), path.join(directory, 'dist'), { recursive: true });
        const original = fs.readFileSync(path.join(root, 'package.json'), 'utf8');
        for (const change of [{ name: 'different-worker' }, { version: '1.3.2' }]) {
            fs.writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ ...JSON.parse(original), ...change }));
            const bytes = fs.readFileSync(path.join(directory, 'dist/index.js'));
            await assert.rejects(regenerate(directory), /Unexpected OPFS package identity|OPFS changed/);
            assert.deepEqual(fs.readFileSync(path.join(directory, 'dist/index.js')), bytes);
        }
    });
    for (const format of ['js', 'cjs']) test(`OPFS ${format} public exports and bounded matching semantics survive rebuild`, async () => {
        for (const name of ['index', 'raw']) {
            const file = path.join(root, 'dist', `${name}.${format}`);
            const api = format === 'cjs' ? require(file) : await import(pathToFileURL(file).href);
            assert.deepEqual(Object.keys(api).sort(), provenance.publicExports[name]);
            if (name !== 'index') continue;
            const cases = [
                ['/data/a.txt', '**/*.txt', true], ['/data/deep/a.txt', '*.txt', true],
                ['/data/.hidden', '**/*', true], ['/data/a.js', '**/*.txt', false],
                ['/data/a.ts', '**/*.{ts,js}', true], ['/data/a.test.ts', '**/!(*.test).ts', false],
                ['/data/a.ts', '**/!(*.test).ts', true], ['/data/a2.txt', '**/a[0-3].txt', true],
                ['/data/a9.txt', '**/a[0-3].txt', false], ['/data/file.txt', '**/file?.txt', false],
                ['/data/a.txt', '#comment', false], ['/data/a.txt', '!**/*.js', true]
            ];
            for (const [file, pattern, expected] of cases) assert.equal(api.matchMinimatch(file, pattern), expected, `${file}: ${pattern}`);
            assert.equal(api.isPathExcluded('/data/.secret', ['**/.secret']), true);
            assert.equal(api.isPathExcluded('/data/a.txt', ['**/.secret']), false);
        }
    });
}

async function browserSmoke(format) {
    const esbuild = require('esbuild');
    const { default: puppeteer } = await import('puppeteer');
    const rawBundle = await esbuild.build({ entryPoints: [path.join(root, 'dist', `raw.${format}`)], bundle: true, write: false, platform: 'browser', format: 'esm', target: 'es2022', logLevel: 'silent' });
    const result = await esbuild.build({
        stdin: { contents: `import { OPFSFileSystem, matchMinimatch } from ${JSON.stringify(path.join(root, 'dist', `index.${format}`))};
            import { wrap, releaseProxy } from 'comlink';
            globalThis.opfsTestAPI = { OPFSFileSystem, wrap, releaseProxy, matchMinimatch, rawSource: ${JSON.stringify(rawBundle.outputFiles[0].text)} };`, resolveDir: path.resolve(__dirname, '..') },
        bundle: true, write: false, platform: 'browser', format: 'iife', target: 'es2022', logLevel: 'silent'
    });
    // A fresh incognito context plus an ephemeral loopback origin owns all test data.
    const server = http.createServer((_request, response) => {
        response.writeHead(200, { 'Content-Type': 'text/html', 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' });
        response.end('<!doctype html><title>Isolated OPFS regression</title>');
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        browser = await puppeteer.launch({ headless: true, executablePath: process.env.EVIGRAPH_BROWSER_PATH });
        const context = await browser.createBrowserContext();
        try {
            const page = await context.newPage();
            await page.goto(`http://127.0.0.1:${server.address().port}/`);
            await page.addScriptTag({ content: result.outputFiles[0].text });
            const observed = await page.evaluate(async () => {
                const { OPFSFileSystem, wrap, releaseProxy, matchMinimatch, rawSource } = globalThis.opfsTestAPI;
                if (!isSecureContext || !navigator.storage?.getDirectory) throw new Error('Real OPFS unavailable');
                const channel = new BroadcastChannel('owned-opfs-regression');
                const events = [];
                channel.onmessage = event => events.push(event.data.path);
                const ownedRoot = await (await navigator.storage.getDirectory()).getDirectoryHandle('owned-regression', { create: true });
                const constructionErrors = [];
                const captureConstructionError = event => { constructionErrors.push(String(event.reason)); event.preventDefault(); };
                window.addEventListener('unhandledrejection', captureConstructionError);
                // Actual Theia OPFSInitialization returns a string root; the provider passes a channel instance.
                const fs = new OPFSFileSystem({ root: '/owned-regression', broadcastChannel: channel, hashAlgorithm: false });
                await fs.index();
                await new Promise(resolve => setTimeout(resolve, 100));
                window.removeEventListener('unhandledrejection', captureConstructionError);
                if (constructionErrors.length) throw new Error(`Theia constructor initialization failed: ${constructionErrors.join('; ')}`);
                await fs.mkdir('/data', { recursive: true });
                const unwatch = fs.watch('/data', { recursive: true, include: ['**/*.txt'], exclude: ['**/secret*'] });
                // Comlink round trip flushes the synchronous watch snapshot registration.
                await fs.index();
                await fs.writeFile('/data/visible.txt', 'evidence α');
                if (await fs.readFile('/data/visible.txt', 'utf8') !== 'evidence α') throw new Error('Facade text round trip failed');
                const physicalFile = await (await ownedRoot.getDirectoryHandle('data')).getFileHandle('visible.txt');
                if (await (await physicalFile.getFile()).text() !== 'evidence α') throw new Error('Theia string root was ignored');
                await fs.writeFile('/data/secret.txt', 'excluded');
                await fs.writeFile('/data/other.bin', new Uint8Array([0, 127, 255]));
                const bytes = await fs.readFile('/data/other.bin', 'binary');
                if (String([...bytes]) !== '0,127,255') throw new Error('Binary round trip failed');
                const fd = await fs.open('/data/sync.bin', { create: true, truncate: true });
                await fs.write(fd, new Uint8Array([3, 4, 5]), 0, 3, 0, true);
                const read = await fs.read(fd, new Uint8Array(3), 0, 3, 0);
                await fs.close(fd);
                if (read.bytesRead !== 3 || String([...read.buffer]) !== '3,4,5') throw new Error('Sync worker descriptor round trip failed');
                const deadline = Date.now() + 3000;
                while (!events.includes('/data/visible.txt') && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
                if (!events.includes('/data/visible.txt') || events.some(path => /secret|other\.bin|sync\.bin/.test(path))) throw new Error(`Watch include/exclude failed: ${JSON.stringify(events)}`);
                unwatch();
                await fs.index();
                await fs.writeFile('/data/unwatched.txt', 'after unwatch');
                await new Promise(resolve => setTimeout(resolve, 100));
                if (events.includes('/data/unwatched.txt')) throw new Error('Unwatch failed');
                // Also exercise the preserved raw module export against the same fresh origin.
                const workerURL = URL.createObjectURL(new Blob([rawSource], { type: 'text/javascript' }));
                const rawWorker = new Worker(workerURL, { type: 'module' });
                URL.revokeObjectURL(workerURL);
                const raw = wrap(rawWorker);
                await raw.setOptions({ root: '/owned-raw-regression', broadcastChannel: false, hashAlgorithm: false });
                await raw.writeFile('/raw.txt', new TextEncoder().encode('raw text'));
                if (new TextDecoder().decode(await raw.readFile('/raw.txt')) !== 'raw text') throw new Error('Raw entry round trip failed');
                await raw.clear();
                await raw[releaseProxy]();
                rawWorker.terminate();
                await fs.clear();
                channel.close();
                return { worker: 'real module Worker via Blob/Comlink', text: true, binary: true, syncDescriptors: true,
                    watchIncluded: events.filter(path => path === '/data/visible.txt').length, excludedEvents: 0, unwatch: true,
                    rawModule: true, theiaConstructor: 'string root + BroadcastChannel instance', physicalRootVerified: true, ordinaryMatcher: matchMinimatch('/data/a.txt', '*.txt'), privateContext: true };
            });
            console.log(JSON.stringify({ chromium: await browser.version(), format, ...observed }));
            assert.equal(observed.ordinaryMatcher, true);
        } finally { await context.close(); }
    } finally {
        if (browser) await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
}

if (process.argv.includes('--browser')) (async () => { for (const format of ['js', 'cjs']) await browserSmoke(format); })().catch(error => { console.error(error); process.exitCode = 1; });
else registerContracts();
