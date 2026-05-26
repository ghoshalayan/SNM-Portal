/**
 * KPI Studio scheduled-jobs admin page (T-003).
 *
 * Lists every registered job, shows its trigger, last-run summary, and
 * a "Run now" button. Click a row to expand its recent-runs history.
 *
 * SuperAdmin-only by virtue of the backend gate (``kpi:settings``).
 * The sidebar entry is hidden for everyone else by the standard
 * has-permission directive.
 */
import { CommonModule, DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { NotificationService } from '../../../../core/services/notification.service';
import {
  ScheduledJob,
  ScheduledJobRun,
  ScheduledJobRunStatus,
} from '../../models/schema.types';
import { JobsService } from '../../services/jobs.service';

@Component({
  selector: 'app-jobs-page',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatCardModule, MatIconModule,
    MatProgressSpinnerModule, MatTooltipModule,
  ],
  template: `
    <div class="page-head">
      <div class="page-head-left">
        <mat-icon class="page-head-icon">schedule</mat-icon>
        <div>
          <h2 class="page-title">Scheduled Jobs</h2>
          <div class="page-subtitle">
            In-process scheduler. Jobs are declared in code; this page
            shows what's registered and lets you fire one manually.
          </div>
        </div>
      </div>
      <div class="page-head-actions">
        <span class="scheduler-status"
              [class.is-active]="schedulerActive"
              [class.is-down]="!loading && !schedulerActive">
          <mat-icon>{{ schedulerActive ? 'play_circle' : 'pause_circle' }}</mat-icon>
          {{ schedulerActive ? 'Scheduler running' : 'Scheduler not running' }}
        </span>
        <button mat-stroked-button color="primary"
                (click)="loadJobs()"
                [disabled]="loading">
          <mat-icon>refresh</mat-icon> Refresh
        </button>
      </div>
    </div>

    @if (loading) {
      <div class="loading"><mat-spinner diameter="32"></mat-spinner></div>
    } @else if (jobs.length === 0) {
      <div class="empty">
        <mat-icon>schedule</mat-icon>
        <p>No jobs registered. Add one via
          <code>kpi_studio.services.scheduled_jobs.register_all</code>.</p>
      </div>
    } @else {
      <div class="job-list">
        @for (job of jobs; track job.name) {
          <mat-card class="job-card">
            <div class="job-row" (click)="toggleJob(job)">
              <div class="job-name">
                <mat-icon class="job-icon"
                          [class.is-enabled]="job.enabled">
                  {{ job.enabled ? 'check_circle' : 'remove_circle' }}
                </mat-icon>
                <div>
                  <strong>{{ job.name }}</strong>
                  <div class="job-desc">{{ job.description || '—' }}</div>
                </div>
              </div>
              <div class="job-trigger" [matTooltip]="triggerTooltip(job)">
                <mat-icon>schedule</mat-icon>
                {{ triggerLabel(job) }}
              </div>
              <div class="job-last">
                @if (job.last_run_status) {
                  <span class="status-pill"
                        [attr.data-status]="job.last_run_status">
                    {{ job.last_run_status }}
                  </span>
                  <span class="when">
                    {{ job.last_run_started_at | date:'dd MMM, HH:mm:ss' }}
                    @if (job.last_run_duration_ms !== null) {
                      <span class="muted">({{ job.last_run_duration_ms }}ms)</span>
                    }
                  </span>
                } @else {
                  <span class="muted">never run</span>
                }
              </div>
              <div class="job-actions" (click)="$event.stopPropagation()">
                <button mat-stroked-button color="primary"
                        (click)="runNow(job)"
                        [disabled]="triggering[job.name]">
                  @if (triggering[job.name]) {
                    <mat-spinner diameter="14" class="cta-spinner"></mat-spinner>
                  } @else {
                    <mat-icon>play_arrow</mat-icon>
                  }
                  Run now
                </button>
              </div>
              <mat-icon class="expand-icon">
                {{ expandedJobName === job.name ? 'expand_less' : 'expand_more' }}
              </mat-icon>
            </div>

            @if (expandedJobName === job.name) {
              <div class="job-detail">
                @if (loadingRuns) {
                  <mat-spinner diameter="22"></mat-spinner>
                } @else if (jobRuns.length === 0) {
                  <p class="muted">No run history yet.</p>
                } @else {
                  <table class="run-table">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>Started</th>
                        <th>Finished</th>
                        <th class="num">Items</th>
                        <th class="num">Time (ms)</th>
                        <th>Trigger</th>
                        <th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (r of jobRuns; track r.run_id) {
                        <tr [attr.data-status]="r.status">
                          <td>
                            <span class="status-pill"
                                  [attr.data-status]="r.status">
                              {{ r.status }}
                            </span>
                          </td>
                          <td>{{ r.started_at | date:'dd MMM, HH:mm:ss' }}</td>
                          <td>
                            @if (r.finished_at) {
                              {{ r.finished_at | date:'HH:mm:ss' }}
                            } @else { — }
                          </td>
                          <td class="num">{{ r.items_processed ?? '—' }}</td>
                          <td class="num">{{ r.duration_ms ?? '—' }}</td>
                          <td>{{ r.trigger_source }}</td>
                          <td class="err">{{ r.error || '' }}</td>
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
  `,
  styles: [`
    :host { display: block; padding: 16px 20px 32px; }

    .page-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
    }
    .page-head-left { display: flex; align-items: center; gap: 12px; }
    .page-head-icon { font-size: 30px; width: 30px; height: 30px; color: var(--snm-accent); }
    .page-title { margin: 0; font-size: 18px; font-weight: 700; color: var(--snm-text-primary); }
    .page-subtitle {
      font-size: 12px; color: var(--snm-text-muted); max-width: 560px;
      line-height: 1.4; margin-top: 2px;
    }
    .page-head-actions {
      display: flex; gap: 12px; align-items: center;
    }
    .scheduler-status {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 10px; border-radius: 999px; font-size: 12px;
      background: var(--snm-bg-panel);
      color: var(--snm-text-muted);
    }
    .scheduler-status.is-active { color: #2e7d32; background: rgba(46,125,50,0.10); }
    .scheduler-status.is-down { color: #c62828; background: rgba(198,40,40,0.10); }
    .cta-spinner { display: inline-block; margin-right: 6px; vertical-align: middle; }

    .loading { display: flex; justify-content: center; padding: 40px 0; }
    .empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 6px; padding: 40px 12px; color: var(--snm-text-muted);
    }
    .empty mat-icon { font-size: 36px; width: 36px; height: 36px; opacity: 0.55; }
    .empty code {
      font-family: monospace; font-size: 11px;
      background: var(--snm-bg-card); padding: 1px 6px; border-radius: 4px;
    }

    .job-list { display: flex; flex-direction: column; gap: 8px; }
    .job-card { padding: 0; overflow: hidden; }
    .job-row {
      display: grid;
      grid-template-columns: 2fr 1.2fr 1.4fr auto 24px;
      align-items: center; gap: 12px;
      padding: 10px 14px;
      cursor: pointer;
    }
    .job-row:hover { background: var(--snm-bg-panel); }
    .job-name { display: flex; align-items: center; gap: 10px; }
    .job-icon.is-enabled { color: #2e7d32; }
    .job-icon { color: var(--snm-text-faint); }
    .job-desc {
      font-size: 11px; color: var(--snm-text-muted); margin-top: 2px;
    }
    .job-trigger {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px; color: var(--snm-text-secondary);
    }
    .job-trigger mat-icon {
      font-size: 16px; width: 16px; height: 16px; color: var(--snm-text-muted);
    }
    .job-last { font-size: 12px; }
    .job-last .when {
      margin-left: 6px; color: var(--snm-text-muted);
      font-variant-numeric: tabular-nums;
    }
    .job-actions { display: flex; gap: 4px; }
    .muted { color: var(--snm-text-faint); font-style: italic; }
    .expand-icon { color: var(--snm-text-muted); }

    .job-detail {
      padding: 12px 14px;
      border-top: 1px solid var(--snm-border-divider);
      background: var(--snm-bg-panel);
    }

    .run-table {
      width: 100%; border-collapse: collapse;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px; overflow: hidden;
    }
    .run-table th, .run-table td {
      padding: 6px 10px; border-bottom: 1px solid var(--snm-border-divider);
      text-align: left; font-size: 12px;
    }
    .run-table th {
      background: var(--snm-bg-header-row); color: var(--snm-text-secondary);
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
      font-size: 11px;
    }
    .run-table td.num, .run-table th.num {
      text-align: right; font-variant-numeric: tabular-nums;
    }
    .run-table td.err {
      font-family: monospace; font-size: 11px; color: #c62828;
      max-width: 320px; overflow: hidden; text-overflow: ellipsis;
    }
    .run-table tr[data-status="success"] td:first-child { border-left: 3px solid #2e7d32; }
    .run-table tr[data-status="failed"] td:first-child { border-left: 3px solid #c62828; }
    .run-table tr[data-status="running"] td:first-child { border-left: 3px solid var(--snm-accent); }
    .run-table tr[data-status="cancelled"] td:first-child { border-left: 3px solid var(--snm-text-faint); }

    .status-pill {
      display: inline-block; padding: 1px 8px; border-radius: 999px;
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .status-pill[data-status="success"] { background: rgba(46,125,50,0.14); color: #2e7d32; }
    .status-pill[data-status="failed"] { background: rgba(198,40,40,0.14); color: #c62828; }
    .status-pill[data-status="running"] { background: rgba(58,107,181,0.14); color: var(--snm-accent-dark); }
    .status-pill[data-status="cancelled"] { background: var(--snm-bg-panel); color: var(--snm-text-muted); }
  `],
})
export class JobsPageComponent implements OnInit, OnDestroy {
  private readonly jobsSvc = inject(JobsService);
  private readonly notify = inject(NotificationService);

