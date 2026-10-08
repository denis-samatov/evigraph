import { ContainerContext, DiagramConfiguration, GLSPTheiaFrontendModule } from '@eclipse-glsp/theia-integration';
import { EviGraphLanguage } from '../common/evigraph-language';
import { EviGraphDiagramConfiguration } from './evigraph-diagram-configuration';

export class EviGraphTheiaFrontendModule extends GLSPTheiaFrontendModule {
    readonly diagramLanguage = EviGraphLanguage;

    bindDiagramConfiguration(context: ContainerContext): void {
        context.bind(DiagramConfiguration).to(EviGraphDiagramConfiguration);
    }
}

export default new EviGraphTheiaFrontendModule();
