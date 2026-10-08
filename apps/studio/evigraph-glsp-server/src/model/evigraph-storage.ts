import { AbstractJsonModelStorage, MaybePromise, RequestModelAction, SaveModelAction } from '@eclipse-glsp/server/node';
import { inject, injectable } from 'inversify';
import { EviGraphFile, fetchGraph } from './evigraph-model';
import { EviGraphModelState } from './evigraph-model-state';

/** Reads the `.evigraph` descriptor and loads the graph from the Core API. Read-only. */
@injectable()
export class EviGraphStorage extends AbstractJsonModelStorage {
    @inject(EviGraphModelState)
    protected override modelState: EviGraphModelState;

    async loadSourceModel(action: RequestModelAction): Promise<void> {
        const file = this.loadFromFile(this.getSourceUri(action), EviGraphFile.is);
        try {
            this.modelState.updateSourceModel({ file, graph: await fetchGraph(file) });
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this.modelState.updateSourceModel({ file, graph: { nodes: [], edges: [] }, error: message });
        }
    }

    saveSourceModel(_action: SaveModelAction): MaybePromise<void> {
        // The graph is a view of Core data; domain changes go through review commands.
    }

    protected override createModelForEmptyFile(_path: string): EviGraphFile {
        return { api: 'http://127.0.0.1:8000', documentVersionId: '', catalogVersionId: '' };
    }
}
