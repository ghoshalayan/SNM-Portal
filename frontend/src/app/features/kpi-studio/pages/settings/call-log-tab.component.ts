/**
 * Call log tab — read-only view over ``kpi_llm_call_log`` (shipped
 * 2026-05-25). Lists every outbound LLM HTTP call with filters,
 * surfaces the request/response JSON via a detail dialog, and groups
 * sibling calls that share a correlation id (one user-facing op).
 *
 * Two settings live in this tab's toolbar (rather than the Health
 * tab) so they're side-by-side with the data they govern:
 *   - call_logging_enabled — master on/off for log persistence.
 *   - call_log_retention_days — daily prune cutoff (1..365).
 *
 * Both fields PATCH through to ``PUT /kpi/settings`` because that's
 * the only settings write endpoint; ``force=true`` is set so the
 * accompanying healthcheck-on-save doesn't reject a logging-only
 * change just because some unrelated model is misbehaving.
 */
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy, Component, DestroyRef, EventEmitter,
  Input, OnInit, Output, computed, inject, signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { CallLogsService } from '../../services/call-logs.service';
import { SettingsService } from '../../services/settings.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  CallLogListParams, CallLogSummary, CallLogTriggerSource,
  KpiSettings, ProviderConfig,
} from '../../models/schema.types';
import {
  CallLogDetailDialogComponent, CallLogDetailDialogData,
} from './call-log-detail-dialog.component';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';


type StatusFilter = 'all' | 'success' | 'failure';

const SOURCE_OPTIONS: { value: CallLogTriggerSource | ''; label: string }[] = [
  { value: '',                   label: 'Any source' },
  { value: 'chat',               label: 'Chat' },
  { value: 'nl_generate',        label: 'NL → SQL' },
  { value: 'eval',               label: 'Eval' },
  { value: 'healthcheck_auto',   label: 'Healthcheck (auto)' },
  { value: 'healthcheck_manual', label: 'Healthcheck (manual)' },
  { value: 'provider_test',      label: 'Provider test' },
  { value: 'settings_test',      label: 'Settings test' },
];

