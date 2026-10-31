/* Local returned-object hardening, not an upstream fixed release; see docs/DEPENDENCY_SECURITY.md. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const VERSION = '4.3.1';
const HASHES = {
    'index.js': ['12440c84957c1990ea2d5e33dc0091722dc1dc1585c6d20e0c780e568ffa9d30', '2270f84aba34ce469af96e5ebf9d6703854b1463f6450b50c12bd958500ae07e'],
    'dist/cjs.js': ['2e5160f84a1141bd927264afe4d15766f1e6cf07daef182b37ff53fea121de7d', 'a18bc1bcb0a285eed2280c1aae3c23bd9cd61bf3c3038dc06706bbbee19c9f42'],
    'dist/umd.js': ['f33e6596482d1fb5c7c427f8ef92f2aa849eea9223acd974176b2fb27ddbf73a', 'ac73e83bcfefd4e39e9a2bee3d7ec478b3ba558c2ef71647d691b9737f6360e8']
};
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

function regenerate(root) {
    const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
    assert.equal(metadata.name, 'deepmerge', 'Unexpected deepmerge package identity');
    assert.equal(metadata.version, VERSION, 'deepmerge changed: review or retire local hardening');
    // Validate every entry point before writing any. Keep the upstream version,
    // license, merge policy and safe-key data; only avoid invoking inherited
    // setters when writing properties on the fresh destination object.
    const plans = Object.entries(HASHES).map(([file, [originalHash, patchedHash]]) => {
        const target = path.join(root, file);
        const current = fs.readFileSync(target, 'utf8');
        const hash = sha256(current);
        if (hash === patchedHash) return { file, target, output: current, changed: false };
        assert.equal(hash, originalHash, `Unknown deepmerge bytes in ${file}: refusing to overwrite`);
        let count = 0;
        const output = current.replace(/destination\[key\] = ([^\n;]+)(;?)/g, (_match, value, semicolon) => {
            count++;
            return `Object.defineProperty(destination, key, { value: ${value}, enumerable: true, configurable: true, writable: true })${semicolon}`;
        });
        assert.equal(count, 3, `Reviewed destination assignments changed in ${file}`);
        assert.equal(sha256(output), patchedHash, `Unexpected local hardening output in ${file}`);
        return { file, target, output, changed: true };
    });
    for (const plan of plans) {
        if (plan.changed) fs.writeFileSync(plan.target, plan.output);
    }
    return {
        status: plans.some(plan => plan.changed) ? 'regenerated' : 'already regenerated',
        sha256: Object.fromEntries(plans.map(plan => [plan.file, sha256(plan.output)]))
    };
}

if (require.main === module) {
    console.log(JSON.stringify(regenerate(path.dirname(require.resolve('deepmerge/package.json')))));
}

module.exports = { regenerate };
