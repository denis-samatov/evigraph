/* Version-bound ESM compatibility bridge; see docs/DEPENDENCY_SECURITY.md. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');

const CLI_VERSION = '1.74.3';
const EXTRACTOR_NAME = '@xhmikosr/decompress';
const EXTRACTOR_VERSION = '11.1.4';
const ORIGINAL_HASH = '52335c9cc0cf79fb970980ecadabf1897dc8adee9a92a5ff881b5647d35e53ce';
const EXTRACTOR_HASH = 'ff74d8df401b20cf5097d33862049d1d781ebbe1c386bb86197a8e0664e17f0d';
const ORIGINAL_IMPORT = 'const decompress = require("decompress");';
const BRIDGE_IMPORT = "const decompress = (...args) => import('decompress').then(({ default: extract }) => extract(...args));";
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

function regenerate(cliRoot, extractorRoot) {
    const cli = JSON.parse(fs.readFileSync(path.join(cliRoot, 'package.json'), 'utf8'));
    const extractor = JSON.parse(fs.readFileSync(path.join(extractorRoot, 'package.json'), 'utf8'));
    assert.equal(cli.version, CLI_VERSION, 'Theia CLI changed: review or retire the bridge');
    assert.equal(extractor.name, EXTRACTOR_NAME, 'CLI extractor is not the reviewed maintained package');
    assert.equal(extractor.version, EXTRACTOR_VERSION, 'CLI extractor changed: review the bridge');
    assert.equal(sha256(fs.readFileSync(path.join(extractorRoot, 'index.js'))), EXTRACTOR_HASH, 'Reviewed extractor source hash changed');
    const target = path.join(cliRoot, 'lib/download-plugins.js');
    const current = fs.readFileSync(target, 'utf8');
    // Reverse only the exact bridge to recognize our output, then verify all
    // upstream bytes. No substring/marker alone can authorize an overwrite.
    const original = current.includes(BRIDGE_IMPORT) ? current.replace(BRIDGE_IMPORT, ORIGINAL_IMPORT) : current;
    assert.equal(sha256(original), ORIGINAL_HASH, 'Unknown Theia downloader bytes: refusing to overwrite');
    const output = original.replace(ORIGINAL_IMPORT, BRIDGE_IMPORT);
    assert.notEqual(original, output, 'Reviewed extractor import was not found');
    if (current === output) return { status: 'already regenerated', sha256: sha256(output) };
    fs.writeFileSync(target, output);
    return { status: 'regenerated', sha256: sha256(output) };
}

if (require.main === module) {
    const cliRoot = path.dirname(require.resolve('@theia/cli/package.json'));
    const cli = createRequire(path.join(cliRoot, 'package.json'));
    const extractorRoot = path.dirname(cli.resolve('decompress'));
    console.log(JSON.stringify(regenerate(cliRoot, extractorRoot)));
}

module.exports = { regenerate };
