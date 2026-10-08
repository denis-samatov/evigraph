import { FrontendApplicationContribution } from '@theia/core/lib/browser/frontend-application-contribution';
import { QuickInputService } from '@theia/core/lib/browser/quick-input/quick-input-service';
import { AbstractViewContribution } from '@theia/core/lib/browser/shell/view-contribution';
import { WidgetFactory } from '@theia/core/lib/browser/widget-manager';
import { bindViewContribution } from '@theia/core/lib/browser/shell/view-contribution';
import { CommandRegistry } from '@theia/core/lib/common/command';
import { ContainerModule, inject, injectable } from '@theia/core/shared/inversify';
import { apiUrl, setApiUrl } from './studio/api';
import { ExplorerWidget } from './studio/explorer-widget';
import { REVIEW_WIDGET_ID, ReviewOpener, ReviewOptions } from './studio/review-opener';
import { ReviewWidget } from './studio/review-widget';
import '../../css/studio.css';

const SET_API_URL = { id: 'evigraph.setApiUrl', label: 'EviGraph: Set Core API URL' };
const SET_REVIEWER = { id: 'evigraph.setReviewer', label: 'EviGraph: Set Reviewer Name' };

@injectable()
export class ExplorerContribution extends AbstractViewContribution<ExplorerWidget> implements FrontendApplicationContribution {
    @inject(QuickInputService) protected readonly quickInput: QuickInputService;

    constructor() {
        super({
            widgetId: ExplorerWidget.ID,
            widgetName: ExplorerWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 50 },
            toggleCommandId: 'evigraph.explorer.toggle'
        });
    }

    async initializeLayout(): Promise<void> {
        await this.openView({ activate: true, reveal: true });
    }

    override registerCommands(commands: CommandRegistry): void {
        super.registerCommands(commands);
        commands.registerCommand(SET_API_URL, {
            execute: async () => {
                const value = await this.quickInput.input({ prompt: 'EviGraph Core API URL', value: apiUrl() });
                if (value) {
                    setApiUrl(value);
                    (await this.widget).reload();
                }
            }
        });
        commands.registerCommand(SET_REVIEWER, {
            execute: async () => {
                const value = await this.quickInput.input({
                    prompt: 'Reviewer name recorded with review events',
                    value: window.localStorage.getItem('evigraph.reviewer') ?? ''
                });
                if (value) {
                    window.localStorage.setItem('evigraph.reviewer', value);
                }
            }
        });
    }
}

export default new ContainerModule(bind => {
    bind(ReviewOpener).toSelf().inSingletonScope();
    bind(ExplorerWidget).toSelf();
    bind(WidgetFactory)
        .toDynamicValue(ctx => ({ id: ExplorerWidget.ID, createWidget: () => ctx.container.get(ExplorerWidget) }))
        .inSingletonScope();
    bind(WidgetFactory)
        .toDynamicValue(ctx => ({
            id: REVIEW_WIDGET_ID,
            createWidget: (options: ReviewOptions) => {
                const child = ctx.container.createChild();
                child.bind(ReviewOptions).toConstantValue(options);
                child.bind(ReviewWidget).toSelf();
                return child.get(ReviewWidget);
            }
        }))
        .inSingletonScope();
    bindViewContribution(bind, ExplorerContribution);
    bind(FrontendApplicationContribution).toService(ExplorerContribution);
});