@Component({
  selector: 'app-call-log-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatDialogModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatProgressSpinnerModule, MatSelectModule,
    MatSlideToggleModule, MatTooltipModule,
  ],
  template: `
    <!-- Logging gates: persistence on/off + retention window. -->
    <section class="log-toggle-card" [class.is-off]="!loggingEnabledField()">
      <div class="lt-info">
        <mat-icon class="lt-icon">history</mat-icon>
        <div>
          <strong>Persist LLM call logs</strong>
          <div class="hint-sm">
            When ON, every outbound LLM HTTP call (chat, NL→SQL, eval,
            healthcheck, provider test) is recorded with its request +
            response JSON. When OFF, nothing is written — the table
            below stays at whatever rows already exist. Old rows are
            pruned daily by the <code>call_log_prune</code> job.
          </div>
          <div class="hint-sm" *ngIf="!loggingEnabledField()">
            <mat-icon class="warn-ico">warning</mat-icon>
            With logging off you lose the ability to look at past
            prompts and responses — useful for cost / disk control but
            kills observability. Manual healthcheck probes still log.
          </div>
        </div>
      </div>
      <div class="lt-controls">
        <mat-slide-toggle
          [checked]="loggingEnabledField()"
          (change)="loggingEnabledField.set($event.checked); markDirty()">
          {{ loggingEnabledField() ? 'On' : 'Off' }}
        </mat-slide-toggle>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="retain">
          <mat-label>Retention (days)</mat-label>
          <input matInput type="number" min="1" max="365"
                 [ngModel]="retentionField()"
                 (ngModelChange)="retentionField.set($event); markDirty()">
        </mat-form-field>
        <button mat-stroked-button color="primary"
                (click)="saveSettings()"
                [disabled]="!dirty() || savingSettings()">
          <mat-spinner *ngIf="savingSettings()" diameter="14"
                       class="cta-spinner"></mat-spinner>
          <mat-icon *ngIf="!savingSettings()">save</mat-icon>
          Save
        </button>
      </div>
    </section>

    <!-- Filters + actions. -->
    <div class="tab-toolbar">
      <div class="filters">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="f-src">
          <mat-label>Source</mat-label>
          <mat-select [value]="sourceFilter()"
                      (valueChange)="sourceFilter.set($event); reload()">
            <mat-option *ngFor="let s of sourceOptions" [value]="s.value">
              {{ s.label }}
            </mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="f-prov">
          <mat-label>Provider</mat-label>
          <mat-select [value]="providerFilter()"
                      (valueChange)="providerFilter.set($event); reload()">
            <mat-option [value]="null">Any provider</mat-option>
            <mat-option *ngFor="let p of providers"
                        [value]="p.provider_config_id">
              {{ p.display_name }}
            </mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="f-stat">
          <mat-label>Status</mat-label>
          <mat-select [value]="statusFilter()"
                      (valueChange)="statusFilter.set($event); reload()">
            <mat-option value="all">All</mat-option>
            <mat-option value="success">Success only</mat-option>
            <mat-option value="failure">Failure only</mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="f-corr">
          <mat-label>Correlation id</mat-label>
          <input matInput
                 [ngModel]="correlationFilter()"
                 (ngModelChange)="correlationFilter.set($event)"
                 (keydown.enter)="reload()"
                 placeholder="paste a correlation_id">
        </mat-form-field>

        <button mat-stroked-button (click)="clearFilters()"
                [disabled]="!filtersActive()">
          <mat-icon>filter_alt_off</mat-icon> Clear
        </button>
      </div>

      <div class="actions">
        <button mat-stroked-button color="primary"
                (click)="reload()"
                [disabled]="loading()">
          <mat-icon>{{ loading() ? 'hourglass_top' : 'refresh' }}</mat-icon>
          {{ loading() ? 'Loading…' : 'Refresh' }}
        </button>
        <button mat-stroked-button color="warn"
                (click)="confirmPurge()"
                matTooltip="Hard-delete every call-log row. Cannot be undone.">
          <mat-icon>delete_sweep</mat-icon> Purge all
        </button>
      </div>
    </div>

    <!-- Results table. -->
    <div *ngIf="rows().length === 0 && !loading()" class="empty">
      <mat-icon>inbox</mat-icon>
      <p *ngIf="filtersActive()">No call logs match these filters.</p>
      <p *ngIf="!filtersActive()">
        No call logs yet. They'll appear here the moment the agent makes
        its first LLM call (chat, NL→SQL, etc).
      </p>
    </div>

    <table *ngIf="rows().length > 0" class="log-table">
      <thead>
        <tr>
          <th>Started</th>
          <th>Source</th>
          <th>Provider · model</th>
          <th>Stage</th>
          <th>Status</th>
          <th class="num">Latency</th>
          <th class="num">Tokens</th>
          <th>Group</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr *ngFor="let r of rows()"
            [attr.data-ok]="r.succeeded"
            [class.is-corr-active]="correlationFilter() && correlationFilter() === r.correlation_id">
          <td class="ts">{{ formatTs(r.started_at) }}</td>
          <td>
            <span class="src-pill">{{ r.trigger_source }}</span>
          </td>
          <td>
            <div class="prov-cell">
              <strong>{{ r.provider_label || r.provider_kind }}</strong>
              <span class="mono">{{ r.model }}</span>
            </div>
          </td>
          <td>
            <span *ngIf="r.stage_key" class="stage-pill">{{ r.stage_key }}</span>
            <span *ngIf="!r.stage_key" class="muted">—</span>
          </td>
          <td>
            <span class="status-pill" [attr.data-ok]="r.succeeded"
                  [matTooltip]="r.error || ''">
              {{ r.succeeded ? (r.response_status ?? 'OK') : 'FAIL' }}
            </span>
          </td>
          <td class="num">{{ r.latency_ms }}ms</td>
          <td class="num">
            {{ r.total_tokens ?? '—' }}
            <span *ngIf="r.total_tokens !== null" class="muted">
              ({{ r.prompt_tokens }}/{{ r.completion_tokens }})
            </span>
          </td>
          <td>
            <button *ngIf="r.correlation_id"
                    mat-icon-button
                    matTooltip="Show every call in this correlation group"
                    (click)="openCorrelation(r.correlation_id!)">
              <mat-icon>account_tree</mat-icon>
            </button>
          </td>
          <td>
            <button mat-icon-button
                    matTooltip="View request + response JSON"
                    (click)="openDetail(r)">
              <mat-icon>open_in_new</mat-icon>
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Cursor pagination — backend returns next_cursor or null. -->
    <div class="pager" *ngIf="rows().length > 0">
      <span class="muted">
        Showing {{ rows().length }} rows.
        <span *ngIf="loadedPages() > 1">
          ({{ loadedPages() }} pages loaded — newest first)
        </span>
      </span>
      <button mat-stroked-button
              (click)="loadMore()"
              [disabled]="loading() || nextCursor() === null">
        <mat-icon>expand_more</mat-icon>
        {{ nextCursor() === null ? 'No more' : 'Load older' }}
      </button>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .log-toggle-card {
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 16px;
      padding: 14px 16px;
      border-radius: 10px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      margin-bottom: 14px;
      &.is-off {
        border-color: rgba(229,57,53,0.30);
        background: rgba(229,57,53,0.05);
      }
    }
    .lt-info { display: flex; gap: 12px; align-items: flex-start; flex: 1; }
    .lt-icon { color: var(--snm-accent); flex-shrink: 0; margin-top: 2px; }
    .lt-controls {
      display: flex; gap: 10px; align-items: center;
      flex-shrink: 0;
    }
    .lt-controls .retain { width: 120px; }
    .warn-ico {
      font-size: 14px; width: 14px; height: 14px;
      vertical-align: middle; color: #f9a825;
    }
    .hint-sm {
      font-size: 12px; color: var(--snm-text-muted);
      line-height: 1.45; margin-top: 4px;
    }
    .tab-toolbar {
      display: flex; justify-content: space-between; align-items: center;
      gap: 12px; flex-wrap: wrap; margin-bottom: 12px;
    }
    .filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .actions { display: flex; gap: 8px; }
    .f-src   { width: 180px; }
    .f-prov  { width: 200px; }
    .f-stat  { width: 150px; }
    .f-corr  { width: 280px; }

    .empty {
      text-align: center;
      padding: 60px 20px;
      color: var(--snm-text-muted);
      mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.5; }
    }

    table.log-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      th, td {
        padding: 8px 10px;
        border-bottom: 1px solid var(--snm-border-divider);
        text-align: left;
        vertical-align: middle;
      }
      th {
        background: var(--snm-bg-header-row);
        color: var(--snm-text-secondary);
        font-weight: 600;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      td.num, th.num { text-align: right; font-family: monospace; }
      tr[data-ok="false"] { background: rgba(229,57,53,0.05); }
      tr.is-corr-active { outline: 1px solid var(--snm-accent); }
      tr:hover { background: var(--snm-bg-panel); }
    }
    .ts { font-family: monospace; font-size: 11px; color: var(--snm-text-secondary); }
    .mono { font-family: monospace; font-size: 11px; }
    .muted { color: var(--snm-text-muted); }
    .prov-cell { display: flex; flex-direction: column; gap: 1px; }
    .src-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      background: var(--snm-bg-panel); font-size: 10px; font-weight: 600;
      color: var(--snm-text-secondary);
    }
    .stage-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      background: rgba(33,150,243,0.15); color: #1565c0;
      font-size: 10px; font-weight: 600;
    }
    .status-pill {
      display: inline-block; padding: 2px 10px; border-radius: 10px;
      font-size: 11px; font-weight: 700;
      background: rgba(46,125,50,0.15); color: #2e7d32;
      &[data-ok="false"] { background: rgba(229,57,53,0.15); color: #c62828; }
    }
    .cta-spinner { display: inline-block; margin-right: 4px; }

    .pager {
      display: flex; justify-content: space-between; align-items: center;
      padding: 12px 4px;
      font-size: 12px;
    }
  `],
})
export class CallLogTabComponent implements OnInit {
  private readonly logsApi = inject(CallLogsService);
  private readonly settingsApi = inject(SettingsService);
  private readonly notify = inject(NotificationService);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  /** Parent settings page passes the active providers + current
   *  settings snapshot so this tab doesn't need its own fetch on
   *  mount — it inherits what's already loaded. */
  @Input({ required: true }) providers: ProviderConfig[] = [];
  @Input({ required: true }) settings!: KpiSettings;
  /** Emit when the user saves the logging toggles so the parent can
   *  refresh its own settings signal. */
  @Output() settingsSaved = new EventEmitter<KpiSettings>();

