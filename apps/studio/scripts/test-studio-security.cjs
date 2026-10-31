/* Execute the actual Monaco sanitizer in Chromium; inspect the shipped Studio assets too. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { MARKER } = require('./prepare-monaco-sanitizer.cjs');

async function main() {
    const esbuild = require('esbuild');
    const { default: puppeteer } = await import('puppeteer');
    const entry = require.resolve('@theia/monaco-editor-core/esm/vs/base/browser/domSanitize.js');
    const result = await esbuild.build({
        stdin: {
            contents: `import { sanitizeHtml } from ${JSON.stringify(entry)}; globalThis.sanitizeStudioHtml = sanitizeHtml;`,
            resolveDir: process.cwd()
        },
        bundle: true,
        write: false,
        platform: 'browser',
        format: 'iife',
        target: 'es2022'
    });
    const browser = await puppeteer.launch({ headless: true, executablePath: process.env.EVIGRAPH_BROWSER_PATH });
    try {
        const page = await browser.newPage();
        await page.setRequestInterception(true);
        page.on('request', request => request.abort());
        await page.setContent('<!doctype html><html><body></body></html>');
        await page.addScriptTag({ content: result.outputFiles[0].text });
        const observed = await page.evaluate(async () => {
            const payloads = [
                '<img src=x onerror="window.studioXss=1"><script>window.studioXss=1</script>',
                '<a href="jav&#x61;script:window.studioXss=1" onclick="window.studioXss=1">link</a>',
                '<svg onload="window.studioXss=1"><a xlink:href="javascript:window.studioXss=1">x</a></svg>',
                '<iframe srcdoc="<img src=x onerror=parent.studioXss=1>"></iframe><object data="javascript:window.studioXss=1"></object>',
                '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=window.studioXss=1>">',
                '<form id="attributes"><input name="innerHTML"><img src=x onerror="window.studioXss=1"></form>'
            ];
            window.studioXss = 0;
            for (const payload of payloads) {
                const host = document.createElement('div');
                host.innerHTML = String(window.sanitizeStudioHtml(payload));
                // Check the reparsed DOM, including mutation payloads, rather than a string regex only.
                for (const node of host.querySelectorAll('*')) {
                    if (['SCRIPT', 'IFRAME', 'OBJECT', 'SVG', 'MATH', 'FORM', 'INPUT'].includes(node.tagName)) {
                        throw new Error(`Executable/foreign element retained: ${node.tagName}`);
                    }
                    for (const attr of node.attributes) {
                        if (/^on/i.test(attr.name) || /^(?:javascript|vbscript):/i.test(attr.value.trim())) {
                            throw new Error(`Executable attribute retained: ${attr.name}`);
                        }
                    }
                }
                document.body.append(host);
            }
            await new Promise(resolve => setTimeout(resolve, 100));
            if (window.studioXss !== 0) throw new Error('Hostile content executed');
            const safe = document.createElement('div');
            safe.innerHTML = String(
                window.sanitizeStudioHtml('<p>Evidence <em>quote</em> <a href="https://example.invalid/source">source</a></p>')
            );
            if (
                safe.querySelector('em')?.textContent !== 'quote' ||
                safe.querySelector('a')?.getAttribute('href') !== 'https://example.invalid/source'
            ) {
                throw new Error('Benign markup/link compatibility changed');
            }
            return { hostileCases: payloads.length, executed: window.studioXss, benignMarkup: 'preserved' };
        });
        console.log(JSON.stringify({ chromium: await browser.version(), ...observed }));
    } finally {
        await browser.close();
    }
    const frontend = path.resolve('evigraph-studio-app/lib/frontend');
    for (const name of ['bundle.js', 'secondary-window.js']) {
        const bytes = fs.readFileSync(path.join(frontend, name));
        const text = bytes.toString('utf8');
        assert(text.includes(MARKER), `${name}: reviewed sanitizer backport absent; rebuild required`);
        assert(!/DOMPurify 3\.2\.7|DOMPurify\w*\.version\s*=\s*["']3\.2\.7/.test(text), `${name}: vulnerable bundled sanitizer remains`);
        console.log(
            JSON.stringify({ asset: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), patchedSanitizer: true })
        );
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
