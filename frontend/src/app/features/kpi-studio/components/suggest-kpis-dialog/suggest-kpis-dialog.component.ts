import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { KpiSchemaService } from '../../services/kpi-schema.service';
import { NlService } from '../../services/nl.service';
import { KpiService } from '../../services/kpi.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  KpiSuggestionItem, TableInfo,
} from '../../models/schema.types';

/**
 * Phase J — AI Suggest KPIs dialog.
 *
 * Flow: pick a table → call ``POST /kpi/nl/suggest-kpis`` → display
 * each proposal with name, description, chart type + a preview of
 * the compiled SQL → user checkboxes which to keep → "Save selected"
 * batch-creates them via ``POST /kpi/kpis``.
 *
 * Returns the list of created KPI ids to the caller (e.g. the KPIs
 * list page) so it can refresh.
 */
@Component({
  selector: 'app-suggest-kpis-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatAutocompleteModule, MatProgressBarModule, MatCheckboxModule,
    MatChipsModule, MatTooltipModule, MatDialogModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="ai-icon">auto_awesome</mat-icon>
      AI Suggest KPIs
    </h2>
    <mat-dialog-content>
      <p class="hint" *ngIf="step() === 'pick'">
        Pick a source table; the AI proposes 5–8 useful KPIs covering
        totals, trends, top-N breakdowns and distributions. Review
        each one and keep what's useful — they save as
        <strong>Builder mode</strong> KPIs you can edit later.
      </p>

      <!-- Step 1 — pick a table -->
      <ng-container *ngIf="step() === 'pick'">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Source table</mat-label>
          <input matInput
                 [matAutocomplete]="auto"
                 [ngModel]="tableSearch()"
                 (ngModelChange)="tableSearch.set($event)"
                 placeholder="Type to search...">
          <mat-icon matSuffix>search</mat-icon>
          <mat-autocomplete #auto="matAutocomplete"
                            (optionSelected)="onTablePick($event)">
            <mat-option *ngFor="let t of filteredTables()" [value]="tableKey(t)">
              {{ tableLabel(t) }}
            </mat-option>
            <mat-option *ngIf="!filteredTables().length" disabled>
              No matching table
            </mat-option>
          </mat-autocomplete>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full">
          <mat-label>How many KPIs to propose</mat-label>
          <input matInput type="number" min="1" max="12"
                 [ngModel]="count()" (ngModelChange)="count.set(+$event || 6)">
        </mat-form-field>
      </ng-container>

      <!-- Step 2 — generating -->
      <div *ngIf="step() === 'generating'" class="generating">
        <mat-progress-bar mode="indeterminate"></mat-progress-bar>
        <p>Asking the AI to draft KPIs for
           <strong>{{ selectedTableKey() }}</strong>… this usually
           takes 5–15 seconds.</p>
      </div>

      <!-- Step 3 — review proposals -->
      <ng-container *ngIf="step() === 'review'">
        <p class="hint" *ngIf="suggestions().length">
          {{ suggestions().length }} proposal{{ suggestions().length === 1 ? '' : 's' }}
          for <strong>{{ selectedTableKey() }}</strong>. Tick the
          ones you want to save.
        </p>
        <p class="hint warn" *ngIf="!suggestions().length">
          The AI didn't return any usable proposals.
          <a (click)="resetToPick()" class="link">Try a different table</a>
          or <a (click)="regenerate()" class="link">retry</a>.
        </p>

        <div *ngFor="let s of suggestions(); let i = index" class="proposal"
             [class.selected]="selected().has(i)"
             [class.disabled]="savedIds().has(i)">
          <mat-checkbox [checked]="selected().has(i)"
                        [disabled]="savedIds().has(i)"
                        (change)="toggleSelected(i)">
          </mat-checkbox>
          <div class="proposal-body">
            <header>
              <strong>{{ s.name }}</strong>
              <mat-chip class="type-chip" disabled>{{ s.builder_spec.chart_type }}</mat-chip>
              <mat-icon class="saved-icon"
                        *ngIf="savedIds().has(i)"
                        matTooltip="Saved">check_circle</mat-icon>
            </header>
            <p class="desc">{{ s.description }}</p>
            <details>
              <summary>SQL preview</summary>
              <pre>{{ s.sql }}</pre>
            </details>
          </div>
        </div>
      </ng-container>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="result()" [disabled]="working()">
        Close
      </button>
      <button mat-stroked-button (click)="resetToPick()"
              *ngIf="step() === 'review'"
              [disabled]="working()">
        Pick another table
      </button>
      <button mat-flat-button color="primary"
              *ngIf="step() === 'pick'"
              (click)="generate()"
              [disabled]="!canGenerate() || working()">
        <mat-icon>auto_awesome</mat-icon>
        Generate
      </button>
      <button mat-flat-button color="primary"
              *ngIf="step() === 'review'"
              (click)="saveSelected()"
              [disabled]="!canSave() || working()">
        <mat-icon>save</mat-icon>
        Save selected ({{ selected().size }})
      </button>
    </mat-dialog-actions>

    <mat-progress-bar *ngIf="working()" mode="indeterminate"></mat-progress-bar>
  `,
  styles: [`
    h2 mat-dialog-title { display: flex; align-items: center; gap: 8px; }
    .ai-icon { color: var(--snm-accent); }
    .full { width: 100%; }
    .hint {
      margin: 0 0 12px; color: var(--snm-text-muted); font-size: 0.9rem;
      line-height: 1.5;
    }
    .hint.warn { color: var(--snm-error); }
    .link { color: var(--snm-accent); cursor: pointer; text-decoration: underline; }

    .generating {
      display: flex; flex-direction: column; gap: 12px;
      padding: 24px 0;
      color: var(--snm-text-secondary);
      p { margin: 0; }
    }

    .proposal {
      display: flex; gap: 12px; align-items: flex-start;
      padding: 10px 12px;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      margin: 8px 0;
      transition: border-color 160ms ease, background 160ms ease;
      &.selected { border-color: var(--snm-accent); background: var(--snm-accent-subtle); }
      &.disabled { opacity: 0.6; }
    }
    .proposal-body { flex: 1; min-width: 0; }
    .proposal-body header {
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      strong { color: var(--snm-text-primary); }
    }
    .type-chip { font-size: 0.7rem !important; }
    .saved-icon { color: var(--snm-accent); font-size: 18px; width: 18px; height: 18px; }
    .desc {
      margin: 4px 0; color: var(--snm-text-secondary);
      font-size: 0.85rem; line-height: 1.4;
    }
    details {
      margin-top: 6px;
      summary { cursor: pointer; font-size: 0.8rem; color: var(--snm-text-muted); }
      pre {
        margin: 6px 0 0; padding: 8px;
        background: var(--snm-bg-panel); border-radius: 4px;
        font-family: ui-monospace, Consolas, monospace;
        font-size: 0.78rem; line-height: 1.4;
        max-height: 220px; overflow: auto;
      }
    }
  `],
})
export class SuggestKpisDialogComponent implements OnInit {
  private readonly schemaApi = inject(KpiSchemaService);
  private readonly nl = inject(NlService);
  private readonly kpis = inject(KpiService);
  private readonly notify = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ref = inject<MatDialogRef<SuggestKpisDialogComponent, number[]>>(
    MatDialogRef,
  );

  readonly step = signal<'pick' | 'generating' | 'review'>('pick');
  readonly working = signal(false);
  readonly tables = signal<TableInfo[]>([]);
  readonly tableSearch = signal('');
  readonly selectedTableKey = signal<string>('');
  readonly count = signal(6);
  readonly suggestions = signal<KpiSuggestionItem[]>([]);
  /** Indices of suggestions the user ticked. */
  readonly selected = signal<Set<number>>(new Set());
  /** Indices already persisted (so the user can't double-save). */
  readonly savedIds = signal<Set<number>>(new Set());
  /** Returned to the caller on close. */
  private readonly createdKpiIds: number[] = [];

  readonly canGenerate = computed(() => !!this.selectedTableKey());
  readonly canSave = computed(() => this.selected().size > 0);

  readonly filteredTables = computed<TableInfo[]>(() => {
    const q = this.tableSearch().trim().toLowerCase();
    const all = this.tables();
    if (!q) return all;
    return all.filter(t => this.tableLabel(t).toLowerCase().includes(q));
  });

  result(): number[] { return [...this.createdKpiIds]; }

  ngOnInit(): void {
    this.schemaApi.getTables()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => this.tables.set(res.tables ?? []),
        error: () => this.notify.error('Could not load schema tables'),
      });
  }

  // ---- step 1 — pick ------------------------------------------------

  tableKey(t: TableInfo): string {
    return t.schema ? `${t.schema}.${t.name}` : t.name;
  }
  tableLabel(t: TableInfo): string {
    return this.tableKey(t) + (t.row_count_estimate ? ` (~${t.row_count_estimate})` : '');
  }

  onTablePick(ev: MatAutocompleteSelectedEvent): void {
    this.selectedTableKey.set(ev.option.value as string);
    this.tableSearch.set(ev.option.value as string);
  }

  generate(): void {
    const key = this.selectedTableKey();
    if (!key) return;
    const [schema, name] = key.includes('.') ? key.split('.', 2) : [null, key];
    this.step.set('generating');
    this.working.set(true);
    this.suggestions.set([]);
    this.selected.set(new Set());
    this.savedIds.set(new Set());

    this.nl.suggestKpis({ table: name, schema, count: this.count() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.working.set(false);
          this.step.set('review');
          this.suggestions.set(res.items);
          // Pre-select all by default — user can untick what they don't want.
          this.selected.set(new Set(res.items.map((_, i) => i)));
          if (res.error) {
            this.notify.error(`AI: ${res.error}`);
          } else if (!res.items.length) {
            this.notify.info('No usable proposals — try a different table.');
          }
        },
        error: err => {
          this.working.set(false);
          this.step.set('pick');
          this.notify.error(err?.error?.detail ?? 'AI suggestion failed');
        },
      });
  }

  regenerate(): void { this.generate(); }

  resetToPick(): void {
    this.step.set('pick');
    this.suggestions.set([]);
    this.selected.set(new Set());
    this.savedIds.set(new Set());
  }

  // ---- step 3 — save ------------------------------------------------

  toggleSelected(index: number): void {
    if (this.savedIds().has(index)) return;
    const next = new Set(this.selected());
    if (next.has(index)) next.delete(index);
    else next.add(index);
    this.selected.set(next);
  }

  saveSelected(): void {
    const indices = [...this.selected()].filter(i => !this.savedIds().has(i));
    if (!indices.length) return;
    this.working.set(true);
    const items = this.suggestions();

    // Parallel saves — each KPI is independent, so one failing
    // doesn't block the others; we collect successes + errors.
    const calls = indices.map(i => {
      const s = items[i];
      return this.kpis.create({
        name: s.name,
        description: s.description || null,
        builder_spec: s.builder_spec,
        time_column: s.builder_spec.time_column ?? null,
      }).pipe(
        map(kpi => ({ index: i, kpi, error: null as string | null })),
        catchError(err => of({
          index: i, kpi: null,
          error: err?.error?.detail?.message ?? err?.error?.detail ?? 'save failed',
        })),
      );
    });

    forkJoin(calls)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(results => {
        this.working.set(false);
        const savedNow = new Set(this.savedIds());
        let okCount = 0; let errCount = 0;
        for (const r of results) {
          if (r.kpi) {
            savedNow.add(r.index);
            this.createdKpiIds.push(r.kpi.kpi_id);
            okCount++;
          } else {
            errCount++;
          }
        }
        this.savedIds.set(savedNow);
        // Drop saved items from the pending selection.
        const stillSelected = new Set(
          [...this.selected()].filter(i => !savedNow.has(i)),
        );
        this.selected.set(stillSelected);

        if (okCount) {
          this.notify.success(
            `Saved ${okCount} KPI${okCount === 1 ? '' : 's'}` +
            (errCount ? ` — ${errCount} failed.` : '.'),
          );
        }
        if (errCount && !okCount) {
          this.notify.error(`All ${errCount} saves failed.`);
        }
      });
  }
}