  jobs: ScheduledJob[] = [];
  loading = false;
  schedulerActive = false;
  triggering: Record<string, boolean> = {};

  expandedJobName: string | null = null;
  jobRuns: ScheduledJobRun[] = [];
  loadingRuns = false;

  private refreshTimer: number | null = null;

  ngOnInit(): void {
    this.loadJobs();
    // Auto-refresh every 30s so a running job's last-run row updates
    // without the user clicking refresh. Cleared on destroy.
    this.refreshTimer = window.setInterval(() => this.loadJobs(true), 30_000);
  }

  ngOnDestroy(): void {
    if (this.refreshTimer !== null) {
      clearInterval(this.refreshTimer);
    }
  }

  loadJobs(silent = false): void {
    if (!silent) this.loading = true;
    this.jobsSvc.listJobs().subscribe({
      next: (res) => {
        this.jobs = res.items;
        this.schedulerActive = res.scheduler_active;
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        if (!silent) {
          this.notify.error(err?.error?.detail || 'Failed to load jobs');
        }
      },
    });
  }

  triggerLabel(job: ScheduledJob): string {
    const t = job.trigger;
    if (t.kind === 'interval' && t.interval_seconds !== null) {
      const s = t.interval_seconds;
      if (s % 3600 === 0) return `every ${s / 3600}h`;
      if (s % 60 === 0) return `every ${s / 60}m`;
      return `every ${s}s`;
    }
    if (t.kind === 'cron' && t.cron_expression) {
      return `cron: ${t.cron_expression}`;
    }
    return '—';
  }

