import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
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
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { NlService } from '../../services/nl.service';
import { NlAgentStep, NlGenerateResponse } from '../../models/schema.types';

export interface GeneratePromptResult {
  sql: string;
  explanation: string;
}

@Component({
  selector: 'app-generate-prompt-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, MatDialogModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatProgressBarModule, MatChipsModule,
    MatButtonToggleModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="ai-icon">auto_awesome</mat-icon>
      Generate SQL from prompt
      <!-- A7-build marker. If you do not see this pill in the dialog
           title, your browser is serving a cached copy. Hard-refresh
           (Ctrl+Shift+R) or restart the frontend dev server.
           NOTE: do NOT put backticks in this comment - they close the
           surrounding JS template literal. Burned twice on this. -->
      <span class="build-pill">A7 · agent</span>
    </h2>

    <mat-dialog-content>
      <p class="hint">
        Describe what you want to see in plain English.
        The model will write a SELECT against the live schema.
      </p>

      <mat-form-field appearance="outline" class="prompt-field">
        <mat-label>Your question</mat-label>
        <textarea matInput rows="3" maxlength="2000" cdkFocusInitial
                  [ngModel]="prompt()"
                  (ngModelChange)="prompt.set($event)"
                  placeholder="e.g. Top 10 customers by quotation value this fiscal year"
                  (keydown.meta.enter)="generate()"
                  (keydown.control.enter)="generate()"></textarea>
        <mat-hint>{{ prompt().length }} / 2000 · Ctrl/⌘+Enter to generate</mat-hint>
      </mat-form-field>

      <!-- Mode toggle. Step-by-step (agent) is the default — model
           inspects the schema iteratively. Quick (single) one-shots the
           prompt with the whole schema in context — cheaper, less
           accurate on complex questions. -->
      <div class="mode-row">
        <mat-button-toggle-group [value]="mode()" (change)="onModeChange($event.value)" hideSingleSelectionIndicator>
          <mat-button-toggle value="agent" matTooltip="Agent inspects the schema step-by-step before writing SQL">
            <mat-icon>route</mat-icon>
            Step-by-step
          </mat-button-toggle>
          <mat-button-toggle value="single" matTooltip="One-shot prompt with full schema in context">
            <mat-icon>bolt</mat-icon>
            Quick
          </mat-button-toggle>
        </mat-button-toggle-group>
      </div>

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <div *ngIf="error()" class="error-banner">
        <mat-icon>error_outline</mat-icon>
        <span>{{ error() }}</span>
      </div>

      <div *ngIf="result() as r" class="result-block">
        <div class="result-meta">
          <mat-chip class="provider-chip" disabled>{{ r.provider }} · {{ r.model }}</mat-chip>
          <span>{{ r.latency_ms }}ms</span>
          <span *ngIf="r.usage['total_tokens']">{{ r.usage['total_tokens'] }} tokens</span>
        </div>

        <p class="explanation">{{ r.explanation || 'No explanation provided.' }}</p>

        <!-- Agent process — always rendered for any agent-mode run so
             the reasoning is visible without an extra click. Even when
             r.steps is empty we render a placeholder card so the
             user can see the run completed.
             (Don't use markdown backticks in this comment — they would
              terminate the surrounding JS template literal.) -->
        <section *ngIf="r.mode !== 'single'" class="timeline-section">
          <header class="timeline-header">
            <mat-icon class="route-icon">route</mat-icon>
            <strong>Agent reasoning</strong>
            <span class="timeline-meta">
              {{ r.steps.length }} step{{ r.steps.length === 1 ? '' : 's' }}
              · {{ r.iterations }} iter
              · {{ r.total_tokens }} tokens
            </span>
            <span *ngIf="!r.succeeded" class="abort-pill">{{ r.error }}</span>
          </header>

          <ol class="timeline" *ngIf="r.steps.length; else noSteps">
            <li *ngFor="let s of r.steps; let i = index"
                class="step"
                [class.error]="s.type === 'tool_error' || s.type === 'abort'"
                [class.final]="s.type === 'final'">
              <div class="step-head">
                <span class="step-num">{{ i + 1 }}</span>
                <mat-icon class="step-icon">{{ stepIcon(s) }}</mat-icon>
                <strong>{{ stepTitle(s) }}</strong>
                <span *ngIf="s.latency_ms != null" class="step-latency">{{ s.latency_ms }}ms</span>
              </div>
              <pre *ngIf="s.args" class="step-args">{{ formatArgs(s.args) }}</pre>
              <pre *ngIf="s.output != null" class="step-output">{{ formatOutput(s.output) }}</pre>
              <p *ngIf="s.error" class="step-error">{{ s.error }}</p>
            </li>
          </ol>
          <ng-template #noSteps>
            <p class="no-steps">
              The agent didn't record any steps. The model may not support
              tool-use, or it terminated immediately. Try the
              <a (click)="setMode('single')" class="link">Quick mode</a>
              as a fallback, or inspect the raw response below.
            </p>
          </ng-template>
        </section>

        <!-- Diagnostic toggle — full JSON response for debugging when
             the timeline doesn't show what the user expects. -->
        <details class="raw-toggle">
          <summary>Show raw response (debug)</summary>
          <pre class="raw-json">{{ formatRaw(r) }}</pre>
        </details>

        <ng-container *ngIf="r.sql; else cannotAnswer">
          <label class="sql-label">Generated SQL</label>
          <pre class="sql-output">{{ r.sql }}</pre>

          <div *ngIf="!r.validation.ok" class="validation-warning">
            <mat-icon>warning</mat-icon>
            <div>
              <strong>Safety validator flagged this SQL:</strong>
              <p>{{ r.validation.message }}</p>
              <ul *ngIf="r.validation.findings.length">
                <li *ngFor="let f of r.validation.findings">{{ f }}</li>
              </ul>
              <p class="warn-hint">You can still apply it and edit by hand, or rephrase your prompt.</p>
            </div>
          </div>
        </ng-container>

        <ng-template #cannotAnswer>
          <p class="empty-sql">The model declined to write SQL for this prompt.</p>
        </ng-template>
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="null" [disabled]="loading()">Cancel</button>
      <button mat-stroked-button color="primary"
              (click)="generate()"
              [disabled]="!canGenerate()">
        <mat-icon>auto_awesome</mat-icon>
        {{ result() ? 'Regenerate' : 'Generate' }}
      </button>
      <button mat-flat-button color="primary"
              (click)="apply()"
              [disabled]="!canApply()">
        Use this SQL
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2 mat-dialog-title { display: flex; align-items: center; gap: 8px; }
    .ai-icon { color: var(--snm-accent, #4a90e2); }
    .build-pill {
      margin-left: auto;
      padding: 2px 8px;
      background: rgba(74, 144, 226, 0.15);
      color: var(--snm-accent, #4a90e2);
      border-radius: 999px;
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .hint { color: var(--snm-text-muted); font-size: 0.85rem; margin: 0 0 12px; }
    .prompt-field { width: 100%; }
    .error-banner {
      display: flex; gap: 8px; padding: 12px; margin-top: 12px;
      background: rgba(229, 57, 53, 0.08);
      border: 1px solid var(--snm-error, #e53935);
      border-radius: 6px; color: var(--snm-error, #c62828);
      font-size: 0.85rem; align-items: center;
    }
    .result-block { margin-top: 16px; display: flex; flex-direction: column; gap: 10px; }
    .result-meta {
      display: flex; gap: 10px; align-items: center;
      font-size: 0.75rem; color: var(--snm-text-muted);
    }
    .provider-chip { font-size: 0.7rem; }
    .explanation {
      margin: 0; padding: 10px 12px;
      background: var(--snm-bg-panel, #f5f7fb);
      border-left: 3px solid var(--snm-accent, #4a90e2);
      border-radius: 4px; font-size: 0.9rem;
    }
    .sql-label {
      font-size: 0.8rem; font-weight: 500; color: var(--snm-text-secondary);
      margin-top: 4px;
    }
    .sql-output {
      margin: 0; padding: 12px;
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      font-size: 0.82rem; line-height: 1.5;
      background: var(--snm-bg-panel, #fafafa);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 6px;
      max-height: 220px; overflow: auto;
      white-space: pre-wrap; word-break: break-word;
    }
    .validation-warning {
      display: flex; gap: 8px; padding: 12px;
      background: rgba(255, 167, 38, 0.1);
      border: 1px solid #ffa726;
      border-radius: 6px; font-size: 0.82rem;
      mat-icon { color: #ef6c00; flex-shrink: 0; }
      strong { color: var(--snm-text-primary); }
      p { margin: 4px 0; }
      .warn-hint { color: var(--snm-text-muted); font-style: italic; }
      ul { margin: 4px 0; padding-left: 18px; }
    }
    .empty-sql {
      color: var(--snm-text-muted); font-style: italic; padding: 12px;
      background: var(--snm-bg-panel, #fafafa); border-radius: 6px;
    }
    /* Mode toggle */
    .mode-row {
      display: flex; justify-content: flex-start;
      margin: 0 0 12px;
    }
    .mode-row mat-button-toggle mat-icon {
      font-size: 16px; width: 16px; height: 16px; vertical-align: middle;
      margin-right: 4px;
    }
    /* Agent timeline (always visible — no expansion panel) */
    .timeline-section {
      display: flex; flex-direction: column; gap: 8px;
      padding: 10px 12px;
      background: var(--snm-bg-panel, #f7f8fa);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 6px;
    }
    .timeline-header {
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
      font-size: 0.85rem;
      strong { color: var(--snm-text-primary); }
    }
    .timeline-meta {
      color: var(--snm-text-muted); font-size: 0.75rem;
      margin-left: auto;
    }
    .route-icon {
      color: var(--snm-accent, #4a90e2);
      font-size: 18px; width: 18px; height: 18px;
    }
    .abort-pill {
      padding: 1px 6px;
      background: rgba(229, 57, 53, 0.12);
      color: var(--snm-error, #c62828);
      border-radius: 3px; font-size: 0.7rem;
    }
    .step-num {
      flex-shrink: 0;
      display: inline-flex; align-items: center; justify-content: center;
      width: 18px; height: 18px;
      background: var(--snm-accent, #4a90e2); color: white;
      border-radius: 50%;
      font-size: 0.7rem; font-weight: 600;
    }
    .step.final .step-num { background: #2e7d32; }
    .step.error .step-num { background: var(--snm-error, #e53935); }
    .timeline {
      list-style: none; padding: 0; margin: 0;
      display: flex; flex-direction: column; gap: 8px;
    }
    .step {
      padding: 8px 10px; border-radius: 4px;
      background: var(--snm-bg-card, #fff);
      border-left: 3px solid var(--snm-accent, #4a90e2);
    }
    .step.final { border-left-color: #50c878; }
    .step.error { border-left-color: var(--snm-error, #e53935); }
    .step-head {
      display: flex; align-items: center; gap: 6px;
      font-size: 0.85rem;
    }
    .step-icon {
      font-size: 16px; width: 16px; height: 16px;
      color: var(--snm-text-muted);
    }
    .step.final .step-icon { color: #2e7d32; }
    .step.error .step-icon { color: var(--snm-error, #e53935); }
    .step-latency { margin-left: auto; color: var(--snm-text-muted); font-size: 0.7rem; }
    .step-args, .step-output {
      margin: 6px 0 0; padding: 6px 8px;
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      font-size: 0.75rem; line-height: 1.4;
      background: var(--snm-bg-card, white);
      border-radius: 3px; max-height: 140px; overflow: auto;
      white-space: pre-wrap; word-break: break-word;
      color: var(--snm-text-secondary);
    }
    .step-error {
      margin: 6px 0 0; padding: 6px 8px;
      background: rgba(229, 57, 53, 0.06);
      color: var(--snm-error, #c62828);
      border-radius: 3px; font-size: 0.8rem;
    }
    .no-steps {
      margin: 0; padding: 10px 12px;
      background: var(--snm-bg-card, white);
      border: 1px dashed var(--snm-border-divider, #ccc);
      border-radius: 4px;
      color: var(--snm-text-muted); font-size: 0.85rem;
    }
    .no-steps .link { color: var(--snm-accent); cursor: pointer; text-decoration: underline; }
    /* Raw-response diagnostic */
    .raw-toggle {
      margin-top: 6px;
      summary {
        cursor: pointer; color: var(--snm-text-muted);
        font-size: 0.75rem; user-select: none;
      }
    }
    .raw-json {
      margin: 8px 0 0; padding: 8px 10px;
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      font-size: 0.7rem; line-height: 1.4;
      background: var(--snm-bg-panel, #f7f7f9);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 4px;
      max-height: 240px; overflow: auto;
      white-space: pre-wrap; word-break: break-word;
      color: var(--snm-text-secondary);
    }
  `],
})
export class GeneratePromptDialogComponent {
  private readonly nl = inject(NlService);
  private readonly destroyRef = inject(DestroyRef);

  readonly prompt = signal('');
  readonly loading = signal(false);
  readonly result = signal<NlGenerateResponse | null>(null);
  readonly error = signal<string | null>(null);
  /** ``agent`` (step-by-step, default) | ``single`` (one-shot, faster, less accurate). */
  readonly mode = signal<'agent' | 'single'>('agent');

  readonly canGenerate = computed(() => this.prompt().trim().length > 0 && !this.loading());
  /** "Use this SQL" requires non-empty generated SQL — even if validation
   * warned, we let the user pull it in to edit. */
  readonly canApply = computed(() => !!this.result()?.sql);

  constructor(private readonly ref: MatDialogRef<GeneratePromptDialogComponent>) {}

  onModeChange(m: 'agent' | 'single'): void {
    this.mode.set(m);
    // Don't auto-regenerate — user clicks Generate when ready.
  }

  /** Used by the "Try Quick mode" link in the no-steps fallback. */
  setMode(m: 'agent' | 'single'): void {
    this.mode.set(m);
  }

  generate(): void {
    if (!this.canGenerate()) return;
    this.loading.set(true);
    this.error.set(null);
    this.nl.generate({ prompt: this.prompt().trim(), mode: this.mode() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.loading.set(false);
          this.result.set(r);
          // Diagnostic — surfaces the raw response in DevTools so a user
          // can confirm the mode + steps the backend returned without
          // needing to open the network tab. Cheap; remove after Phase B.
          // eslint-disable-next-line no-console
          console.log('[nl/generate] response:', r);
        },
        error: err => {
          this.loading.set(false);
          this.result.set(null);
          const detail = err?.error?.detail;
          if (typeof detail === 'string') this.error.set(detail);
          else if (detail?.message) this.error.set(detail.message);
          else this.error.set('Generation failed.');
        },
      });
  }

  apply(): void {
    const r = this.result();
    if (!r?.sql) return;
    this.ref.close({ sql: r.sql, explanation: r.explanation } satisfies GeneratePromptResult);
  }

  // ---- Timeline rendering helpers ---------------------------------------

  stepIcon(s: NlAgentStep): string {
    switch (s.type) {
      case 'final':       return 'check_circle';
      case 'tool_error':  return 'error_outline';
      case 'abort':       return 'block';
      case 'thought':     return 'psychology';
      default:            return this.toolIcon(s.tool);
    }
  }

  /** Pick a Material icon per tool name so the timeline scans visually. */
  private toolIcon(tool: string | null | undefined): string {
    switch (tool) {
      case 'list_tables':          return 'list_alt';
      case 'describe_table':       return 'view_column';
      case 'peek_distinct_values': return 'data_exploration';
      case 'validate_sql':         return 'verified';
      case 'propose_sql':          return 'check_circle';
      default:                     return 'extension';
    }
  }

  stepTitle(s: NlAgentStep): string {
    if (s.type === 'thought') return 'Model reply';
    if (s.type === 'abort')   return 'Aborted';
    if (s.type === 'final')   return 'Final SQL proposed';
    return s.tool ?? 'tool';
  }

  /** Pretty-print args / output dicts. Truncates long strings so the
   * timeline stays scannable; the full payload is still in the audit log. */
  formatArgs(args: Record<string, any> | null | undefined): string {
    if (!args) return '';
    return JSON.stringify(args, null, 2);
  }

  formatOutput(output: any): string {
    if (output == null) return '';
    let str: string;
    try {
      str = typeof output === 'string' ? output : JSON.stringify(output, null, 2);
    } catch {
      str = String(output);
    }
    // Cap so a list_tables of 200+ tables doesn't blow up the dialog.
    if (str.length > 1500) {
      return str.slice(0, 1500) + `\n… (${str.length - 1500} more characters)`;
    }
    return str;
  }

  /** Pretty-print the full response for the diagnostic toggle. Capped
   * at 8 KB so a huge agent run doesn't slow the dialog. */
  formatRaw(r: NlGenerateResponse): string {
    let str: string;
    try {
      str = JSON.stringify(r, null, 2);
    } catch {
      str = String(r);
    }
    if (str.length > 8000) {
      return str.slice(0, 8000) + `\n… (${str.length - 8000} more characters truncated)`;
    }
    return str;
  }
}
