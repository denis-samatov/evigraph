import { GLSPSocketServerContribution, GLSPSocketServerContributionOptions } from '@eclipse-glsp/theia-integration/lib/node';
import { injectable } from 'inversify';
import { createRequire } from 'node:module';
import * as path from 'path';
import { EviGraphLanguage } from '../common/evigraph-language';

const DEFAULT_PORT = 0;
const PORT_ARG_KEY = 'EVIGRAPH_GLSP';
export const LOG_DIR = path.join(__dirname, '..', '..', 'logs');
// Resolved at runtime so the bundler does not inline the GLSP server into the Theia backend.
const MODULE_PATH = createRequire(__filename).resolve('evigraph-glsp-server');

@injectable()
export class EviGraphServerContribution extends GLSPSocketServerContribution {
    readonly id = EviGraphLanguage.contributionId;

    createContributionOptions(): Partial<GLSPSocketServerContributionOptions> {
        return {
            executable: MODULE_PATH,
            socketConnectionOptions: { port: getPort(PORT_ARG_KEY, DEFAULT_PORT), host: '127.0.0.1' },
            additionalArgs: ['--no-consoleLog', '--fileLog', '--logDir', LOG_DIR]
        };
    }
}

export function getPort(argsKey: string, defaultPort?: number): number {
    argsKey = `--${argsKey.replace('--', '').replace('=', '')}=`;
    const args = process.argv.filter(a => a.startsWith(argsKey));
    if (args.length > 0) {
        return Number.parseInt(args[0].substring(argsKey.length), 10);
    }
    return defaultPort ?? NaN;
}
