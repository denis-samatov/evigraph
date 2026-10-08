/** @jsx React.createElement */
import { open, OpenerService } from '@theia/core/lib/browser/opener-service';
import { ReactWidget } from '@theia/core/lib/browser/widgets/react-widget';
import { MessageService } from '@theia/core/lib/common/message-service';
import URI from '@theia/core/lib/common/uri';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import * as React from '@theia/core/shared/react';
import { FileService } from '@theia/filesystem/lib/browser/file-service';
import { WorkspaceService } from '@theia/workspace/lib/browser/workspace-service';
import { api, apiUrl, codePointToUtf16, Concept, EvidenceSpan, ReviewRow, ReviewView } from './api';
import { REVIEW_WIDGET_ID, ReviewOptions } from './review-opener';

const REVIEWER_KEY = 'evigraph.reviewer';

/** Review editor: document text with evidence highlights, suggested concepts and review commands. */
@injectable()
export class ReviewWidget extends ReactWidget {
    @inject(ReviewOptions) protected readonly options: ReviewOptions;
    @inject(MessageService) protected readonly messages: MessageService;
    @inject(FileService) protected readonly files: FileService;
    @inject(WorkspaceService) protected readonly workspace: WorkspaceService;
    @inject(OpenerService) protected readonly openers: OpenerService;

    protected text = '';
    protected view: ReviewView | undefined;
    protected concepts: Concept[] = [];
    protected selected: string | undefined;
    protected spans: EvidenceSpan[] = [];
    protected busy = false;
    protected error = '';
    protected toAdd = '';

    @postConstruct()
    protected init(): void {
        this.id = `${REVIEW_WIDGET_ID}:${this.options.versionId}:${this.options.catalogVersionId}`;
        this.title.label = this.options.title;
        this.title.caption = `Review ${this.options.title}`;
        this.title.iconClass = 'codicon codicon-checklist';
        this.title.closable = true;
        this.addClass('evigraph-review');
        this.load();
    }

    protected get reviewer(): string {
        return window.localStorage.getItem(REVIEWER_KEY) || 'expert';
    }

    protected async load(): Promise<void> {
        await this.run(async () => {
            const [text, view, concepts] = await Promise.all([
                api.text(this.options.versionId),
                api.review(this.options.versionId, this.options.catalogVersionId),
                api.concepts(this.options.catalogVersionId)
            ]);
            this.text = text;
            this.view = view;
            this.concepts = concepts;
            if (this.selected && !view.assertions.some(a => a.assertion_id === this.selected)) {
                this.selected = undefined;
                this.spans = [];
            }
        });
    }

    protected async run(work: () => Promise<void>): Promise<void> {
        this.busy = true;
        this.error = '';
        this.update();
        try {
            await work();
        } catch (e) {
            this.error = `${e instanceof Error ? e.message : e} (API ${apiUrl()})`;
        } finally {
            this.busy = false;
            this.update();
        }
    }

    protected async suggest(): Promise<void> {
        await this.run(() => api.suggest(this.options.versionId, this.options.catalogVersionId).then(() => undefined));
        await this.load();
    }

    protected async select(row: ReviewRow): Promise<void> {
        this.selected = row.assertion_id;
        this.spans = [];
        this.update();
        if (row.score === null) {
            return; // added by an expert: no model evidence
        }
        await this.run(async () => {
            this.spans = await api.evidence(row.assertion_id);
        });
    }

    protected async decide(row: ReviewRow, kind: 'accept' | 'reject' | 'withdraw'): Promise<void> {
        await this.run(() => api.review_(row.assertion_id, kind, row.revision, this.reviewer).then(() => undefined));
        await this.load();
    }

    protected async add(): Promise<void> {
        if (!this.toAdd) {
            return;
        }
        await this.run(() => api.add(this.options.versionId, this.toAdd, this.reviewer).then(() => undefined));
        this.toAdd = '';
        await this.load();
    }

    protected async complete(): Promise<void> {
        await this.run(() => api.complete(this.options.versionId, this.options.catalogVersionId, this.reviewer).then(() => undefined));
        await this.load();
        if (this.view?.completed) {
            this.messages.info(`${this.options.title}: review completed; the document now provides gold labels.`);
        }
    }

    protected async openGraph(): Promise<void> {
        const root = this.workspace.tryGetRoots()[0];
        if (!root) {
            this.messages.warn('Open a workspace folder to store graph views.');
            return;
        }
        const uri = new URI(root.resource.toString()).resolve(`graphs/${this.options.versionId.slice(0, 8)}.evigraph`);
        const descriptor = {
            api: apiUrl(),
            documentVersionId: this.options.versionId,
            catalogVersionId: this.options.catalogVersionId,
            title: this.options.title
        };
        await this.files.write(uri, JSON.stringify(descriptor, undefined, 2));
        await open(this.openers, uri);
    }

