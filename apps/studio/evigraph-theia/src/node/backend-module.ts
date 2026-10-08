import { GLSPServerContribution } from '@eclipse-glsp/theia-integration/lib/node';
import { ContainerModule } from '@theia/core/shared/inversify';
import { EviGraphServerContribution } from './evigraph-server-contribution';

export default new ContainerModule(bind => {
    bind(EviGraphServerContribution).toSelf().inSingletonScope();
    bind(GLSPServerContribution).toService(EviGraphServerContribution);
});
