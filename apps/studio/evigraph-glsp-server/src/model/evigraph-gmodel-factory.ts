import { GEdge, GGraph, GLabel, GModelFactory, GNode } from '@eclipse-glsp/server';
import { inject, injectable } from 'inversify';
import { GraphNode } from './evigraph-model';
import { EviGraphModelState } from './evigraph-model-state';

const NODE_WIDTH = 190;
const NODE_HEIGHT = 44;

/**
 * Radial layout: the document in the centre, its concepts on the first ring, the reviewed
 * documents supporting them on the outer ring, other members of its provenance group on the left.
 */
export function layout(nodes: GraphNode[], edges: { source: string; target: string; kind: string }[]): Map<string, { x: number; y: number }> {
    const pos = new Map<string, { x: number; y: number }>();
    const centre = { x: 0, y: 0 };
    const ring = (a: number, rx: number, ry: number) => ({ x: centre.x + rx * Math.cos(a), y: centre.y + ry * Math.sin(a) });
    const doc = nodes.find(n => n.kind === 'document');
    if (doc) {
        pos.set(doc.id, centre);
    }
    const concepts = nodes.filter(n => n.kind === 'concept');
    const angle = new Map<string, number>();
    concepts.forEach((n, i) => {
        const a = (2 * Math.PI * i) / Math.max(concepts.length, 1) - Math.PI / 2;
        angle.set(n.id, a);
        pos.set(n.id, ring(a, 330, 190));
    });
    // reviewed documents: towards the concepts they support, spread so they never overlap
    const outer = nodes
        .filter(n => n.kind === 'reviewed_document')
        .map(n => {
            const parents = edges.filter(e => e.target === n.id && e.kind === 'supported_by').map(e => angle.get(e.source) ?? 0);
            const x = parents.reduce((s, a) => s + Math.cos(a), 0);
            const y = parents.reduce((s, a) => s + Math.sin(a), 0);
            return { n, a: parents.length ? Math.atan2(y, x) : 0 };
        })
        .sort((p, q) => p.a - q.a);
    const gap = Math.min(0.42, (2 * Math.PI) / Math.max(outer.length, 1));
    for (let i = 1; i < outer.length; i++) {
        outer[i].a = Math.max(outer[i].a, outer[i - 1].a + gap);
    }
    outer.forEach(({ n, a }) => pos.set(n.id, ring(a, 640, 340)));
    nodes.filter(n => n.kind === 'copy').forEach((n, i) => pos.set(n.id, { x: centre.x - 900, y: centre.y - 40 + i * 64 }));
    const xs = [...pos.values()].map(p => p.x);
    const ys = [...pos.values()].map(p => p.y);
    const dx = 40 - Math.min(...xs) + NODE_WIDTH / 2;
    const dy = 40 - Math.min(...ys) + NODE_HEIGHT / 2;
    pos.forEach((p, k) => pos.set(k, { x: p.x + dx - NODE_WIDTH / 2, y: p.y + dy - NODE_HEIGHT / 2 }));
    return pos;
}

const STATE_MARK: Record<string, string> = { accepted: ' ✓', rejected: ' ✕', auto_applied: ' auto', proposed: '' };

function shorten(text: string, max = 38): string {
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

@injectable()
export class EviGraphGModelFactory implements GModelFactory {
    @inject(EviGraphModelState)
    protected modelState: EviGraphModelState;

    createModel(): void {
        const { graph, error, file } = this.modelState.sourceModel;
        const pos = layout(graph.nodes, graph.edges);
        const children = [];
        if (error) {
            children.push(
                GNode.builder()
                    .id('error')
                    .addCssClass('evigraph-error')
                    .add(GLabel.builder().id('error_label').text(`Cannot load graph: ${error}`).build())
                    .layout('hbox')
                    .position({ x: 20, y: 20 })
                    .build()
            );
        }
        for (const n of graph.nodes) {
            const score = typeof n.score === 'number' ? ` ${n.score.toFixed(2)}` : '';
            const state = n.state ? STATE_MARK[n.state] ?? '' : '';
            const builder = GNode.builder()
                .id(n.id)
                .addCssClass('evigraph-node')
                .addCssClass(`evigraph-${n.kind}`)
                .add(GLabel.builder().id(`${n.id}_label`).text(`${shorten(n.label)}${score}${state}`).build())
                .layout('hbox')
                .addLayoutOptions({ paddingLeft: 8, paddingRight: 8, prefWidth: NODE_WIDTH, prefHeight: NODE_HEIGHT })
                .position(pos.get(n.id) ?? { x: 0, y: 0 });
            if (n.state) {
                builder.addCssClass(`evigraph-state-${n.state}`);
            }
            children.push(builder.build());
        }
        for (const e of graph.edges) {
            children.push(
                GEdge.builder().id(e.id).addCssClass(`evigraph-edge-${e.kind}`).sourceId(e.source).targetId(e.target).build()
            );
        }
        const root = GGraph.builder()
            .id(`graph:${file.documentVersionId}`)
            .addChildren(children)
            .build();
        this.modelState.updateRoot(root);
    }
}
