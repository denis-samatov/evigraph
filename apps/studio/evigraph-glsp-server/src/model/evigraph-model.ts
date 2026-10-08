/**
 * A `.evigraph` file names a document version and a catalog version; the graph itself is read
 * from the EviGraph Core API (`GET /document-versions/{id}/graph`).
 */
export interface EviGraphFile {
    api: string;
    documentVersionId: string;
    catalogVersionId: string;
    title?: string;
}

export interface GraphNode {
    id: string;
    kind: 'document' | 'concept' | 'reviewed_document' | 'copy';
    label: string;
    state?: string | null;
    score?: number | null;
}

export interface GraphEdge {
    id: string;
    source: string;
    target: string;
    kind: 'asserts' | 'supported_by' | 'same_provenance';
    weight?: number | null;
}

export interface LocalGraph {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export namespace EviGraphFile {
    export function is(object: unknown): object is EviGraphFile {
        const o = object as Partial<EviGraphFile> | undefined;
        return !!o && typeof o.api === 'string' && typeof o.documentVersionId === 'string' && typeof o.catalogVersionId === 'string';
    }
}

export async function fetchGraph(file: EviGraphFile): Promise<LocalGraph> {
    const url = new URL(`/document-versions/${file.documentVersionId}/graph`, file.api);
    url.searchParams.set('catalog_version_id', file.catalogVersionId);
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`EviGraph Core returned ${response.status} for ${url}`);
    }
    return (await response.json()) as LocalGraph;
}
