import { DefaultModelState, JsonModelState } from '@eclipse-glsp/server';
import { injectable } from 'inversify';
import { EviGraphFile, LocalGraph } from './evigraph-model';

export interface EviGraphSource {
    file: EviGraphFile;
    graph: LocalGraph;
    error?: string;
}

@injectable()
export class EviGraphModelState extends DefaultModelState implements JsonModelState<EviGraphSource> {
    protected source: EviGraphSource;

    get sourceModel(): EviGraphSource {
        return this.source;
    }

    updateSourceModel(source: EviGraphSource): void {
        this.source = source;
    }
}