  readonly sourceOptions = SOURCE_OPTIONS;

  // ---- logging settings (mirrored from parent settings) --------------
  readonly loggingEnabledField = signal<boolean>(true);
  readonly retentionField = signal<number>(7);
  readonly dirty = signal(false);
  readonly savingSettings = signal(false);

  // ---- filters --------------------------------------------------------
  readonly sourceFilter = signal<CallLogTriggerSource | ''>('');
  readonly providerFilter = signal<number | null>(null);
  readonly statusFilter = signal<StatusFilter>('all');
  readonly correlationFilter = signal<string>('');

  // ---- list state -----------------------------------------------------
  readonly loading = signal(false);
  readonly rows = signal<CallLogSummary[]>([]);
  readonly nextCursor = signal<number | null>(null);
  readonly loadedPages = signal(0);

  readonly filtersActive = computed(() =>
    !!this.sourceFilter() ||
    this.providerFilter() != null ||
    this.statusFilter() !== 'all' ||
    !!this.correlationFilter().trim());

  ngOnInit(): void {
    this.loggingEnabledField.set(this.settings.call_logging_enabled);
    this.retentionField.set(this.settings.call_log_retention_days);
    this.reload();
  }

  markDirty(): void { this.dirty.set(true); }

  // ---- data load ------------------------------------------------------

