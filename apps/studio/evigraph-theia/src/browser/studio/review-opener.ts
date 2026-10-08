import { ApplicationShell } from '@theia/core/lib/browser/shell/application-shell';
import { WidgetManager } from '@theia/core/lib/browser/widget-manager';
import { inject, injectable } from '@theia/core/shared/inversify';

export interface ReviewOptions {
    versionId: string;
    catalogVersionId: string;
    title: string;
}

export const ReviewOptions = Symbol("ReviewOptions");
export const REVIEW_WIDGET_ID = "evigraph-review";

/** Opens (or reveals) the review editor of a document version. */
@injectable()
export class ReviewOpener {
    @inject(WidgetManager) protected readonly widgets: WidgetManager;
    @inject(ApplicationShell) protected readonly shell: ApplicationShell;

    async open(options: ReviewOptions): Promise<void> {
        const widget = await this.widgets.getOrCreateWidget(REVIEW_WIDGET_ID, options);
        if (!widget.isAttached) {
            await this.shell.addWidget(widget, { area: 'main' });
        }
        await this.shell.activateWidget(widget.id);
    }
}
