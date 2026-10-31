/* Reproducible, deliberately version-bound security backport; see docs/DEPENDENCY_SECURITY.md. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');

const MONACO_VERSION = '1.108.201';
const PURIFY_VERSION = '3.4.17';
const ORIGINAL_HASH = '7b0d9a951d2d5b886080ceb56eed060bbffc2ca3d88e7131e6c18f749fd32661';
const PATCHED_SOURCE_HASH = 'e89caec0717b7c1726e819b480133beaa1cdf7439c22fbfb753e5688be6922c3';
const MARKER = 'EviGraph Monaco sanitizer security backport: DOMPurify 3.4.17';
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

function regenerate(monacoRoot, purifyRoot) {
    const monaco = JSON.parse(fs.readFileSync(path.join(monacoRoot, 'package.json'), 'utf8'));
    const purify = JSON.parse(fs.readFileSync(path.join(purifyRoot, 'package.json'), 'utf8'));
    assert.equal(monaco.version, MONACO_VERSION, 'Monaco changed: review or retire the backport');
    assert.equal(purify.version, PURIFY_VERSION, 'DOMPurify changed: review the pinned source');
    const source = fs.readFileSync(path.join(purifyRoot, 'dist/purify.cjs.js'));
    assert.equal(sha256(source), PATCHED_SOURCE_HASH, 'Official DOMPurify source hash changed');
    // Theia's published Monaco artifact uses CommonJS plus a default interop export.
    // Keep official code/license intact; remove only the now-invalid source-map URL.
    const output = Buffer.from(
        `/*! ${MARKER} */\n` +
            source.toString('utf8').replace(/\n\/\/# sourceMappingURL=purify\.cjs\.js\.map\s*$/, '\n') +
            '\nmodule.exports.default = module.exports;\n'
    );
    const target = path.join(monacoRoot, 'esm/vs/base/browser/dompurify/dompurify.js');
    const current = fs.readFileSync(target);
    if (current.equals(output)) {
        return { status: 'already regenerated', sha256: sha256(output) };
    }
    assert.equal(sha256(current), ORIGINAL_HASH, 'Unknown Monaco sanitizer bytes: refusing to overwrite');
    fs.writeFileSync(target, output);
    return { status: 'regenerated', sha256: sha256(output) };
}

if (require.main === module) {
    const monacoRoot = path.dirname(require.resolve('@theia/monaco-editor-core/package.json'));
    const purifyRoot = path.dirname(path.dirname(require.resolve('dompurify')));
    assert.equal(
        createRequire(path.join(monacoRoot, 'package.json'))('dompurify').version,
        PURIFY_VERSION,
        'Monaco nested dependency resolution is not patched'
    );
    console.log(JSON.stringify(regenerate(monacoRoot, purifyRoot)));
}

module.exports = { regenerate, MARKER };
