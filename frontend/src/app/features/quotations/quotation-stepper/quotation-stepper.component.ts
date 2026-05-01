import { CommonModule } from '@angular/common';
import { Component, Input, computed, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Horizontal timeline showing where a quotation sits in its lifecycle.
 *
 * Stations:
 *   Draft → Approved → Matured → Viability → Annexure
 *
 * Side-states:
 *   - status === 'Reject'   → shown inline on whichever station is current
 *                             (Reject only happens from Approved, so it sits at step 2).
 *   - status === 'Revised'  → label on step 1; signals this version is frozen.
 *
 * `viabilityStatus` is optional; when null the Viability step shows a dotted
 * outline (not yet generated).
 */

export type QuotStatus = 'Draft' | 'Approved' | 'Matured' | 'Reject' | 'Revised' | string;
export type ViabilityStatus = 'Draft' | 'Approved' | null | undefined;

interface Stop {
  key: 'draft' | 'approved' | 'matured' | 'viability' | 'annexure';
  label: string;
  icon: string;
  /** true → solid highlight (this is "current" or passed) */
  reached: boolean;
  /** true → this is the active stop */
  active: boolean;
  /** Optional mini-label under the main one (e.g. "Draft" for viability). */
  sub?: string;
  /** Mark as error/reject tone. */
  error?: boolean;
  /** Future/disabled — e.g. Annexure until we build it. */
  future?: boolean;
}

@Component({
  selector: 'app-quotation-stepper',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="stepper">
      @for (s of stops(); track s.key; let last = $last) {
        <div class="stop"
          [class.reached]="s.reached"
          [class.active]="s.active"
          [class.error]="s.error"
          [class.future]="s.future"
          [matTooltip]="tooltipFor(s)">
          <div class="dot">
            <mat-icon>{{ s.icon }}</mat-icon>
          </div>
          <div class="label">{{ s.label }}</div>
          @if (s.sub) { <div class="sub">{{ s.sub }}</div> }
        </div>
        @if (!last) {
          <div class="line" [class.reached]="connectorReached($index)"></div>
        }
      }
    </div>
  `,
  styles: [`
    :host { display: block; margin: 12px 0 18px; }

    .stepper {
      display: flex;
      align-items: flex-start;
      gap: 0;
      padding: 16px 20px;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-glass-border-heavy);
      border-radius: 14px;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
    }

    .stop {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      min-width: 0;
      flex: 0 0 auto;
    }

    .dot {
      width: 36px; height: 36px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      background: var(--snm-bg-panel);
      border: 2px dashed var(--snm-border-divider);
      color: var(--snm-text-muted);
      transition: all 0.2s ease;
    }
    .dot mat-icon {
      font-size: 20px; width: 20px; height: 20px;
    }

    .label {
      font-size: 12px;
      font-weight: 600;
      color: var(--snm-text-muted);
      white-space: nowrap;
    }
    .sub {
      font-size: 10px;
      color: var(--snm-text-faint);
      line-height: 1.1;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .stop.reached .dot {
      background: linear-gradient(135deg, var(--snm-accent), var(--snm-accent-dark));
      border-color: var(--snm-accent-dark);
      border-style: solid;
      color: var(--snm-text-on-primary);
      box-shadow: 0 2px 8px var(--snm-accent-shadow);
    }
    .stop.reached .label { color: var(--snm-text-primary); }

    .stop.active .dot {
      transform: scale(1.08);
      box-shadow: 0 0 0 6px var(--snm-accent-subtle), 0 2px 10px var(--snm-accent-shadow);
    }
    .stop.active .label { color: var(--snm-accent-dark); font-weight: 700; }

    .stop.error .dot {
      background: linear-gradient(135deg, #ef5350, #c62828);
      border-color: #c62828;
      color: #fff;
      box-shadow: 0 2px 8px rgba(198,40,40,0.3);
    }
    .stop.error .label { color: #c62828; }

    .stop.future .dot { opacity: 0.5; }
    .stop.future .label { color: var(--snm-text-faint); }

    .line {
      flex: 1 1 auto;
      min-width: 24px;
      height: 2px;
      margin-top: 17px;   /* centers on the dot */
      background: var(--snm-border-divider);
      transition: background 0.2s ease;
    }
    .line.reached {
      background: linear-gradient(90deg, var(--snm-accent-dark), var(--snm-accent));
    }

    @media (max-width: 768px) {
      .stepper { padding: 12px 8px; }
      .label { font-size: 11px; }
      .sub { display: none; }
      .dot { width: 32px; height: 32px; }
      .dot mat-icon { font-size: 18px; width: 18px; height: 18px; }
    }
  `],
})
export class QuotationStepperComponent {
  @Input() set quotationStatus(v: QuotStatus | null | undefined) {
    this._status.set(v || 'Draft');
  }
  get quotationStatus(): QuotStatus { return this._status(); }

  @Input() set viabilityStatus(v: ViabilityStatus) {
    this._viab.set(v || null);
  }
  get viabilityStatus(): ViabilityStatus { return this._viab(); }

  @Input() versionNo?: number;
  @Input() parentQuotId?: number | null;

  private _status = signal<QuotStatus>('Draft');
  private _viab = signal<ViabilityStatus>(null);

  stops = computed<Stop[]>(() => {
    const s = this._status();
    const v = this._viab();
    const isRevised = s === 'Revised';
    const isReject = s === 'Reject';

    // Derive viability & annexure sub-states from quotation.status too — it
    // progresses Matured → ViabilityGenerated → ViabilityApproved →
    // AnnexureGenerated → AnnexureApproved as the user moves through stages.
    const viabReached =
      v != null
      || s === 'ViabilityGenerated' || s === 'ViabilityApproved'
      || s === 'AnnexureGenerated' || s === 'AnnexureApproved';
    const viabApproved =
      v === 'Approved'
      || s === 'ViabilityApproved'
      || s === 'AnnexureGenerated' || s === 'AnnexureApproved';
    const annexureReached = s === 'AnnexureGenerated' || s === 'AnnexureApproved';
    const annexureApproved = s === 'AnnexureApproved';

    const reached = {
      draft: true,
      approved: this._hasPassed('approved'),
      matured: this._hasPassed('matured'),
      viability: viabReached,
      annexure: annexureReached,
    };

    const activeKey = this._activeKey();

    const stops: Stop[] = [
      {
        key: 'draft',
        label: isRevised ? 'Revised' : 'Draft',
        icon: isRevised ? 'history' : 'edit_note',
        reached: reached.draft,
        active: activeKey === 'draft',
        sub: isRevised ? 'superseded' : undefined,
      },
      {
        key: 'approved',
        label: isReject ? 'Rejected' : 'Approved',
        icon: isReject ? 'cancel' : 'check_circle',
        reached: reached.approved || isReject,
        active: activeKey === 'approved',
        error: isReject,
      },
      {
        key: 'matured',
        label: 'Matured',
        icon: 'verified',
        reached: reached.matured,
        active: activeKey === 'matured',
        sub: reached.matured ? 'PO received' : undefined,
      },
      {
        key: 'viability',
        label: 'Viability',
        icon: 'query_stats',
        reached: reached.viability,
        active: activeKey === 'viability',
        sub: reached.viability ? (viabApproved ? 'approved' : 'draft') : undefined,
      },
      {
        key: 'annexure',
        label: 'Annexure',
        icon: 'description',
        reached: reached.annexure,
        active: activeKey === 'annexure',
        sub: reached.annexure ? (annexureApproved ? 'approved' : 'draft') : undefined,
        future: !reached.annexure,
      },
    ];
    return stops;
  });

  connectorReached(i: number): boolean {
    const s = this.stops();
    return s[i].reached && s[i + 1]?.reached;
  }

  tooltipFor(s: Stop): string {
    switch (s.key) {
      case 'draft':
        return s.label === 'Revised'
          ? 'This version has been superseded by a newer revision.'
          : 'Quotation is in draft — not yet approved.';
      case 'approved':
        return s.error
          ? 'Approved quotation was rejected. It can be reverted.'
          : 'Quotation has been approved.';
      case 'matured':
        return s.reached
          ? 'PO received — quotation matured.'
          : 'Waiting for purchase order to mark as matured.';
      case 'viability':
        if (!s.reached) return 'Viability sheet not yet generated.';
        return s.sub === 'approved'
          ? 'Viability sheet is approved.'
          : 'Viability sheet is in draft — pending approval.';
      case 'annexure':
        return 'Annexure generation — coming soon.';
    }
  }

  // --- private helpers ---
  private _order = ['draft', 'approved', 'matured', 'viability', 'annexure'] as const;

  private _hasPassed(stop: (typeof this._order)[number]): boolean {
    const s = this._status();
    const v = this._viab();
    const post = new Set([
      'Approved', 'Matured',
      'ViabilityGenerated', 'ViabilityApproved',
      'AnnexureGenerated', 'AnnexureApproved',
    ]);
    switch (stop) {
      case 'approved':
        return post.has(s) || v != null;
      case 'matured':
        return (
          s === 'Matured'
          || s === 'ViabilityGenerated' || s === 'ViabilityApproved'
          || s === 'AnnexureGenerated' || s === 'AnnexureApproved'
          || v != null
        );
      default:
        return false;
    }
  }

  private _activeKey(): Stop['key'] {
    const s = this._status();
    const v = this._viab();
    if (s === 'AnnexureApproved') return 'annexure';
    if (s === 'AnnexureGenerated') return 'annexure';
    if (s === 'ViabilityApproved') return 'annexure';  // next step is generate annexure
    if (s === 'ViabilityGenerated' || v === 'Draft') return 'viability';
    if (v === 'Approved') return 'annexure';
    if (s === 'Matured') return 'viability';  // next action is generate viability
    if (s === 'Approved') return 'matured';
    if (s === 'Reject') return 'approved';
    return 'draft';
  }
}