  triggerTooltip(job: ScheduledJob): string {
    const next = job.trigger.next_fire_at;
    return next ? `Next fire: ${next}` : 'Next fire time unavailable';
  }

  statusBand(s: ScheduledJobRunStatus | null): string {
    return s || '';
  }

  toggleJob(job: ScheduledJob): void {
    if (this.expandedJobName === job.name) {
      this.expandedJobName = null;
      this.jobRuns = [];
      return;
    }
    this.expandedJobName = job.name;
    this.loadRuns(job.name);
  }

  private loadRuns(name: string): void {
    this.loadingRuns = true;
    this.jobsSvc.listRuns(name, 50).subscribe({
      next: (res) => {
        this.jobRuns = res.items;
        this.loadingRuns = false;
      },
      error: (err) => {
        this.loadingRuns = false;
        this.notify.error(err?.error?.detail || 'Failed to load runs');
      },
    });
  }

  runNow(job: ScheduledJob): void {
    this.triggering[job.name] = true;
    this.jobsSvc.triggerJob(job.name).subscribe({
      next: (res) => {
        this.triggering[job.name] = false;
        this.notify.success(
          `${job.name}: run #${res.run_id} finished with status "${res.status}"`
        );
        this.loadJobs(true);
        if (this.expandedJobName === job.name) this.loadRuns(job.name);
      },
      error: (err) => {
        this.triggering[job.name] = false;
        this.notify.error(err?.error?.detail || `${job.name} failed to start`);
      },
    });
  }
}
