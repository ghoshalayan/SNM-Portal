/**
 * Reusable stage-shell for the post-Convert quotation flow.
 *
 * Wraps each stage (FWS, Viability, Annexure) in a consistent shell so
 * the user always sees the same three regions in the same place:
 *
 *   1. **Header** — icon + stage name, status pill, version label,
 *      optional Switch-Version button.
 *   2. **Next-step strip** — a single primary CTA paired with a
 *      one-line "what to do next" hint. This is the action the user
 *      came here to perform; it's always above the fold.
 *   3. **Body** — a content slot for the stage's editor (the line-
 *      items grid for FWS, the form for Annexure, etc.).
 *
 * Designed as the visual fix for the post-Convert UX complaint that
 * actions were scattered + buried under tabs. The shell does not own
 * any business logic — it emits ``primaryClick`` and ``switchClick``
 * and lets the host page do the work. That keeps it equally usable
 * for "Approve & Continue", "Generate", "Save & Close Cycle" — any
 * verb the host wants in the primary slot.
 */
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  VersionInlineItem,
  VersionInlinePickerComponent,
} from './version-inline-picker.component';

/** Drives the colored status pill on the header. */
export type StageStatus =
  | 'idle'       // nothing exists yet (e.g. Viability before Generate)
  | 'draft'      // exists, editable, not approved
  | 'approved'   // latest snapshot signed off
  | 'warn'       // attention needed (stale, rejected, etc.)
  | 'locked';    // gated until upstream is complete

export interface StagePrimaryCta {
  /** Button label, e.g. "Approve & Continue to Viability". */
  label: string;
  /** Material icon to render before the label. */
  icon?: string;
  /** True → renders as a flat outlined button (secondary tone). */
  outlined?: boolean;
  /** Disable the button (e.g. while a precondition is unmet). */
  disabled?: boolean;
  /** Replace the icon with a spinner while a round-trip is in flight. */
  busy?: boolean;
  /** Material color. Defaults to ``primary``. */
  color?: 'primary' | 'accent' | 'warn';
}