  private params(cursor: number | null): CallLogListParams {
    const p: CallLogListParams = { limit: 50 };
    if (cursor != null) p.cursor = cursor;
    if (this.sourceFilter()) p.trigger_source = this.sourceFilter();
    if (this.providerFilter() != null) p.provider_config_id = this.providerFilter();
    if (this.statusFilter() === 'success') p.ok = true;
    if (this.statusFilter() === 'failure') p.ok = false;
    const cid = this.correlationFilter().trim();
    if (cid) p.correlation_id = cid;
    return p;
  }

  reload(): void {
    this.loading.set(true);
    this.loadedPages.set(0);
    this.logsApi.list(this.params(null))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.rows.set(res.items);
          this.nextCursor.set(res.next_cursor);
          this.loadedPages.set(1);
          this.loading.set(false);
        },
        error: err => {
          this.loading.set(false);
          this.notify.error(err?.error?.detail || 'Failed to load call logs.');
        },
      });
  }

  loadMore(): void {
    const cur = this.nextCursor();
    if (cur == null) return;
    this.loading.set(true);
    this.logsApi.list(this.params(cur))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.rows.update(prev => [...prev, ...res.items]);
          this.nextCursor.set(res.next_cursor);
          this.loadedPages.update(n => n + 1);
          this.loading.set(false);
        },
        error: err => {
          this.loading.set(false);
          this.notify.error(err?.error?.detail || 'Failed to load more logs.');
        },
      });
  }

  clearFilters(): void {
    this.sourceFilter.set('');
    this.providerFilter.set(null);
    this.statusFilter.set('all');
    this.correlationFilter.set('');
    this.reload();
  }

  // ---- settings save (logging toggles only) --------------------------

  saveSettings(): void {
    this.savingSettings.set(true);
    // force=true so an unrelated unhealthy stage doesn't block a
    // logging-only change. Logging persistence has no LLM cost.
    this.settingsApi.update({
      call_logging_enabled: this.loggingEnabledField(),
      call_log_retention_days: this.retentionField(),
      force: true,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => {
          this.savingSettings.set(false);
          this.dirty.set(false);
          this.notify.success('Call-log settings saved.');
          this.settingsSaved.emit(s);
        },
        error: err => {
          this.savingSettings.set(false);
          this.notify.error(err?.error?.detail?.message
            || err?.error?.detail
            || 'Save failed.');
        },
      });
  }

  // ---- dialogs --------------------------------------------------------

  openDetail(r: CallLogSummary): void {
    const data: CallLogDetailDialogData = { callLogId: r.call_log_id };
    this.dialog.open(CallLogDetailDialogComponent, {
      data, width: '880px', maxWidth: '94vw',
    });
  }

  openCorrelation(cid: string): void {
    const data: CallLogDetailDialogData = { correlationId: cid };
    this.dialog.open(CallLogDetailDialogComponent, {
      data, width: '880px', maxWidth: '94vw',
    });
  }

  confirmPurge(): void {
    this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Purge ALL call logs?',
        message: 'This hard-deletes every kpi_llm_call_log row. ' +
                 'The table will be empty until the next LLM call runs. ' +
                 'Use this when the log is overwhelming you and you ' +
                 'want a clean slate. Cannot be undone.',
        confirmText: 'Purge all',
        confirmColor: 'warn',
      },
    }).afterClosed().subscribe(ok => {
      if (!ok) return;
      this.logsApi.purgeAll().subscribe({
        next: () => {
          this.notify.success('All call logs deleted.');
          this.reload();
        },
        error: err => {
          this.notify.error(err?.error?.detail || 'Purge failed.');
        },
      });
    });
  }

  // ---- formatting -----------------------------------------------------

  /** ``2026-05-25T14:32:11.234567`` → ``05-25 14:32:11`` so the
   *  fixed-width column fits without truncation. Full timestamp lives
   *  in the detail dialog. */
  formatTs(iso: string): string {
    if (!iso) return '';
    // Trust the backend's UTC ISO format. Slice to MM-DD HH:MM:SS.
    const m = iso.match(/^\d{4}-(\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/);
    return m ? `${m[1]} ${m[2]}` : iso;
  }
}
