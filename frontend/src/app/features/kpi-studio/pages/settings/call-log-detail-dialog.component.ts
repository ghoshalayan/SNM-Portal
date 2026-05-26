/**
 * Detail drawer for one ``kpi_llm_call_log`` row — surfaces the full
 * request and response JSON so an admin can see exactly what the agent
 * sent and what the upstream returned.
 *
 * Two modes (the parent picks which by which loader it calls):
 *
 *  - Single-call detail: `loadSingle(call_log_id)` — one row, pretty
 *    JSON for both sides.
 *  - Correlation siblings: `loadCorrelation(correlation_id)` — every
 *    call that shared the same user-facing operation, in chronological
 *    order, with an accordion-style row per sibling.
 *
 * Both modes accept the **inverse** affordance: from the single-call
 * view, clicking "Show siblings" pivots to correlation mode; from
 * correlation mode, clicking a sibling expands its full JSON inline.
 */
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, Inject, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { CallLogsService } from '../../services/call-logs.service';
import {
  CallLogDetail, CallLogSummary,
} from '../../models/schema.types';

export interface CallLogDetailDialogData {
  /** Start in single-call mode for this row. */
  callLogId?: number;
  /** Start in correlation mode for this id. */
  correlationId?: string;
}

@Component({
  selector: 'app-call-log-detail-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, MatButtonModule, MatDialogModule, MatIconModule,
    MatProgressBarModule, MatTabsModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon"
                [class.ok]="primary()?.succeeded"
                [class.fail]="primary() && !primary()!.succeeded">
        {{ primary()?.succeeded ? 'check_circle' : 'error_outline' }}
      </mat-icon>
      {{ headline() }}
    </h2>

    <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

    <mat-dialog-content class="content">
      <div *ngIf="error()" class="banner banner-fail">
        <mat-icon>error_outline</mat-icon> {{ error() }}
      </div>

      <!-- ===== single-call mode ===== -->
      <ng-container *ngIf="single() as call">
        <dl class="meta">
          <dt>Provider</dt>
          <dd>{{ call.provider_label || call.provider_kind }}
              <span class="muted">({{ call.provider_kind }})</span></dd>
          <dt>Model</dt>
          <dd class="mono">{{ call.model }}</dd>
          <dt>Base URL</dt>
          <dd class="mono">{{ call.base_url }}</dd>
          <dt>Trigger</dt>
          <dd>
            <span class="src-pill">{{ call.trigger_source }}</span>
            <span *ngIf="call.stage_key" class="stage-pill">{{ call.stage_key }}</span>
          </dd>
          <dt>Started</dt>
          <dd>{{ call.started_at }}</dd>
          <dt>HTTP</dt>
          <dd>
            <span class="status-pill" [attr.data-ok]="call.succeeded">
              {{ call.response_status ?? '—' }}
            </span>
            {{ call.latency_ms }} ms
          </dd>
          <dt>Tokens</dt>
          <dd>
            prompt {{ call.prompt_tokens ?? '—' }} ·
            completion {{ call.completion_tokens ?? '—' }} ·
            total <strong>{{ call.total_tokens ?? '—' }}</strong>
          </dd>
          <dt *ngIf="call.correlation_id">Correlation</dt>
          <dd *ngIf="call.correlation_id" class="mono corr-row">
            <code>{{ call.correlation_id }}</code>
            <button mat-stroked-button color="primary"
                    (click)="loadCorrelation(call.correlation_id!)">
              <mat-icon>account_tree</mat-icon> Show siblings
            </button>
          </dd>
          <dt *ngIf="call.error">Error</dt>
          <dd *ngIf="call.error" class="err">{{ call.error }}</dd>
        </dl>

        <mat-tab-group animationDuration="200ms" class="json-tabs">
          <mat-tab label="Request body">
            <pre class="json"
                 [class.truncated]="call.request_truncated">{{ pretty(call.request_body) }}</pre>
            <div *ngIf="call.request_truncated" class="trunc-hint">
              Body was truncated to 64KB to keep the log row small.
            </div>
          </mat-tab>
          <mat-tab label="Request headers">
            <pre class="json">{{ pretty(call.request_headers) }}</pre>
          </mat-tab>
          <mat-tab label="Response body">
            <pre class="json"
                 [class.truncated]="call.response_truncated">{{ pretty(call.response_body) }}</pre>
            <div *ngIf="call.response_truncated" class="trunc-hint">
              Body was truncated to 64KB to keep the log row small.
            </div>
          </mat-tab>
        </mat-tab-group>
      </ng-container>

      <!-- ===== correlation siblings mode ===== -->
      <ng-container *ngIf="siblings() as group">
        <div class="banner banner-info">
          <mat-icon>info</mat-icon>
          {{ group.length }} call(s) shared correlation
          <code class="mono">{{ correlationId() }}</code>.
        </div>

        <div class="siblings">
          <div *ngFor="let s of group; let i = index" class="sibling-row"
               [class.is-open]="openIndex() === i"
               [attr.data-ok]="s.succeeded">
            <button class="sibling-head" (click)="toggleOpen(i)">
              <span class="seq">#{{ i + 1 }}</span>
              <span class="src-pill">{{ s.trigger_source }}</span>
              <span *ngIf="s.stage_key" class="stage-pill">{{ s.stage_key }}</span>
              <span class="prov">{{ s.provider_label || s.provider_kind }}</span>
              <span class="mono">{{ s.model }}</span>
              <span class="status-pill" [attr.data-ok]="s.succeeded">
                {{ s.response_status ?? (s.succeeded ? 'ok' : 'fail') }}
              </span>
              <span class="num">{{ s.latency_ms }}ms</span>
              <span class="num" *ngIf="s.total_tokens !== null">
                {{ s.total_tokens }}t
              </span>
              <mat-icon class="chev">
                {{ openIndex() === i ? 'expand_less' : 'expand_more' }}
              </mat-icon>
            </button>
            <div *ngIf="openIndex() === i" class="sibling-body">
              <div *ngIf="s.error" class="err">⚠ {{ s.error }}</div>
              <details open>
                <summary>Request body</summary>
                <pre class="json">{{ pretty(s.request_body) }}</pre>
              </details>
              <details>
                <summary>Request headers</summary>
                <pre class="json">{{ pretty(s.request_headers) }}</pre>
              </details>
              <details open>
                <summary>Response body</summary>
                <pre class="json">{{ pretty(s.response_body) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </ng-container>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="copyJson()"
              *ngIf="single() || siblings()"
              matTooltip="Copy the active JSON payload to clipboard">
        <mat-icon>content_copy</mat-icon> Copy JSON
      </button>
      <button mat-raised-button color="primary" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon { vertical-align: middle; margin-right: 6px; }
    .title-icon.ok { color: #2e7d32; }
    .title-icon.fail { color: #c62828; }
    .content {
      min-width: 720px;
      max-width: 92vw;
      max-height: 78vh;
      padding-top: 4px;
    }
    .banner {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 6px; margin-bottom: 12px;
      font-size: 13px;
    }
    .banner-fail {
      background: rgba(229,57,53,0.10); color: #c62828;
      border: 1px solid rgba(229,57,53,0.40);
    }
    .banner-info {
      background: rgba(33,150,243,0.10); color: var(--snm-text-primary);
      border: 1px solid rgba(33,150,243,0.35);
    }
    dl.meta {
      display: grid; grid-template-columns: 130px 1fr;
      column-gap: 10px; row-gap: 6px;
      margin: 0 0 12px;
      font-size: 13px;
    }
    dl.meta dt { color: var(--snm-text-muted); font-weight: 600; }
    dl.meta dd { margin: 0; color: var(--snm-text-primary); word-break: break-all; }
    dl.meta dd.err { color: #c62828; }
    dl.meta dd.corr-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .mono { font-family: monospace; font-size: 12px; }
    .muted { color: var(--snm-text-muted); margin-left: 4px; }
    .src-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      background: var(--snm-bg-panel); font-size: 11px; font-weight: 600;
      color: var(--snm-text-secondary); margin-right: 6px;
    }
    .stage-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      background: rgba(33,150,243,0.15); color: #1565c0;
      font-size: 11px; font-weight: 600; margin-right: 6px;
    }
    .status-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; font-weight: 700;
      background: rgba(46,125,50,0.15); color: #2e7d32;
      &[data-ok="false"] { background: rgba(229,57,53,0.15); color: #c62828; }
    }
    .json-tabs { margin-top: 8px; }
    pre.json {
      margin: 8px 0 0;
      padding: 10px 12px;
      background: var(--snm-bg-panel);
      border-radius: 6px;
      font-family: monospace;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 48vh;
      overflow: auto;
    }
    pre.json.truncated {
      border-left: 3px solid #f9a825;
    }
    .trunc-hint {
      font-size: 11px; color: var(--snm-text-muted);
      padding: 4px 12px;
    }
    .siblings { display: flex; flex-direction: column; gap: 6px; }
    .sibling-row {
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      overflow: hidden;
      background: var(--snm-bg-card);
    }
    .sibling-row[data-ok="false"] { border-color: rgba(229,57,53,0.55); }
    .sibling-head {
      display: flex; align-items: center; gap: 8px;
      width: 100%;
      padding: 8px 10px;
      background: transparent;
      border: none;
      cursor: pointer;
      text-align: left;
      color: var(--snm-text-primary);
      font-size: 12px;
    }
    .sibling-head:hover { background: var(--snm-bg-panel); }
    .sibling-row.is-open .sibling-head {
      background: var(--snm-bg-panel);
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .seq {
      font-weight: 700;
      color: var(--snm-text-muted);
      min-width: 28px;
    }
    .prov { color: var(--snm-text-secondary); }
    .num { color: var(--snm-text-muted); margin-left: 4px; }
    .chev { margin-left: auto; color: var(--snm-text-muted); }
    .sibling-body {
      padding: 8px 12px 12px;
      details { margin-top: 6px; }
      summary {
        cursor: pointer; padding: 4px 0;
        font-size: 12px; font-weight: 600;
        color: var(--snm-text-secondary);
      }
    }
    .err { color: #c62828; font-size: 12px; padding: 4px 0; }
  `],
})
export class CallLogDetailDialogComponent {
  private readonly svc = inject(CallLogsService);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly single = signal<CallLogDetail | null>(null);
  readonly siblings = signal<CallLogDetail[] | null>(null);
  readonly correlationId = signal<string | null>(null);
  readonly openIndex = signal<number>(-1);

  /** "Primary" row used to colour the title icon: in single-call mode
   *  it's the only row; in siblings mode it's the first failure (or
   *  first call if all succeeded) — that's the row most likely to be
   *  what the admin came here to investigate. */
  readonly primary = computed<CallLogSummary | null>(() => {
    if (this.single()) return this.single();
    const group = this.siblings();
    if (!group?.length) return null;
    return group.find(g => !g.succeeded) ?? group[0];
  });

  readonly headline = computed(() => {
    const s = this.single();
    if (s) return `Call #${s.call_log_id} · ${s.trigger_source}`;
    const cid = this.correlationId();
    if (cid) return `Correlation ${cid.slice(0, 12)}…`;
    return 'Call log';
  });

  constructor(
    public dialogRef: MatDialogRef<CallLogDetailDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: CallLogDetailDialogData,
  ) {
    if (data.callLogId != null) {
      this.loadSingle(data.callLogId);
    } else if (data.correlationId) {
      this.loadCorrelation(data.correlationId);
    }
  }

  loadSingle(id: number): void {
    this.loading.set(true);
    this.error.set(null);
    this.siblings.set(null);
    this.correlationId.set(null);
    this.svc.get(id).subscribe({
      next: row => { this.single.set(row); this.loading.set(false); },
      error: err => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Failed to load call log.');
      },
    });
  }

  loadCorrelation(cid: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.single.set(null);
    this.correlationId.set(cid);
    this.openIndex.set(-1);
    this.svc.byCorrelation(cid).subscribe({
      next: res => {
        this.siblings.set(res.items);
        this.loading.set(false);
        // Auto-expand the first failure so the admin's eye lands on
        // the broken call without an extra click. Falls back to the
        // first row in an all-success group.
        const failIdx = res.items.findIndex(c => !c.succeeded);
        this.openIndex.set(failIdx >= 0 ? failIdx : 0);
      },
      error: err => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Failed to load correlation group.');
      },
    });
  }

  toggleOpen(i: number): void {
    this.openIndex.set(this.openIndex() === i ? -1 : i);
  }

  /** Pretty-print a JSON string for the <pre>. If the value isn't
   *  parseable JSON (rare — masked headers + truncation can leave a
   *  partial blob) we render it as-is so the admin still sees
   *  *something* instead of an empty box. */
  pretty(raw: string | null | undefined): string {
    if (raw == null || raw === '') return '(empty)';
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }

  /** Copy the most relevant JSON to the clipboard — the response body
   *  in single-call mode, or the whole siblings array in correlation
   *  mode (for pasting into a debugging note). */
  copyJson(): void {
    const s = this.single();
    let payload = '';
    if (s) {
      payload = this.pretty(s.response_body);
    } else if (this.siblings()) {
      payload = JSON.stringify(this.siblings(), null, 2);
    }
    navigator.clipboard?.writeText(payload).catch(() => {/* swallow */});
  }

  close(): void {
    this.dialogRef.close();
  }
}
