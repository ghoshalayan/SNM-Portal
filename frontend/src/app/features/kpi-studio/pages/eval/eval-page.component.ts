/**
 * KPI Studio eval-harness admin page (T-001).
 *
 * Three surfaces in one component (tabs):
 *  - **Runs** — most-recent first. Click a row to expand its per-case
 *    results inline. "Run now" button POSTs /eval/runs synchronously.
 *  - **Cases** — list with activate/deactivate, create (dialog), and
 *    edit (dialog). Hard delete is intentionally not exposed — soft
 *    delete via the toggle keeps history alive.
 *
 * SuperAdmin-only by virtue of the backend gate (kpi:settings). The
 * sidebar menu item is hidden for everyone else by the standard
 * has-permission directive, so this page being reachable already
 * implies the right role.
 */
import { CommonModule, DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { NotificationService } from '../../../../core/services/notification.service';
import {
  EvalCase,
  EvalRun,
} from '../../models/schema.types';
import { EvalService } from '../../services/eval.service';
import { EvalCaseDialogComponent, EvalCaseDialogData } from './eval-case-dialog.component';

@Component({
  selector: 'app-eval-page',
  standalone: true,
  imports: [
    CommonModule, DatePipe, DecimalPipe, FormsModule,
    MatButtonModule, MatCardModule, MatChipsModule, MatDialogModule,
    MatFormFieldModule, MatIconModule, MatInputModule,
    MatProgressSpinnerModule, MatSlideToggleModule, MatTabsModule,
    MatTooltipModule,
  ],
  template: `
    <div class="page-head">
      <div class="page-head-left">
        <mat-icon class="page-head-icon">science</mat-icon>
        <div>
          <h2 class="page-title">Eval Harness</h2>
          <div class="page-subtitle">
            Golden test cases fired through the NL-to-SQL pipeline.
            Pass-rate is the regression signal — author cases for the
            queries you care about most.
          </div>
        </div>
      </div>
      <div class="page-head-actions">
        <button mat-stroked-button color="primary"
                (click)="loadRuns(); loadCases()"
                [disabled]="loadingRuns || loadingCases">
          <mat-icon>refresh</mat-icon> Refresh
        </button>
        <button mat-raised-button color="primary"
                (click)="runNow()"
                [disabled]="triggering || loadingCases">
          @if (triggering) {
            <mat-spinner diameter="18" class="cta-spinner"></mat-spinner>
          } @else {
            <mat-icon>play_arrow</mat-icon>
          }
          Run now
        </button>
      </div>
    </div>

    <mat-tab-group animationDuration="200ms" [(selectedIndex)]="activeTab">
      <!-- ============= RUNS ============= -->
      <mat-tab label="Runs">
        <div class="tab-body">
          @if (loadingRuns) {
            <div class="loading"><mat-spinner diameter="32"></mat-spinner></div>
          } @else if (runs.length === 0) {
            <div class="empty">
              <mat-icon>history</mat-icon>
              <p>No runs yet. Author a case then hit <strong>Run now</strong>.</p>
            </div>
          } @else {
            <div class="run-list">
              @for (run of runs; track run.eval_run_id) {
                <mat-card class="run-card">
                  <div class="run-row" (click)="toggleRun(run)">
                    <div class="run-id">#{{ run.eval_run_id }}</div>
                    <div class="run-rate" [attr.data-band]="bandFor(run)">
                      {{ (run.pass_rate * 100) | number:'1.0-1' }}%
                    </div>
                    <div class="run-counts">
                      <span class="ct pass">{{ run.cases_passed }} pass</span>
                      <span class="ct fail" *ngIf="run.cases_failed">
                        {{ run.cases_failed }} fail
                      </span>
                      <span class="ct err" *ngIf="run.cases_errored">
                        {{ run.cases_errored }} err
                      </span>
                      <span class="ct skip" *ngIf="run.cases_skipped">
                        {{ run.cases_skipped }} skip
                      </span>
                    </div>
                    <div class="run-when">
                      {{ run.started_at | date:'dd MMM yyyy, HH:mm:ss' }}
                      <span class="run-by">via {{ run.triggered_by }}</span>
                    </div>
                    <mat-icon class="expand-icon">
                      {{ expandedRunId === run.eval_run_id ? 'expand_less' : 'expand_more' }}
                    </mat-icon>
                  </div>

                  @if (expandedRunId === run.eval_run_id) {
                    <div class="run-detail">
                      @if (loadingDetail) {
                        <mat-spinner diameter="24"></mat-spinner>
                      } @else if (runDetail) {
                        <div class="run-meta-strip">
                          @if (runDetail.snapshot_id) {
                            <span class="meta-pill">snapshot #{{ runDetail.snapshot_id }}</span>
                          }
                          @if (runDetail.prompt_version) {
                            <span class="meta-pill">prompt v{{ runDetail.prompt_version }}</span>
                          }
                          @if (runDetail.tags_filter && runDetail.tags_filter.length) {
                            <span class="meta-pill">
                              tags: {{ runDetail.tags_filter.join(', ') }}
                            </span>
                          }
                          @if (runDetail.summary_json?.['wall_clock_s']) {
                            <span class="meta-pill">
                              {{ runDetail.summary_json?.['wall_clock_s'] }}s
                            </span>
                          }
                        </div>

                        <table class="case-table">
                          <thead>
                            <tr>
                              <th>Status</th>
                              <th>Case</th>
                              <th>Reasons</th>
                              <th class="num">Rows</th>
                              <th class="num">Tokens</th>
                              <th class="num">Time (ms)</th>
                            </tr>
                          </thead>
                          <tbody>
                            @for (r of runDetail.results; track r.result_id) {
                              <tr [attr.data-status]="r.status">
                                <td>
                                  <span class="status-pill"
                                        [attr.data-status]="r.status">
                                    {{ r.status }}
                                  </span>
                                </td>
                                <td>
                                  <strong>#{{ r.case_id }}</strong>
                                  {{ caseNameById[r.case_id] || '(unknown)' }}
                                </td>
                                <td class="reasons">
                                  @for (reason of r.failure_reasons; track reason) {
                                    <span class="reason-tag"
                                          [matTooltip]="reasonDetail(r, reason)">
                                      {{ reason }}
                                    </span>
                                  }
                                  @if (!r.failure_reasons?.length) { — }
                                </td>
                                <td class="num">{{ r.produced_row_count ?? '—' }}</td>
                                <td class="num">{{ r.tokens_used ?? '—' }}</td>
                                <td class="num">{{ r.duration_ms ?? '—' }}</td>
                              </tr>
                            }
                          </tbody>
                        </table>
                      }
                    </div>
                  }
                </mat-card>
              }
            </div>
          }
        </div>
      </mat-tab>

      <!-- ============= CASES ============= -->
      <mat-tab label="Cases">
        <div class="tab-body">
          <div class="cases-toolbar">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="filter-field">
              <mat-icon matPrefix>search</mat-icon>
              <input matInput placeholder="Filter by name or tag"
                     [(ngModel)]="caseFilter" />
            </mat-form-field>
            <mat-slide-toggle [(ngModel)]="showInactive"
                              (change)="loadCases()">
              Show inactive
            </mat-slide-toggle>
            <button mat-raised-button color="primary"
                    (click)="openCaseDialog(null)">
              <mat-icon>add</mat-icon> New case
            </button>
          </div>

          @if (loadingCases) {
            <div class="loading"><mat-spinner diameter="32"></mat-spinner></div>
          } @else if (filteredCases.length === 0) {
            <div class="empty">
              <mat-icon>list</mat-icon>
              <p>No cases match. Click <strong>New case</strong> to author one.</p>
            </div>
          } @else {
            <table class="case-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Name</th>
                  <th>Tags</th>
                  <th>Expected tables</th>
                  <th>Last pass</th>
                  <th>Active</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (c of filteredCases; track c.case_id) {
                  <tr>
                    <td>{{ c.case_id }}</td>
                    <td>
                      <strong>{{ c.name }}</strong>
                      <div class="case-prompt-preview">{{ c.prompt }}</div>
                    </td>
                    <td>
                      <mat-chip-set>
                        @for (t of c.tags; track t) {
                          <mat-chip>{{ t }}</mat-chip>
                        }
                      </mat-chip-set>
                    </td>
                    <td class="mono">
                      {{ (c.expected_tables || []).join(', ') || '—' }}
                    </td>
                    <td>
                      @if (c.last_pass_at) {
                        {{ c.last_pass_at | date:'dd MMM, HH:mm' }}
                      } @else {
                        <span class="muted">never</span>
                      }
                    </td>
                    <td>
                      <mat-slide-toggle [checked]="c.is_active"
                                        (change)="toggleActive(c)">
                      </mat-slide-toggle>
                    </td>
                    <td class="actions">
                      <button mat-icon-button
                              (click)="runJust(c)"
                              [disabled]="triggering"
                              matTooltip="Run only this case">
                        <mat-icon>play_arrow</mat-icon>
                      </button>
                      <button mat-icon-button
                              (click)="openCaseDialog(c)"
                              matTooltip="Edit">
                        <mat-icon>edit</mat-icon>
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </div>
      </mat-tab>
    </mat-tab-group>
  `,
  styles: [`
    :host { display: block; padding: 16px 20px 32px; }

    .page-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .page-head-left { display: flex; align-items: center; gap: 12px; }
    .page-head-icon {
      font-size: 30px; width: 30px; height: 30px;
      color: var(--snm-accent);
    }
    .page-title { margin: 0; font-size: 18px; font-weight: 700; color: var(--snm-text-primary); }
    .page-subtitle {
      font-size: 12px; color: var(--snm-text-muted); max-width: 560px;
      line-height: 1.4; margin-top: 2px;
    }
    .page-head-actions { display: flex; gap: 8px; align-items: center; }
    .cta-spinner { display: inline-block; margin-right: 6px; vertical-align: middle; }

    .tab-body { padding: 14px 4px; }
    .loading {
      display: flex; justify-content: center; padding: 40px 0;
    }
    .empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 6px; padding: 40px 12px;
      color: var(--snm-text-muted);
    }
    .empty mat-icon {
      font-size: 36px; width: 36px; height: 36px; opacity: 0.55;
    }

    /* ----- Runs ----- */
    .run-list { display: flex; flex-direction: column; gap: 8px; }
    .run-card { padding: 0; overflow: hidden; }
    .run-row {
      display: grid;
      grid-template-columns: 60px 80px 1fr auto 24px;
      align-items: center; gap: 12px;
      padding: 10px 14px;
      cursor: pointer;
    }
    .run-row:hover { background: var(--snm-bg-panel); }
    .run-id {
      font-family: monospace; font-weight: 700;
      color: var(--snm-text-secondary);
    }
    .run-rate {
      font-size: 16px; font-weight: 700;
      padding: 2px 8px; border-radius: 6px;
      text-align: center;
    }
    .run-rate[data-band="green"] {
      background: rgba(46,125,50,0.14); color: #2e7d32;
    }
    .run-rate[data-band="yellow"] {
      background: rgba(200,150,30,0.18); color: rgba(140, 95, 0, 0.95);
    }
    .run-rate[data-band="red"] {
      background: rgba(198,40,40,0.14); color: #c62828;
    }
    .run-counts { display: flex; gap: 10px; font-size: 12px; }
    .ct { font-weight: 600; }
    .ct.pass { color: #2e7d32; }
    .ct.fail { color: #c62828; }
    .ct.err { color: #c62828; font-style: italic; }
    .ct.skip { color: var(--snm-text-muted); }
    .run-when {
      font-size: 12px; color: var(--snm-text-muted);
      font-variant-numeric: tabular-nums; text-align: right;
    }
    .run-by { display: block; font-style: italic; opacity: 0.8; }
    .expand-icon { color: var(--snm-text-muted); }

    .run-detail {
      padding: 12px 14px;
      border-top: 1px solid var(--snm-border-divider);
      background: var(--snm-bg-panel);
    }
    .run-meta-strip {
      display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;
    }
    .meta-pill {
      font-size: 11px;
      padding: 2px 8px; border-radius: 999px;
      background: var(--snm-bg-card); color: var(--snm-text-secondary);
      border: 1px solid var(--snm-border-divider);
    }

    /* ----- Cases ----- */
    .cases-toolbar {
      display: flex; gap: 12px; align-items: center; margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .filter-field { flex: 0 0 320px; }
    .case-prompt-preview {
      font-size: 11px; color: var(--snm-text-muted);
      max-width: 360px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap;
    }
    .actions { display: flex; gap: 4px; justify-content: flex-end; }
    .muted { color: var(--snm-text-faint); font-style: italic; }
    .mono { font-family: monospace; font-size: 12px; }

    /* Shared table styling */
    .case-table {
      width: 100%; border-collapse: collapse;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      overflow: hidden;
    }
    .case-table th, .case-table td {
      padding: 6px 10px;
      border-bottom: 1px solid var(--snm-border-divider);
      text-align: left;
      font-size: 12px;
    }
    .case-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
      font-size: 11px;
    }
    .case-table td.num, .case-table th.num {
      text-align: right; font-variant-numeric: tabular-nums;
    }
    .case-table tr[data-status="pass"] td:first-child { border-left: 3px solid #2e7d32; }
    .case-table tr[data-status="fail"] td:first-child { border-left: 3px solid #c62828; }
    .case-table tr[data-status="error"] td:first-child { border-left: 3px solid #c62828; }
    .case-table tr[data-status="skipped"] td:first-child { border-left: 3px solid var(--snm-text-faint); }
    .status-pill {
      display: inline-block; padding: 1px 8px; border-radius: 999px;
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .status-pill[data-status="pass"] { background: rgba(46,125,50,0.14); color: #2e7d32; }
    .status-pill[data-status="fail"] { background: rgba(198,40,40,0.14); color: #c62828; }
    .status-pill[data-status="error"] { background: rgba(198,40,40,0.18); color: #c62828; font-style: italic; }
    .status-pill[data-status="skipped"] { background: var(--snm-bg-panel); color: var(--snm-text-muted); }
    .reasons { display: flex; flex-wrap: wrap; gap: 4px; }
    .reason-tag {
      font-size: 10px; padding: 1px 6px; border-radius: 4px;
      background: rgba(198,40,40,0.10); color: #c62828;
      font-family: monospace;
    }
  `],
})
export class EvalPageComponent implements OnInit {
  private readonly evalSvc = inject(EvalService);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotificationService);

  activeTab = 0;

  // Runs
  runs: EvalRun[] = [];
  loadingRuns = false;
  triggering = false;
  expandedRunId: number | null = null;
  runDetail: EvalRun | null = null;
  loadingDetail = false;

  // Cases
  cases: EvalCase[] = [];
  loadingCases = false;
  caseFilter = '';
  showInactive = false;
  caseNameById: Record<number, string> = {};

  ngOnInit(): void {
    this.loadRuns();
    this.loadCases();
  }

  // ---- runs ----------------------------------------------------------------

  loadRuns(): void {
    this.loadingRuns = true;
    this.evalSvc.listRuns(50).subscribe({
      next: (res) => {
        this.runs = res.items;
        this.loadingRuns = false;
      },
      error: (err) => {
        this.loadingRuns = false;
        this.notify.error(err?.error?.detail || 'Failed to load runs');
      },
    });
  }

  bandFor(run: EvalRun): 'green' | 'yellow' | 'red' {
    if (run.pass_rate >= 0.9) return 'green';
    if (run.pass_rate >= 0.6) return 'yellow';
    return 'red';
  }

  toggleRun(run: EvalRun): void {
    if (this.expandedRunId === run.eval_run_id) {
      this.expandedRunId = null;
      this.runDetail = null;
      return;
    }
    this.expandedRunId = run.eval_run_id;
    this.runDetail = null;
    this.loadingDetail = true;
    this.evalSvc.getRun(run.eval_run_id).subscribe({
      next: (full) => {
        this.runDetail = full;
        this.loadingDetail = false;
      },
      error: (err) => {
        this.loadingDetail = false;
        this.notify.error(err?.error?.detail || 'Failed to load run detail');
      },
    });
  }

  reasonDetail(r: { failure_detail: Record<string, unknown> | null }, reason: string): string {
    const blob = r.failure_detail?.[reason];
    return blob ? JSON.stringify(blob) : reason;
  }

  runNow(): void {
    this.triggerRun({});
  }

  runJust(c: EvalCase): void {
    this.triggerRun({ case_ids: [c.case_id] });
  }

  private triggerRun(payload: { tags?: string[]; case_ids?: number[] }): void {
    this.triggering = true;
    this.evalSvc.triggerRun(payload).subscribe({
      next: (run) => {
        this.triggering = false;
        this.notify.success(
          `Run #${run.eval_run_id}: ${run.cases_passed}/${run.cases_total} passed`
        );
        this.activeTab = 0;
        this.loadRuns();
        // Auto-expand the new run so its results are visible.
        this.expandedRunId = run.eval_run_id;
        this.runDetail = run;
      },
      error: (err) => {
        this.triggering = false;
        this.notify.error(err?.error?.detail || 'Run failed to start');
      },
    });
  }

  // ---- cases ---------------------------------------------------------------

  loadCases(): void {
    this.loadingCases = true;
    this.evalSvc.listCases(this.showInactive).subscribe({
      next: (res) => {
        this.cases = res.items;
        this.caseNameById = {};
        for (const c of this.cases) this.caseNameById[c.case_id] = c.name;
        this.loadingCases = false;
      },
      error: (err) => {
        this.loadingCases = false;
        this.notify.error(err?.error?.detail || 'Failed to load cases');
      },
    });
  }

  get filteredCases(): EvalCase[] {
    const f = this.caseFilter.trim().toLowerCase();
    if (!f) return this.cases;
    return this.cases.filter(c =>
      c.name.toLowerCase().includes(f) ||
      (c.tags || []).some(t => t.toLowerCase().includes(f))
    );
  }

  toggleActive(c: EvalCase): void {
    const next = !c.is_active;
    this.evalSvc.updateCase(c.case_id, { is_active: next }).subscribe({
      next: (updated) => {
        c.is_active = updated.is_active;
        this.notify.success(
          updated.is_active ? `Activated #${c.case_id}` : `Deactivated #${c.case_id}`
        );
      },
      error: (err) => {
        this.notify.error(err?.error?.detail || 'Update failed');
      },
    });
  }

  openCaseDialog(existing: EvalCase | null): void {
    const data: EvalCaseDialogData = { existing };
    const ref = this.dialog.open(EvalCaseDialogComponent, {
      data, width: '720px', maxWidth: '92vw',
    });
    ref.afterClosed().subscribe((saved: EvalCase | null | undefined) => {
      if (saved) this.loadCases();
    });
  }
}
