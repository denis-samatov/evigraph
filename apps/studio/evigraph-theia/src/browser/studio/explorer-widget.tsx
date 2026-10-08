/** @jsx React.createElement */
import { ReactWidget } from '@theia/core/lib/browser/widgets/react-widget';
import { MessageService } from '@theia/core/lib/common/message-service';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import * as React from '@theia/core/shared/react';
import { api, apiUrl, CatalogSummary, DocumentSummary, Project } from './api';
import { ReviewOpener } from './review-opener';

/** Left panel: project -> published catalog version -> documents. */
@injectable()
export class ExplorerWidget extends ReactWidget {
    static readonly ID = 'evigraph-explorer';
    static readonly LABEL = 'EviGraph';

    @inject(MessageService) protected readonly messages: MessageService;
    @inject(ReviewOpener) protected readonly opener: ReviewOpener;

    protected projects: Project[] = [];
    protected catalogs: CatalogSummary[] = [];
    protected documents: DocumentSummary[] = [];
    protected projectId = '';
    protected catalogVersionId = '';
    protected error = '';
    protected loading = false;

    @postConstruct()
    protected init(): void {
        this.id = ExplorerWidget.ID;
        this.title.label = ExplorerWidget.LABEL;
        this.title.caption = 'EviGraph projects and documents';
        this.title.iconClass = 'codicon codicon-type-hierarchy-sub';
        this.title.closable = true;
        this.addClass('evigraph-explorer');
        this.reload();
    }

    async reload(): Promise<void> {
        await this.run(async () => {
            this.projects = await api.projects();
            if (!this.projectId && this.projects.length) {
                await this.selectProject(this.projects[0].id, false);
            }
        });
    }

    protected async selectProject(projectId: string, wrap = true): Promise<void> {
        const work = async (): Promise<void> => {
            this.projectId = projectId;
            this.catalogs = await api.catalogs(projectId);
            const published = this.catalogs.flatMap(c => c.versions.filter(v => v.status === 'published'));
            this.catalogVersionId = published[0]?.id ?? '';
            this.documents = await api.documents(projectId);
        };
        return wrap ? this.run(work) : work();
    }

    protected async run(work: () => Promise<void>): Promise<void> {
        this.loading = true;
        this.error = '';
        this.update();
        try {
            await work();
        } catch (e) {
            this.error = `${e instanceof Error ? e.message : e} (API ${apiUrl()})`;
        } finally {
            this.loading = false;
            this.update();
        }
    }

    protected render(): React.ReactNode {
        const versions = this.catalogs.flatMap(c =>
            c.versions.filter(v => v.status === 'published').map(v => ({ id: v.id, label: `${c.name} v${v.version}` }))
        );
        return (
            <div className="evigraph-explorer-body">
                <div className="evigraph-toolbar">
                    <select value={this.projectId} onChange={e => this.selectProject(e.currentTarget.value)} title="Project">
                        {this.projects.map(p => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                    </select>
                    <button className="theia-button secondary" onClick={() => this.reload()} title="Reload">↻</button>
                </div>
                {versions.length > 0 && (
                    <select value={this.catalogVersionId} onChange={e => { this.catalogVersionId = e.currentTarget.value; this.update(); }} title="Catalog version">
                        {versions.map(v => (
                            <option key={v.id} value={v.id}>{v.label}</option>
                        ))}
                    </select>
                )}
                {this.error && <div className="evigraph-error">{this.error}</div>}
                {this.loading && <div className="evigraph-muted">Loading…</div>}
                <ul className="evigraph-doc-list">
                    {this.documents.map(d => (
                        <li
                            key={d.version_id}
                            onClick={() =>
                                this.catalogVersionId
                                    ? this.opener.open({ versionId: d.version_id, catalogVersionId: this.catalogVersionId, title: d.title ?? d.version_id.slice(0, 8) })
                                    : this.messages.warn('Publish a catalog version first.')
                            }
                            title={`${d.chars} characters · provenance: ${d.provenance_reason}`}
                        >
                            <span className="evigraph-doc-title">{d.title ?? d.version_id.slice(0, 8)}</span>
                            {d.group_size > 1 && <span className="evigraph-badge" title="Documents in the same provenance group">×{d.group_size}</span>}
                        </li>
                    ))}
                </ul>
            </div>
        );
    }
}
