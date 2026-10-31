/* Contracts for the actual CLI dependency callers, not the root package resolution. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const vm = require('node:vm');

const cli = createRequire(require.resolve('@theia/cli/package.json'));
const mocha = createRequire(cli.resolve('mocha/package.json'));
const { BufferedWorkerPool } = mocha('./lib/nodejs/buffered-worker-pool.js');

test('Theia CLI resolves the reviewed browser and worker dependencies', () => {
    for (const name of ['puppeteer', 'puppeteer-core']) {
        assert.equal(cli(`${name}/package.json`).version, '25.16.0', `CLI ${name} must use the reviewed minor update`);
    }
    assert.equal(mocha('serialize-javascript/package.json').version, '7.1.4');
});

function checkSpoofedValue(value) {
    let output;
    try {
        output = BufferedWorkerPool.serializeOptions({ grep: value });
    } catch (error) {
        // Intrinsic brand validation may reject objects impersonating native types.
        assert.equal(error.name, 'TypeError');
        return;
    }
    const context = Object.create(null);
    let evaluationError;
    try {
        vm.runInNewContext(`(${output})`, context, { timeout: 1000 });
    } catch (error) {
        evaluationError = error;
    }
    assert.equal(context.cliSerializationInjected, undefined, 'spoofed options executed during worker deserialization');
    // A forged native value may become invalid after unsafe flags are stripped.
    // The worker must fail closed without executing injected code; legitimate
    // values have a separate round-trip and real-worker compatibility contract.
    if (evaluationError) assert.equal(evaluationError.name, 'SyntaxError');
}

test('actual Mocha worker serializer rejects RegExp flags code injection', () => {
    const value = Object.create(RegExp.prototype);
    Object.defineProperties(value, {
        source: { get: () => 'x' },
        flags: { get: () => '"+(globalThis.cliSerializationInjected=1)+"' }
    });
    value.toJSON = () => '@placeholder';
    checkSpoofedValue(value);
});

test('actual Mocha worker serializer rejects Date code injection', () => {
    const value = Object.create(Date.prototype);
    value.toISOString = () => '"+(globalThis.cliSerializationInjected=1)+"';
    value.toJSON = () => '2026-10-31';
    checkSpoofedValue(value);
});

test('worker serialization preserves ordinary RegExp, Date and nested options', () => {
    const result = vm.runInNewContext(
        `(${BufferedWorkerPool.serializeOptions({ grep: /worker-contract/i, date: new Date('2026-10-31T00:00:00Z'), nested: { values: [1, true, null] } })})`
    );
    assert.equal(result.grep.source, 'worker-contract');
    assert.equal(result.grep.flags, 'i');
    assert.equal(result.date.toISOString(), '2026-10-31T00:00:00.000Z');
    assert.equal(JSON.stringify(result.nested), '{"values":[1,true,null]}');
});

test('real Mocha parallel workers preserve pass and failure reporting', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-cli-workers-'));
    try {
        const files = ['first', 'second'].map(name => {
            const file = path.join(dir, `${name}.cjs`);
            fs.writeFileSync(
                file,
                `const assert = require('node:assert/strict'); describe('worker-contract', () => { it('${name}', () => assert.equal(2 + 2, 4)); });`
            );
            return file;
        });
        const command = [
            mocha.resolve('./bin/mocha.js'),
            '--no-config',
            '--no-package',
            '--parallel',
            '--jobs',
            '2',
            '--reporter',
            'json',
            '--grep',
            'worker-contract'
        ];
        const run = () => spawnSync(process.execPath, [...command, ...files], { encoding: 'utf8', timeout: 30000, cwd: dir });
        const positive = run();
        assert.ifError(positive.error);
        assert.equal(positive.status, 0, positive.stderr);
        assert.equal(JSON.parse(positive.stdout).stats.passes, 2);
        fs.writeFileSync(
            files[1],
            "describe('worker-contract', () => { it('negative control', () => { throw new Error('expected worker negative control'); }); });"
        );
        const negative = run();
        assert.ifError(negative.error);
        assert.equal(negative.status, 1, negative.stderr);
        const result = JSON.parse(negative.stdout);
        assert.equal(result.stats.passes, 1);
        assert.equal(result.stats.failures, 1);
        assert.match(result.failures[0].err.message, /expected worker negative control/);
    } finally {
        fs.rmSync(dir, { recursive: true });
    }
});

test('Theia browser test adapter works with sandboxed Chrome and reports a failing fixture', { timeout: 60000 }, async () => {
    const browser = await cli('puppeteer-core').launch({ headless: true, executablePath: process.env.EVIGRAPH_BROWSER_PATH });
    const server = http.createServer((_request, response) => {
        response.setHeader('Content-Type', 'text/html; charset=utf-8');
        response.end(`<!doctype html><title>CLI adapter contract</title><script>
            const readyService = { reachedState: () => Promise.resolve(), ready: Promise.resolve(), roots: Promise.resolve([]) };
            window.theia = {
                '@theia/core/lib/common/logger': { logger: {} },
                '@theia/core/lib/browser/frontend-application-state': { FrontendApplicationStateService: 'state' },
                '@theia/core/lib/common/preferences/preference-service': { PreferenceService: 'preferences' },
                '@theia/workspace/lib/browser/workspace-service': { WorkspaceService: 'workspace' },
                container: { get: () => readyService }
            };
        </script>`);
    });
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-cli-browser-'));
    try {
        await new Promise((resolve, reject) => {
            server.once('error', reject);
            server.listen(0, '127.0.0.1', resolve);
        });
        for (const failing of [false, true]) {
            const file = path.join(dir, 'adapter.cjs');
            fs.writeFileSync(
                file,
                `describe('Theia adapter contract', () => { it('reports result', () => { chai.assert.equal(document.title, ${JSON.stringify(failing ? 'intentional mismatch' : 'CLI adapter contract')}); }); });`
            );
            let page;
            let timer;
            try {
                let didRun;
                let didFail;
                const completion = new Promise((resolve, reject) => {
                    didRun = resolve;
                    didFail = reject;
                });
                page = await cli('./lib/test-page.js').default({
                    files: { spec: [file], extension: ['cjs'] },
                    newPage: () => browser.newPage(),
                    matchAppUrl: url => url.startsWith('http://127.0.0.1:'),
                    onDidRun: didRun
                });
                page.on('pageerror', didFail);
                await page.goto(`http://127.0.0.1:${server.address().port}`);
                timer = setTimeout(() => didFail(new Error('Theia adapter did not report a result')), 30000);
                const failures = await completion;
                assert.equal(failures, failing ? 1 : 0);
            } finally {
                clearTimeout(timer);
                if (page) await page.close();
            }
        }
        console.log(
            JSON.stringify({
                cliBrowser: await browser.version(),
                sandboxEnabled: true,
                fixtureScope: 'synthetic Theia readiness, actual CLI adapter'
            })
        );
    } finally {
        await browser.close();
        await new Promise(resolve => server.close(resolve));
        fs.rmSync(dir, { recursive: true });
    }
});
