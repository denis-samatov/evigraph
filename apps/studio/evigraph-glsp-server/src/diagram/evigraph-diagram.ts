import {
    ActionHandlerConstructor,
    BindingTarget,
    ComputedBoundsActionHandler,
    DefaultTypes,
    DiagramConfiguration,
    DiagramModule,
    EdgeTypeHint,
    getDefaultMapping,
    GModelElement,
    GModelElementConstructor,
    GModelFactory,
    InstanceMultiBinding,
    ModelState,
    ServerLayoutKind,
    ShapeTypeHint,
    SourceModelStorage
} from '@eclipse-glsp/server';
import { injectable } from 'inversify';
import { EviGraphGModelFactory } from '../model/evigraph-gmodel-factory';
import { EviGraphModelState } from '../model/evigraph-model-state';
import { EviGraphStorage } from '../model/evigraph-storage';

/** Read-only diagram: nodes and edges cannot be created, deleted, moved or resized. */
@injectable()
export class EviGraphDiagramConfiguration implements DiagramConfiguration {
    layoutKind = ServerLayoutKind.MANUAL;
    needsClientLayout = true;
    animatedUpdate = true;

    get typeMapping(): Map<string, GModelElementConstructor<GModelElement>> {
        return getDefaultMapping();
    }

    get shapeTypeHints(): ShapeTypeHint[] {
        return [{ elementTypeId: DefaultTypes.NODE, deletable: false, reparentable: false, repositionable: false, resizable: false }];
    }

    get edgeTypeHints(): EdgeTypeHint[] {
        return [
            {
                elementTypeId: DefaultTypes.EDGE,
                deletable: false,
                repositionable: false,
                routable: false,
                sourceElementTypeIds: [DefaultTypes.NODE],
                targetElementTypeIds: [DefaultTypes.NODE]
            }
        ];
    }
}

@injectable()
export class EviGraphDiagramModule extends DiagramModule {
    readonly diagramType = 'evigraph-diagram';

    protected bindDiagramConfiguration(): BindingTarget<DiagramConfiguration> {
        return EviGraphDiagramConfiguration;
    }

    protected bindSourceModelStorage(): BindingTarget<SourceModelStorage> {
        return EviGraphStorage;
    }

    protected bindModelState(): BindingTarget<ModelState> {
        return { service: EviGraphModelState };
    }

    protected bindGModelFactory(): BindingTarget<GModelFactory> {
        return EviGraphGModelFactory;
    }

    protected override configureActionHandlers(binding: InstanceMultiBinding<ActionHandlerConstructor>): void {
        super.configureActionHandlers(binding);
        binding.add(ComputedBoundsActionHandler);
    }
}
