/* Compatibility and bounded cancellation contracts for actual matcher callers. */
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const cli = createRequire(require.resolve('@theia/cli/package.json'));
const mocha = createRequire(cli.resolve('mocha/package.json'));
const filesystem = createRequire(require.resolve('@theia/filesystem/package.json'));
const glspConfig = createRequire(require.resolve('@eclipse-glsp/config/package.json'));
const rimrafCallers = [
    createRequire(glspConfig.resolve('rimraf/package.json')),
    createRequire(filesystem.resolve('rimraf/package.json'))
];
const matcherCallers = ['@theia/filesystem/package.json', '@theia/navigator/package.json', '@eslint/config-array',
    '@typescript-eslint/typescript-estree', 'eslint']
    .map(name => createRequire(require.resolve(name))).concat(mocha);

function fixture(t) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'evigraph-matching-'));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    return root;
}

test('reviewed modern callers resolve compatible patched matching releases', () => {
    for (const caller of [cli, mocha, ...rimrafCallers]) {
        assert.equal(caller('glob/package.json').version, '14.0.3');
        assert.equal(typeof caller('glob').glob.sync, 'function');
    }
    for (const caller of matcherCallers) assert.equal(caller('minimatch/package.json').version, '11.0.3');
    // Callback-style legacy glob retains its own callable matcher; never force
    // the modern named-export API into that unqualified legacy consumer.
    const legacy = createRequire(require.resolve('globby/package.json'));
    const legacyGlob = createRequire(legacy.resolve('glob/package.json'));
    assert.equal(typeof legacyGlob('minimatch'), 'function');
});

test('actual matcher callers preserve brace, extglob, globstar, dot and case options', () => {
    for (const caller of matcherCallers) {
        const { minimatch, Minimatch } = caller('minimatch');
        assert.equal(minimatch('src/deep/app.ts', '**/*.{ts,js}'), true);
        assert.equal(minimatch('src/deep/app.txt', '**/*.{ts,js}'), false);
        assert.equal(minimatch('src/app.test.ts', '**/!(*.test).ts'), false);
        assert.equal(minimatch('src/app.ts', '**/!(*.test).ts'), true);
        assert.equal(new Minimatch('**/*', { dot: true }).match('.config/file'), true);
        assert.equal(new Minimatch('**/*').match('.config/file'), false);
        assert.equal(new Minimatch('**/*.TS', { nocase: true }).match('src/app.ts'), true);
    }
    const search = filesystem('./lib/browser-only/file-search.js');
    assert.equal(search.normalizeGlob('src\\*.ts'), '**/src/*.ts');
    assert.equal(search.matchesPattern('src/app.ts', ['**/*.ts']), true);
    assert.equal(search.matchesPattern('src/app.js', ['**/*.ts']), false);
});

test('actual Mocha lookup preserves deterministic owned test-file discovery', t => {
    const root = fixture(t);
    fs.mkdirSync(path.join(root, 'nested'));
    for (const name of ['a.cjs', 'nested/b.cjs', 'nested/skip.ts', '.hidden.cjs']) fs.writeFileSync(path.join(root, name), '');
    const lookup = mocha('./lib/cli/lookup-files.js');
    assert.deepEqual(lookup(path.join(root, '**/*.cjs'), ['cjs'], true), [path.join(root, 'a.cjs'), path.join(root, 'nested/b.cjs')]);
});

test('actual Theia dependency checker discovers owned workspaces using glob.sync', t => {
    const root = fixture(t);
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ name: 'owned-root', workspaces: ['packages/*'] }));
    for (const name of ['first', 'second']) {
        const dir = path.join(root, 'packages', name);
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ name, version: '1.0.0' }));
    }
    const checker = cli.resolve('./lib/check-dependencies.js');
    const code = `require(${JSON.stringify(checker)}).default({include:['**'],exclude:[],onlyTheiaExtensions:false});`;
    const result = spawnSync(process.execPath, ['-e', code], { cwd: root, encoding: 'utf8', timeout: 10000 });
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Found 2 workspaces/);
    assert.match(result.stdout, /No issues were found/);
});

test('actual modern rimraf callers restrict wildcard cleanup to owned fixture matches', async t => {
    for (const caller of rimrafCallers) {
        const root = fixture(t);
        fs.mkdirSync(path.join(root, 'nested'));
        fs.writeFileSync(path.join(root, 'one.tmp'), 'owned temporary');
        fs.writeFileSync(path.join(root, 'keep.txt'), 'preserved');
        fs.writeFileSync(path.join(root, 'nested', 'keep.tmp'), 'preserved nested');
        await caller('.').rimraf(path.join(root, '*.tmp'), { glob: true });
        assert.equal(fs.existsSync(path.join(root, 'one.tmp')), false);
        assert.equal(fs.readFileSync(path.join(root, 'keep.txt'), 'utf8'), 'preserved');
        assert.equal(fs.readFileSync(path.join(root, 'nested', 'keep.tmp'), 'utf8'), 'preserved nested');
    }
});

test('actual Mocha glob stops scheduling reads after a controlled abort', async t => {
    const root = fixture(t);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) fs.mkdirSync(path.join(root, `d${i}`, `n${j}`), { recursive: true });
    const controller = new AbortController();
    const reason = new Error('owned cancellation contract');
    let readsAfterAbort = 0;
    let reads = 0;
    let pending = 0;
    const completed = [];
    const instrumented = {
        ...fs,
        readdir(file, options, callback) {
            reads++;
            if (controller.signal.aborted) readsAfterAbort++;
            pending++;
            fs.readdir(file, options, (error, entries) => {
                if (!controller.signal.aborted) controller.abort(reason);
                callback(error, entries);
                pending--;
                if (pending === 0) completed.splice(0).forEach(resolve => resolve());
            });
        }
    };
    await assert.rejects(mocha('glob').glob('**/*', { cwd: root, fs: instrumented, signal: controller.signal }), error => error === reason);
    if (pending) await new Promise(resolve => completed.push(resolve));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(reads, 1, 'only the initial read should have been scheduled');
    assert.equal(readsAfterAbort, 0, 'aborted traversal must not schedule descendant reads');
});

// This consumer needs makeRe, removed in minimatch11. Preserve compatibility
// rather than disguising its still-open legacy advisory behind a broad override.
test('actual import-x ESM entry and configured no-internal-modules rule remain usable', async () => {
    const { pathToFileURL } = require('node:url');
    const manifestPath = require.resolve('eslint-plugin-import-x/package.json');
    const pluginCaller = createRequire(manifestPath);
    const esm = path.join(path.dirname(manifestPath), 'lib/index.js');
    const module = await import(pathToFileURL(esm).href);
    assert.ok(module.default.rules['no-internal-modules']);
    assert.equal(typeof pluginCaller('minimatch').makeRe, 'function');
    const { Linter } = require('eslint');
    const messages = new Linter().verify("import value from 'owned-package/internal';", [{
        plugins: { 'import-x': module.default },
        rules: { 'import-x/no-internal-modules': ['error', { forbid: ['owned-package/*'] }] }
    }]);
    assert.equal(messages.length, 1);
    assert.equal(messages[0].ruleId, 'import-x/no-internal-modules');
    assert.equal(messages[0].messageId, 'noAllowed');
});
