import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialog } from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiService } from '../../services/kpi.service';
import { NlService } from '../../services/nl.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  BuilderSpec,
  ChartConfig,
  ChartType,
  ExecutionResult,
  KpiDetail,
} from '../../models/schema.types';
import { ChartRendererComponent } from '../../components/chart-renderer/chart-renderer.component';
import { KpiBuilderPaneComponent } from '../../components/kpi-builder-pane/kpi-builder-pane.component';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import {
  GeneratePromptDialogComponent,
  GeneratePromptResult,
} from '../../components/generate-prompt-dialog/generate-prompt-dialog.component';
import { PeriodSelectorComponent } from '../../components/period-selector/period-selector.component';
import { ChartStylePickerComponent } from '../../components/chart-style-picker/chart-style-picker.component';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';
import {
  ChartStyle, TimePeriod, TimePeriodSelection,
} from '../../models/schema.types';

const CHART_TYPES: { value: ChartType; label: string }[] = [
  { value: 'scorecard', label: 'Score card' },
  { value: 'stat_group', label: 'Stat group' },
  { value: 'bar', label: 'Bar' },
  { value: 'line', label: 'Line' },
  { value: 'pie', label: 'Pie' },
  { value: 'table', label: 'Table' },
];

@Component({
  selector: 'app-kpi-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatProgressBarModule, MatTooltipModule, MatDividerModule,
    MatButtonToggleModule,
    ChartRendererComponent, KpiErrorBannerComponent,
    PeriodSelectorComponent, ChartStylePickerComponent,
    KpiBuilderPaneComponent,
  ],
  template: `
    <div class="editor-page">
      <header class="page-header">
        <button mat-icon-button (click)="back()" matTooltip="Back to list">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <div class="title-block">
          <h1>{{ isNew() ? 'New KPI' : (kpi()?.name || 'KPI') }}</h1>
          <p class="subtitle" *ngIf="kpi() as k">
            v{{ currentVersionNo() || '?' }} ·
            updated {{ k.updated_at | date:'short' }}
          </p>
        </div>
        <span class="spacer"></span>
        <button *ngIf="nlEnabled()"
                mat-stroked-button color="primary"
                (click)="openGenerateDialog()"
                [disabled]="loading()"
                matTooltip="Generate SQL from a natural-language prompt">
          <mat-icon>auto_awesome</mat-icon>
          Generate from prompt
        </button>
        <button mat-stroked-button (click)="runPreview()" [disabled]="loading() || !canPreview()">
          <mat-icon>play_arrow</mat-icon>
          Run preview
        </button>
        <button mat-flat-button color="primary" (click)="save()"
                [disabled]="loading() || !canSave()">
          <mat-icon>save</mat-icon>
          {{ isNew() ? 'Save' : 'Save as new version' }}
        </button>
      </header>

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <app-kpi-error-banner [error]="loadError()"
                             (retry)="retryLoad()"
                             (dismiss)="loadError.set(null)" />

      <div class="editor-grid">
        <!-- Left pane: metadata + (Builder | SQL) authoring -->
        <section class="left-pane">
          <!-- Name + Description side by side. Description gets the
               extra width because it usually carries more text;
               below ~700px the row collapses (media query at the
               style block bottom). -->
          <div class="meta-row">
            <mat-form-field appearance="outline" class="meta-name">
              <mat-label>Name</mat-label>
              <input matInput [ngModel]="name()" (ngModelChange)="name.set($event)" maxlength="200" required>
            </mat-form-field>
            <mat-form-field appearance="outline" class="meta-desc">
              <mat-label>Description (optional)</mat-label>
              <input matInput maxlength="1000"
                     [ngModel]="description()"
                     (ngModelChange)="description.set($event)">
            </mat-form-field>
          </div>

          <!-- Authoring mode toggle. Builder is Power BI–style
               drag-into-wells; SQL drops you into the raw editor for
               complex queries. The toggle is the *only* knob that
               picks which payload save/preview send. -->
          <div class="mode-toggle">
            <mat-button-toggle-group [value]="authoringMode()"
                                     (change)="setAuthoringMode($event.value)">
              <mat-button-toggle value="builder">
                <mat-icon>view_module</mat-icon> Builder
              </mat-button-toggle>
              <mat-button-toggle value="sql">
                <mat-icon>terminal</mat-icon> SQL
              </mat-button-toggle>
            </mat-button-toggle-group>
            <span class="mode-hint" *ngIf="authoringMode() === 'builder'">
              Drag columns into wells; we compile to SQL on save.
            </span>
            <span class="mode-hint" *ngIf="authoringMode() === 'sql'">
              Raw SQL mode — full control, no spec round-trip.
            </span>
          </div>

          <div *ngIf="nlExplanation()" class="ai-note">
            <mat-icon class="ai-icon">auto_awesome</mat-icon>
            <span>{{ nlExplanation() }}</span>
            <button mat-icon-button (click)="nlExplanation.set(null)" matTooltip="Dismiss">
              <mat-icon>close</mat-icon>
            </button>
          </div>

          <!-- Builder mode -->
          <ng-container *ngIf="authoringMode() === 'builder'">
            <app-kpi-builder-pane class="builder-host"
                                  [spec]="builderSpec()"
                                  (specChange)="onBuilderSpecChange($event)" />
          </ng-container>

          <!-- SQL mode -->
          <ng-container *ngIf="authoringMode() === 'sql'">
            <label class="sql-label">
              SQL
              <span class="hint">Read-only · auto-injects TOP 50000 if missing</span>
            </label>
            <textarea class="sql-editor"
                      spellcheck="false"
                      [ngModel]="queryText()"
                      (ngModelChange)="queryText.set($event)"
                      placeholder="SELECT region, SUM(revenue) AS total
FROM customers
GROUP BY region"></textarea>
          </ng-container>

          <div *ngIf="validationError()" class="error-banner">
            <mat-icon>error_outline</mat-icon>
            <div>
              <strong>{{ validationError()!.message }}</strong>
              <ul *ngIf="validationError()!.findings?.length">
                <li *ngFor="let f of validationError()!.findings">{{ f }}</li>
              </ul>
            </div>
          </div>

          <!-- Optional time-column hint. Authors set this when their SQL
               uses :start_date / :end_date so dashboards know which
               column the period selector filters on. -->
          <mat-form-field appearance="outline" class="full"
                          *ngIf="authoringMode() === 'sql'">
            <mat-label>Time column (optional)</mat-label>
            <input matInput maxlength="100"
                   [ngModel]="timeColumn()" (ngModelChange)="timeColumn.set($event)"
                   placeholder="e.g. createdon">
            <mat-hint>
              Reference :start_date and :end_date in your SQL to make this KPI
              respond to the period selector.
            </mat-hint>
          </mat-form-field>
        </section>

        <!-- Right pane: chart picker + preview. All four controls
             (Period / Chart type / Theme / Animations) sit on one
             flexible row at the top so the preview pane below has
             maximum vertical space. -->
        <section class="right-pane">
          <div class="preview-controls">
            <app-period-selector class="ctrl-period"
              [compact]="true"
              [value]="periodSelection().period"
              (periodChange)="onPeriodChange($event)" />

            <mat-form-field appearance="outline" class="ctrl-chart">
              <mat-label>Chart type</mat-label>
              <mat-select [value]="chartType()" (valueChange)="setChartType($event)">
                <mat-option *ngFor="let c of chartTypes" [value]="c.value">{{ c.label }}</mat-option>
              </mat-select>
            </mat-form-field>

            <app-chart-style-picker class="ctrl-style"
              [value]="chartStyle()"
              (styleChange)="chartStyle.set($event)" />
          </div>

          <span *ngIf="autoSuggestion() as s" class="suggestion-hint">
            <mat-icon class="ai-icon">auto_awesome</mat-icon>
            Auto-suggestion: <strong>{{ s.type }}</strong> — {{ s.reason }}
            <button mat-button color="primary" *ngIf="chartType() !== s.type"
                    (click)="acceptSuggestion()">Accept</button>
          </span>

          <div class="preview-pane">
            <ng-container *ngIf="result() as r; else placeholder">
              <div class="preview-meta">
                <span>{{ r.row_count }} rows</span>
                <span>{{ r.duration_ms }}ms</span>
                <span *ngIf="r.truncated" class="truncated-pill">truncated</span>
              </div>
              <app-kpi-chart-renderer [result]="r" [chartConfig]="chartConfig()"/>
              <details class="rewritten-sql">
                <summary>Rewritten SQL</summary>
                <pre>{{ r.rewritten_sql }}</pre>
                <ul *ngIf="r.notes.length">
                  <li *ngFor="let n of r.notes">{{ n }}</li>
                </ul>
              </details>
            </ng-container>
            <ng-template #placeholder>
              <div class="placeholder">
                <mat-icon>insights</mat-icon>
                <p>Click <strong>Run preview</strong> to execute and chart your query.</p>
              </div>
            </ng-template>
          </div>
        </section>
      </div>
    </div>
  `,
  styles: [`
    /* Pin to the viewport (toolbar 64px + content-area 1.5rem padding
       top/bottom = 112px). Without this, height:100% cascades from
       a parent min-height-bounded element and the page grows with
       content — the inner panes never engage their own scroll, so
       the user is forced to scroll the entire window. */
    :host { display: block; height: 100%; }
    .editor-page {
      padding: 16px 24px 24px;
      display: flex; flex-direction: column;
      gap: 12px;
      height: calc(100vh - 64px - 3rem);
      box-sizing: border-box;
      overflow: hidden;
    }
    .page-header { display: flex; gap: 12px; align-items: center; }
    .page-header h1 { margin: 0; font-size: 1.3rem; color: var(--snm-text-primary); }
    .page-header .subtitle { margin: 0; font-size: 0.75rem; color: var(--snm-text-muted); }
    .spacer { flex: 1; }
    .title-block { display: flex; flex-direction: column; }

    /* 2:1 split — the left form (especially the builder's help panel
       and wells) is the working area; the right preview is reference.
       Right pane has a smaller min-width so the chart compresses
       gracefully on narrower viewports instead of forcing horizontal
       page scroll. */
    .editor-grid {
      display: grid;
      grid-template-columns: minmax(560px, 2fr) minmax(340px, 1fr);
      gap: 16px; flex: 1; min-height: 0;
    }
    @media (max-width: 1100px) {
      .editor-grid {
        grid-template-columns: minmax(0, 1fr);
        grid-auto-rows: minmax(0, auto);
      }
    }
    .left-pane, .right-pane {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px; padding: 16px;
      display: flex; flex-direction: column; gap: 12px;
      min-height: 0;
      /* Each pane owns its scroll. The left pane's main scroll
         actually happens inside the builder host (.wells-pane); this
         is a safety net for the SQL-mode textarea + raw-SQL banner
         case. The right pane scrolls its preview chart + SQL details. */
      overflow: hidden;
    }
    .right-pane { overflow-y: auto; }
    .full { width: 100%; }

    /* Name + Description on a single row. Description is a regular
       single-line input now (the multi-line textarea version ate
       too much vertical real estate above the builder). Stacks
       below 700px so it stays usable on narrow viewports. */
    .meta-row {
      display: flex; gap: 12px;
      flex: 0 0 auto;
    }
    .meta-row .meta-name { flex: 1 1 220px; min-width: 0; }
    .meta-row .meta-desc { flex: 2 1 320px; min-width: 0; }
    @media (max-width: 700px) {
      .meta-row { flex-direction: column; gap: 0; }
    }

    .sql-label {
      font-size: 0.85rem; font-weight: 500; color: var(--snm-text-secondary);
      display: flex; justify-content: space-between; align-items: baseline;
    }
    .sql-label .hint { font-weight: 400; color: var(--snm-text-muted); font-size: 0.75rem; }
    .sql-editor {
      flex: 1; min-height: 240px;
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      font-size: 0.85rem; line-height: 1.5;
      padding: 12px; border-radius: 6px;
      border: 1px solid var(--snm-border-field, #d0d0d0);
      background: var(--snm-bg-panel, #fafafa);
      color: var(--snm-text-primary);
      resize: vertical;
    }
    .sql-editor:focus {
      outline: none;
      border-color: var(--snm-accent, #4a90e2);
      box-shadow: 0 0 0 2px var(--snm-accent-shadow, rgba(74,144,226,0.15));
    }

    .error-banner {
      display: flex; gap: 8px; padding: 12px;
      background: rgba(229, 57, 53, 0.08);
      border: 1px solid var(--snm-error, #e53935);
      border-radius: 6px; color: var(--snm-error, #c62828);
      font-size: 0.85rem;
    }
    .ai-note {
      display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px;
      background: var(--snm-bg-panel, #eef4ff);
      border-left: 3px solid var(--snm-accent, #4a90e2);
      border-radius: 4px; font-size: 0.85rem;
      color: var(--snm-text-secondary);
    }
    .ai-note .ai-icon { color: var(--snm-accent); font-size: 18px; width: 18px; height: 18px; margin-top: 2px; }
    .ai-note > span { flex: 1; }
    .error-banner ul { margin: 4px 0 0; padding-left: 18px; }

    .chart-picker {
      display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    }
    /* Allow chart-type and theme dropdowns to shrink with the
       narrower preview pane instead of forcing horizontal scroll. */
    .chart-picker mat-form-field { flex: 1 1 180px; max-width: 240px; }

    /* Consolidated preview-controls row: Period (compact) + Chart
       type + Theme/Animations on one flex row. Each cell shrinks
       to fit so they stay on a single line down to ~440px wide;
       below that the row wraps gracefully. */
    .preview-controls {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      flex: 0 0 auto;
    }
    .preview-controls .ctrl-period { flex: 1 1 130px; min-width: 0; }
    .preview-controls .ctrl-chart  { flex: 1 1 130px; min-width: 0; }
    .preview-controls .ctrl-chart ::ng-deep .mat-mdc-form-field-subscript-wrapper { display: none; }
    .preview-controls .ctrl-style  { flex: 1 1 180px; min-width: 0; }
    .suggestion-hint {
      flex: 1; font-size: 0.8rem; color: var(--snm-text-muted);
      display: flex; align-items: center; gap: 6px;
    }
    .ai-icon { font-size: 16px; width: 16px; height: 16px; color: var(--snm-accent); }

    .preview-pane {
      flex: 1; min-height: 0; overflow: auto;
      background: var(--snm-bg-panel, #fafafa);
      border-radius: 6px; padding: 12px;
    }
    .preview-meta {
      display: flex; gap: 12px; font-size: 0.75rem;
      color: var(--snm-text-muted); margin-bottom: 8px;
    }
    .truncated-pill {
      background: var(--snm-error); color: white;
      padding: 2px 6px; border-radius: 3px; font-size: 0.65rem; text-transform: uppercase;
    }
    .rewritten-sql {
      margin-top: 12px; font-size: 0.8rem;
      summary { cursor: pointer; color: var(--snm-text-secondary); }
      pre { background: var(--snm-bg-card, white); padding: 8px;
            border-radius: 4px; overflow-x: auto; }
    }
    .placeholder {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 12px; height: 100%; color: var(--snm-text-muted);
      mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
    }

    /* Authoring-mode toggle (Builder | SQL). */
    .mode-toggle {
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .mode-toggle mat-button-toggle mat-icon {
      font-size: 16px; width: 16px; height: 16px; vertical-align: middle; margin-right: 4px;
    }
    .mode-hint {
      font-size: 0.78rem; color: var(--snm-text-muted);
    }

    /* Builder host needs to fill the remaining left-pane space so its
       internal scroll regions work. */
    .builder-host {
      flex: 1; min-height: 0; display: block;
    }
  `],
})
export class KpiEditorComponent implements OnInit {
  private readonly kpis = inject(KpiService);
  private readonly nl = inject(NlService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly location = inject(Location);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly chartTypes = CHART_TYPES;
  /** Hidden when no LLM provider is configured server-side. */
  readonly nlEnabled = signal(false);
  readonly nlExplanation = signal<string | null>(null);

  // ---- form state ------------------------------------------------------
  readonly kpi = signal<KpiDetail | null>(null);
  readonly name = signal('');
  readonly description = signal('');
  readonly queryText = signal('');
  readonly chartType = signal<ChartType>('table');
  readonly chartConfigData = signal<Record<string, any>>({});
  readonly chartStyle = signal<ChartStyle>({ theme: 'default', animations: true });
  readonly timeColumn = signal('');

  /** Authoring mode — drives whether save/preview send a builder_spec
   * or a raw query_text. Defaults to ``builder`` for new KPIs (the
   * Power BI–style flow); legacy KPIs without a spec land on ``sql``. */
  readonly authoringMode = signal<'builder' | 'sql'>('builder');
  readonly builderSpec = signal<BuilderSpec>({
    chart_type: 'bar',
    source: { name: '' },
    wells: {},
    filters: [],
    top_n: null,
    time_column: null,
  });
  /** Period filter applied to preview runs. Stays in editor state only;
   * the period selection is NOT persisted on the KPI itself — dashboards
   * pass their own period when running the saved KPI. */
  readonly periodSelection = signal<TimePeriodSelection>({ period: null });

  // ---- runtime state ---------------------------------------------------
  readonly loading = signal(false);
  readonly result = signal<ExecutionResult | null>(null);
  readonly validationError = signal<{ message: string; findings?: string[] } | null>(null);
  readonly loadError = signal<FormattedError | null>(null);

  // ---- derived ---------------------------------------------------------
  readonly isNew = computed(() => this.kpi() == null);
  readonly currentVersionNo = computed(
    () => this.kpi()?.versions?.find(v => v.version_id === this.kpi()?.current_version_id)?.version_no,
  );
  readonly chartConfig = computed<ChartConfig>(() => ({
    type: this.chartType(),
    config: this.chartConfigData(),
    style: this.chartStyle(),
  }));
  readonly autoSuggestion = computed(() => this.result()?.suggestion ?? null);
  /** Builder-mode: source table + every required well filled. SQL-mode:
   * non-empty SQL. The two modes share the same preview / save buttons. */
  readonly canPreview = computed(() => {
    if (this.authoringMode() === 'builder') {
      const s = this.builderSpec();
      if (!s.source?.name) return false;
      // Same required-well rule as the backend compiler.
      const required: Record<string, string[]> = {
        scorecard: ['value'], stat_group: ['values'],
        bar: ['axis', 'values'], pie: ['axis', 'values'],
        line: ['axis', 'values'], table: ['columns'],
      };
      for (const w of required[s.chart_type] ?? []) {
        if (!(s.wells[w] ?? []).length) return false;
      }
      return true;
    }
    return this.queryText().trim().length > 0;
  });
  readonly canSave = computed(() => this.name().trim().length > 0 && this.canPreview());

  ngOnInit(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam && idParam !== 'new') {
      this.loadExisting(parseInt(idParam, 10));
    }
    // Probe NL availability so the button stays hidden when no LLM key
    // is configured. Status is shareReplay-cached so this is one trip.
    this.nl.status()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => this.nlEnabled.set(s.enabled),
        error: () => this.nlEnabled.set(false),
      });
  }

  openGenerateDialog(): void {
    const hasExistingSql = this.queryText().trim().length > 0;
    const proceed = (result: GeneratePromptResult) => {
      this.queryText.set(result.sql);
      this.nlExplanation.set(result.explanation || null);
      this.validationError.set(null);
      this.result.set(null);  // force a fresh preview
      this.notify.success('SQL applied to editor.');
    };

    const open = () => {
      const ref = this.dialog.open(GeneratePromptDialogComponent, {
        width: '640px',
        maxWidth: '90vw',
      });
      ref.afterClosed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((res: GeneratePromptResult | null | undefined) => {
          if (res) proceed(res);
        });
    };

    if (hasExistingSql) {
      const confirm = this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: 'Replace existing SQL?',
          message: 'Generating from a prompt will replace the SQL currently in the editor.',
          confirmText: 'Continue',
          confirmColor: 'primary',
        },
      });
      confirm.afterClosed()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(ok => { if (ok) open(); });
    } else {
      open();
    }
  }

  private loadExisting(id: number): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.kpis.get(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: kpi => {
        this.kpi.set(kpi);
        this.name.set(kpi.name);
        this.description.set(kpi.description ?? '');
        this.queryText.set(kpi.query_text ?? '');
        this.chartType.set(kpi.chart_config?.type ?? 'table');
        this.chartConfigData.set(kpi.chart_config?.config ?? {});
        // Default style for legacy KPIs that pre-date the style field.
        this.chartStyle.set(kpi.chart_config?.style ?? { theme: 'default', animations: true });
        this.timeColumn.set(kpi.time_column ?? '');
        // Mode + spec rehydration. KPIs created via Builder come back
        // with a non-null builder_spec; raw-SQL ones don't.
        if (kpi.builder_spec) {
          this.builderSpec.set(kpi.builder_spec);
          this.authoringMode.set('builder');
        } else {
          this.authoringMode.set('sql');
        }
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        this.loadError.set(formatHttpError(err, 'Failed to load KPI'));
      },
    });
  }

  /** Mode switch keeps state on each side independent — switching to
   * SQL doesn't wipe the builder spec, so a tab back recovers it. */
  setAuthoringMode(mode: 'builder' | 'sql'): void {
    this.authoringMode.set(mode);
    // Clear stale preview so the user re-runs in the new mode.
    this.result.set(null);
    this.validationError.set(null);
  }

  onBuilderSpecChange(spec: BuilderSpec): void {
    this.builderSpec.set(spec);
    // Stale preview — the spec changed shape; user must re-run.
    if (this.result() != null) this.result.set(null);
  }

  retryLoad(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam && idParam !== 'new') {
      this.loadExisting(parseInt(idParam, 10));
    } else {
      this.loadError.set(null);
    }
  }

  setChartType(t: ChartType): void {
    this.chartType.set(t);
    // When the user picks manually, drop suggestion-derived config so renderer falls back to defaults.
    this.chartConfigData.set({});
  }

  acceptSuggestion(): void {
    const s = this.autoSuggestion();
    if (!s) return;
    this.chartType.set(s.type);
    this.chartConfigData.set(s.config ?? {});
  }

  onPeriodChange(sel: TimePeriodSelection): void {
    this.periodSelection.set(sel);
    // Re-run preview if we already have a result, so the chart updates
    // when the user toggles a chip. No-op if the editor is empty.
    if (this.result() != null && this.canPreview()) {
      this.runPreview();
    }
  }

  runPreview(): void {
    if (!this.canPreview()) return;
    this.loading.set(true);
    this.validationError.set(null);
    const sel = this.periodSelection();
    const isBuilder = this.authoringMode() === 'builder';
    this.kpis.preview({
      // One of these two is set per mode; the backend rejects when both
      // are null, so validation flows through cleanly.
      query_text: isBuilder ? null : this.queryText(),
      builder_spec: isBuilder ? this.builderSpec() : null,
      period: sel.period ?? null,
      start_date: sel.start_date ?? null,
      end_date: sel.end_date ?? null,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.loading.set(false);
          this.result.set(r);
          // First successful preview adopts the suggestion; subsequent runs keep the user's choice.
          if (r.suggestion && this.chartType() === 'table' && Object.keys(this.chartConfigData()).length === 0) {
            this.chartType.set(r.suggestion.type);
            this.chartConfigData.set(r.suggestion.config ?? {});
          }
        },
        error: err => {
          this.loading.set(false);
          this.result.set(null);
          const detail = err?.error?.detail;
          if (detail?.error === 'validation_failed' || detail?.error === 'execution_failed') {
            this.validationError.set({ message: detail.message, findings: detail.findings });
          } else {
            this.notify.error(typeof detail === 'string' ? detail : (detail?.message ?? 'Preview failed'));
          }
        },
      });
  }

  save(): void {
    if (!this.canSave()) return;
    const isBuilder = this.authoringMode() === 'builder';
    // Builder-mode payload sends the spec — server compiles + persists
    // both spec and SQL. SQL-mode sends raw query + chart_config as
    // before; the spec column on the new version becomes null.
    const payload = isBuilder ? {
      name: this.name().trim(),
      description: this.description().trim() || null,
      builder_spec: this.builderSpec(),
      time_column: this.builderSpec().time_column ?? null,
    } : {
      name: this.name().trim(),
      description: this.description().trim() || null,
      query_text: this.queryText(),
      chart_config: this.chartConfig(),
      time_column: this.timeColumn().trim() || null,
    };
    this.loading.set(true);
    const obs = this.isNew()
      ? this.kpis.create(payload)
      : this.kpis.update(this.kpi()!.kpi_id, payload);
    obs.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: created => {
        this.loading.set(false);
        const wasNew = this.isNew();
        // Adopt the saved record before deciding what to do — once `kpi`
        // is set, ``isNew()`` becomes false and subsequent saves take the
        // update path correctly.
        this.kpi.set(created);
        this.notify.success(wasNew ? 'KPI created.' : 'KPI saved as new version.');

        if (wasNew) {
          // Replace the URL in place rather than triggering a router
          // navigation. ``router.navigate(...)`` was destroying this
          // component instance and the new instance was racing with the
          // wildcard redirect — landing the user on /dashboard.
          // ``location.replaceState`` updates the URL silently; the
          // component stays mounted with all state intact.
          this.location.replaceState(`/kpi-studio/kpis/${created.kpi_id}`);
        }
      },
      error: err => {
        this.loading.set(false);
        const detail = err?.error?.detail;
        if (detail?.error === 'validation_failed') {
          this.validationError.set({ message: detail.message, findings: detail.findings });
        } else {
          this.notify.error(typeof detail === 'string' ? detail : (detail?.message ?? 'Save failed'));
        }
      },
    });
  }

  back(): void {
    this.router.navigate(['/kpi-studio/kpis']);
  }
}