    protected renderText(): React.ReactNode {
        if (!this.spans.length) {
            return this.text;
        }
        const map = codePointToUtf16(this.text);
        const ordered = [...this.spans].sort((a, b) => a.start - b.start);
        const parts: React.ReactNode[] = [];
        let pos = 0;
        ordered.forEach((s, i) => {
            const a = map[s.start];
            const b = map[s.end];
            parts.push(this.text.slice(pos, a));
            parts.push(
                <mark key={s.id} className="evigraph-evidence" title={`evidence #${s.rank} · contribution ${s.score.toFixed(3)}`} ref={i === 0 ? scrollIntoView : undefined}>
                    {this.text.slice(a, b)}
                </mark>
            );
            pos = b;
        });
        parts.push(this.text.slice(pos));
        return parts;
    }

    protected render(): React.ReactNode {
        const view = this.view;
        const asserted = new Set(view?.assertions.map(a => a.concept_id));
        const undecided = view?.assertions.filter(a => a.state === 'proposed' || a.state === 'auto_applied').length ?? 0;
        const selectedRow = view?.assertions.find(a => a.assertion_id === this.selected);
        const drop = this.spans[0]?.deletion_drop;
        return (
            <div className="evigraph-review-body">
                <div className="evigraph-review-header">
                    <span className="evigraph-review-title">{this.options.title}</span>
                    {view?.certification ? (
                        <span className="evigraph-chip ok" title="Auto-apply is certified for the active release">
                            certified α={view.certification.alpha} δ={view.certification.delta}
                        </span>
                    ) : (
                        <span className="evigraph-chip" title="No active certification: every tag needs review">suggest &amp; review</span>
                    )}
                    {view?.completed && <span className="evigraph-chip ok">review completed</span>}
                    <span className="evigraph-spacer" />
                    <button className="theia-button secondary" onClick={() => this.suggest()} disabled={this.busy || !view?.release_id}>Suggest</button>
                    <button className="theia-button secondary" onClick={() => this.openGraph()} disabled={this.busy}>Open graph</button>
                    <button className="theia-button" onClick={() => this.complete()} disabled={this.busy || undecided > 0 || view?.completed} title={undecided ? `${undecided} tag(s) still undecided` : ''}>
                        Complete review
                    </button>
                </div>
                {this.error && <div className="evigraph-error">{this.error}</div>}
                <div className="evigraph-review-main">
                    <div className="evigraph-text">{this.renderText()}</div>
                    <div className="evigraph-side">
                        <table className="evigraph-assertions">
                            <thead>
                                <tr><th>Concept</th><th>Score</th><th>Decision</th><th>State</th><th /></tr>
                            </thead>
                            <tbody>
                                {view?.assertions.map(row => (
                                    <tr key={row.assertion_id} className={row.assertion_id === this.selected ? 'selected' : ''} onClick={() => this.select(row)}>
                                        <td title={row.concept_label}><span className="evigraph-key">{row.concept_key}</span>{row.concept_label}</td>
                                        <td>{row.score === null ? '—' : row.score.toFixed(2)}</td>
                                        <td>{row.decision === 'auto_applied' ? 'auto' : row.decision === 'needs_review' ? 'review' : '—'}</td>
                                        <td><span className={`evigraph-state ${row.state}`}>{row.state.replace('_', ' ')}</span></td>
                                        <td className="evigraph-actions" onClick={e => e.stopPropagation()}>
                                            {row.state !== 'accepted' && <button className="theia-button" onClick={() => this.decide(row, 'accept')} disabled={this.busy} title="Accept">✓</button>}
                                            {row.state !== 'rejected' && <button className="theia-button secondary" onClick={() => this.decide(row, 'reject')} disabled={this.busy} title="Reject">✕</button>}
                                            {(row.state === 'accepted' || row.state === 'rejected') && (
                                                <button className="theia-button secondary" onClick={() => this.decide(row, 'withdraw')} disabled={this.busy} title="Withdraw the decision">↺</button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {view && !view.assertions.length && <div className="evigraph-muted">No suggestions yet. Press Suggest.</div>}
                        <div className="evigraph-add">
                            <select value={this.toAdd} onChange={e => { this.toAdd = e.currentTarget.value; this.update(); }}>
                                <option value="">Add a concept the engine missed…</option>
                                {this.concepts.filter(c => !asserted.has(c.id)).map(c => (
                                    <option key={c.id} value={c.id}>{c.key} · {c.label}</option>
                                ))}
                            </select>
                            <button className="theia-button secondary" onClick={() => this.add()} disabled={this.busy || !this.toAdd}>Add</button>
                        </div>
                        {selectedRow && (
                            <div className="evigraph-evidence-panel">
                                <div className="evigraph-muted">
                                    Evidence for <b>{selectedRow.concept_label}</b>
                                    {typeof drop === 'number' && ` · removing these passages lowers the score by ${drop.toFixed(3)}`}
                                </div>
                                {this.spans.map(s => (
                                    <blockquote key={s.id} title={`characters ${s.start}–${s.end} (code points)`}>{s.quote}</blockquote>
                                ))}
                                {!this.spans.length && selectedRow.score !== null && !this.busy && <div className="evigraph-muted">No passage contributes positively.</div>}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    }
}

function scrollIntoView(element: HTMLElement | null): void {
    element?.scrollIntoView({ block: 'center', behavior: 'smooth' });
}