@Component({
  selector: 'app-stage-shell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    VersionInlinePickerComponent,
  ],
  template: `
    <section class="ss-wrap" [class.is-locked]="status === 'locked'">
      <!-- ---- HEADER ---- -->
      <header class="ss-head">
        <div class="ss-title">
          <mat-icon class="ss-title-icon">{{ stageIcon }}</mat-icon>
          <span class="ss-title-text">{{ stageName }}</span>
        </div>

        <div class="ss-meta">
          <span class="ss-status-pill" [attr.data-status]="status">
            {{ statusText || status }}
          </span>
          @if (versionLabel) {
            <span class="ss-version">{{ versionLabel }}</span>
          }
          @if (approvedAt) {
            <span class="ss-when">
              on {{ approvedAt | date: 'mediumDate' }}
              @if (approvedByName) {
                <span class="ss-who">· by {{ approvedByName }}</span>
              }
            </span>
          }
        </div>

        <div class="ss-head-actions">
          @if (showVersionControl) {
            <app-version-inline-picker
              [items]="versionItems"
              [currentId]="currentVersionId"
              [busy]="!canSwitchVersion"
              [headLabel]="stageName + ' versions'"
              (picked)="versionPicked.emit($event)">
            </app-version-inline-picker>
          }
        </div>
      </header>

      <!-- ---- NEXT-STEP STRIP ---- -->
      @if (nextStepHint || primaryCta) {
        <div class="ss-next" [class.is-warn]="status === 'warn'">
          @if (nextStepHint) {
            <div class="ss-next-text">
              <mat-icon class="ss-next-arrow">arrow_forward</mat-icon>
              <span><strong>Next step:</strong> {{ nextStepHint }}</span>
            </div>
          }
          @if (primaryCta) {
            <button
              [class.mat-raised-button]="!primaryCta.outlined"
              [class.mat-stroked-button]="primaryCta.outlined"
              [attr.color]="primaryCta.color || 'primary'"
              mat-raised-button
              [color]="primaryCta.color || 'primary'"
              [disabled]="primaryCta.disabled || primaryCta.busy"
              (click)="primaryClick.emit()"
              class="ss-cta">
              @if (primaryCta.busy) {
                <mat-spinner diameter="18" class="ss-cta-spinner"></mat-spinner>
              } @else if (primaryCta.icon) {
                <mat-icon>{{ primaryCta.icon }}</mat-icon>
              }
              <span>{{ primaryCta.label }}</span>
            </button>
          }
        </div>
      }

      <!-- ---- BODY (editor slot) ---- -->
      <div class="ss-body">
        <ng-content></ng-content>
      </div>
    </section>
  `,
  styles: [`
    :host { display: block; }

    .ss-wrap {
      display: flex; flex-direction: column;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 10px;
      overflow: hidden;
    }
    .ss-wrap.is-locked {
      opacity: 0.7;
    }

    /* ---- Header bar ---- */
    .ss-head {
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: 16px;
      padding: 14px 18px;
      background: var(--snm-bg-panel);
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .ss-title {
      display: flex; align-items: center; gap: 10px;
    }
    .ss-title-icon {
      color: var(--snm-accent);
      font-size: 24px; width: 24px; height: 24px;
    }
    .ss-title-text {
      font-size: 16px;
      font-weight: 600;
      color: var(--snm-text-primary);
    }

    .ss-meta {
      display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
      font-size: 13px;
      color: var(--snm-text-muted);
      min-width: 0;
    }
    .ss-status-pill {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      background: var(--snm-glass-bg);
      color: var(--snm-text-secondary);
      border: 1px solid var(--snm-border-divider);
    }
    .ss-status-pill[data-status='approved'] {
      background: rgba(58, 107, 181, 0.12);
      color: var(--snm-accent-dark);
      border-color: var(--snm-accent);
    }
    .ss-status-pill[data-status='draft'] {
      background: rgba(200, 150, 30, 0.12);
      color: rgba(160, 110, 0, 0.95);
      border-color: rgba(200, 150, 30, 0.4);
    }
    .ss-status-pill[data-status='warn'] {
      background: rgba(198, 40, 40, 0.10);
      color: #c62828;
      border-color: rgba(198, 40, 40, 0.4);
    }
    .ss-status-pill[data-status='locked'] {
      background: var(--snm-bg-panel);
      color: var(--snm-text-faint);
    }
    .ss-version {
      font-weight: 700;
      color: var(--snm-text-primary);
      font-size: 13px;
    }
    .ss-when {
      color: var(--snm-text-muted);
      font-size: 12px;
    }
    .ss-who { color: var(--snm-text-faint); }

    .ss-head-actions {
      display: flex; gap: 8px; align-items: center;
      flex: 0 0 auto;
    }
    .ss-head-actions button mat-icon { margin-right: 4px; }

    /* ---- Next-step strip ---- */
    .ss-next {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 18px;
      background: linear-gradient(
        90deg,
        rgba(58, 107, 181, 0.06),
        rgba(58, 107, 181, 0.02)
      );
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .ss-next.is-warn {
      background: linear-gradient(
        90deg,
        rgba(200, 150, 30, 0.10),
        rgba(200, 150, 30, 0.02)
      );
    }
    .ss-next-text {
      display: flex; align-items: center; gap: 8px;
      font-size: 13px;
      color: var(--snm-text-secondary);
      line-height: 1.4;
      min-width: 0;
    }
    .ss-next-text strong {
      color: var(--snm-text-primary);
      font-weight: 600;
      margin-right: 4px;
    }
    .ss-next-arrow {
      color: var(--snm-accent);
      font-size: 18px; width: 18px; height: 18px;
    }
    .ss-cta {
      flex: 0 0 auto;
      min-width: 200px;
    }
    .ss-cta mat-icon { margin-right: 6px; }
    .ss-cta-spinner {
      display: inline-block;
      vertical-align: middle;
      margin-right: 6px;
    }

    /* ---- Body (slot for the editor) ---- */
    .ss-body {
      padding: 16px 18px;
      background: var(--snm-bg-card);
    }

    /* ---- Compact mobile ---- */
    @media (max-width: 768px) {
      .ss-head {
        grid-template-columns: 1fr;
        gap: 8px;
      }
      .ss-head-actions {
        justify-content: flex-end;
      }
      .ss-next {
        flex-direction: column;
        align-items: stretch;
      }
      .ss-cta { width: 100%; min-width: 0; }
    }
  `],
})
export class StageShellComponent {
  /** Stage display name shown in the header — "Final Working Sheet",
   *  "Viability Sheet", "Annexure". */
  @Input({ required: true }) stageName!: string;

  /** Material icon for the header. Suggested:
   *    FWS       → "inventory_2"
   *    Viability → "query_stats"
   *    Annexure  → "description" */
  @Input({ required: true }) stageIcon!: string;

  /** Drives the status pill's color + label. */
  @Input() status: StageStatus = 'idle';
  /** Optional override for the pill text. Defaults to the status key
   *  in upper-case ("APPROVED", "DRAFT", …). */
  @Input() statusText: string | null = null;

  /** Current version label, e.g. ``"C1-V2"``. */
  @Input() versionLabel: string | null = null;
  @Input() approvedAt: string | null = null;
  @Input() approvedByName: string | null = null;

  /** One-line "what to do next" guidance. Plain English; ends without
   *  punctuation. Example: "Approve to unlock the Viability stage". */
  @Input() nextStepHint: string | null = null;

  /** Configures the primary CTA. ``null`` hides it entirely (e.g.
   *  when the user lacks the underlying permission). */
  @Input() primaryCta: StagePrimaryCta | null = null;

  /** Show the inline version picker. Usually true once at least one
   *  approval snapshot exists. */
  @Input() showVersionControl = false;
  /** Disable the picker while a load is in flight. */
  @Input() canSwitchVersion = true;
  /** Snapshot rows the picker should render. Empty list = chip
   *  shows "No versions yet". */
  @Input() versionItems: VersionInlineItem[] = [];
  /** Id of the snapshot currently loaded into the editor. */
  @Input() currentVersionId: number | null = null;

  /** Fires when the user clicks the primary CTA. */
  @Output() primaryClick = new EventEmitter<void>();
  /** Fires when the user picks a row in the inline version picker.
   *  Host opens the Save-as-Draft / Discard switch dialog. */
  @Output() versionPicked = new EventEmitter<number>();
}
