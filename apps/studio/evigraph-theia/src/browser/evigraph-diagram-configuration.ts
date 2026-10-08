import { ContainerConfiguration } from '@eclipse-glsp/client';
import { GLSPDiagramConfiguration } from '@eclipse-glsp/theia-integration/lib/browser';
import { Container, injectable } from '@theia/core/shared/inversify';
import { initializeEviGraphDiagramContainer } from 'evigraph-glsp-client/lib/evigraph-diagram-module';
import { EviGraphLanguage } from '../common/evigraph-language';

@injectable()
export class EviGraphDiagramConfiguration extends GLSPDiagramConfiguration {
    readonly diagramType = EviGraphLanguage.diagramType;

    override configureContainer(container: Container, ...containerConfiguration: ContainerConfiguration): void {
        initializeEviGraphDiagramContainer(container, ...containerConfiguration);
    }
}
