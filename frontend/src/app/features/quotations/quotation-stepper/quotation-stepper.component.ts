import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, computed, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Lifecycle stage stepper. Four canonical stages for the new workspace
 * (Phase 5 brought forward to Phase 1):
 *
 *   Quotation → Purchase Order → Viability → Annexure
 *
 * Each stage shows its own status sub-text (driven by the matching
 * per-stage entity, not the legacy collapsed ``QuotSummary.status``).
 * Click to navigate to that stage's tab group inside the workspace.
 *
 * Inputs:
 *   - ``currentStage`` (default 'quotation') — which station to render
 *     as active. Parent owns this state.
 *   - ``quotationStatus`` — drives the Quotation station's sub-status
 *     and reached state for the rest of the lifecycle.
 *   - ``poStatus`` — Stage-2 PO row status (Draft / Submitted /
 *     Rejected / null).
 *   - ``viabilityStatus`` — Stage-3 viability sheet status (Draft /
 *     Approved / null).
 *   - ``annexureStatus`` — Stage-4 annexure status (Draft / Approved
 *     / null).
 *
 * Emits:
 *   - ``stageSelected`` when the user clicks a station. Parent maps
 *     this to a tab-group switch.
 */

export type QuotStatus = 'Draft' | 'Approved' | 'Converted' | 'Reject' | 'Revised' | string;
export type PoStatus = 'Draft' | 'Submitted' | 'Rejected' | null | undefined;
export type ViabilityStatus = 'Draft' | 'Approved' | null | undefined;
export type AnnexureStatus = 'Draft' | 'Approved' | null | undefined;
export type StageKey = 'quotation' | 'po' | 'viability' | 'annexure';

interface Stop {
  key: StageKey;
  label: string;
  icon: string;
  /** true → solid highlight (this stage has been started or passed). */
  reached: boolean;
  /** true → user is currently viewing this stage. */
  active: boolean;
  /** Sub-text under the label, e.g. "approved" / "draft" / "PO received". */
  sub?: string;
  /** Mark the stop with the warning tone (e.g. Rejected). */
  error?: boolean;
  /** Mark the stop as locked-out (no entity exists yet). Still
   *  clickable so the user can navigate; content panel handles the
   *  empty state. */
  future?: boolean;
}

@Component({
  selector: 'app-quotation-stepper',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="stepper" [class.vertical]="orientation === 'vertical'">
      @for (s of stops(); track s.key; let last = $last) {
        <button type="button" class="stop"
          [class.reached]="s.reached"
          [class.active]="s.active"
          [class.error]="s.error"
          [class.future]="s.future"
          [matTooltip]="tooltipFor(s)"
          (click)="stageSelected.emit(s.key)">
          <div class="dot">
            <mat-icon>{{ s.icon }}</mat-icon>
          </div>
          <div class="label">{{ s.label }}</div>
          @if (s.sub) { <div class="sub">{{ s.sub }}</div> }
        </button>
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
      background: transparent;
      border: 0;
      padding: 4px 6px;
      cursor: pointer;
      border-radius: 10px;
      transition: background 0.18s ease;
    }
    .stop:hover { background: var(--snm-accent-subtle, rgba(58,107,181,0.08)); }
    .stop:focus-visible {
      outline: 2px solid var(--snm-accent);
      outline-offset: 2px;
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
    .dot mat-icon { font-size: 20px; width: 20px; height: 20px; }

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

    .stop.future .dot { opacity: 0.6; }
    .stop.future .label { color: var(--snm-text-faint); }

    .line {
      flex: 1 1 auto;
      min-width: 24px;
      height: 2px;
      margin-top: 21px;   /* centers on the dot inside the .stop button */
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

    /* ----- Vertical (Phase 5 side-rail) layout ----- */
    .stepper.vertical {
      flex-direction: column;
      align-items: stretch;
      padding: 12px;
      min-width: 220px;
      width: 100%;
      gap: 0;
      position: sticky;
      top: 12px;
    }
    .stepper.vertical .stop {
      flex-direction: row;
      align-items: center;
      justify-content: flex-start;
      gap: 12px;
      padding: 10px 12px;
      width: 100%;
      text-align: left;
    }
    .stepper.vertical .label {
      flex: 1;
      font-size: 13px;
      white-space: normal;
    }
    .stepper.vertical .sub {
      flex-shrink: 0;
      align-self: center;
    }
    /* Connector becomes a vertical line between dots in column mode. */
    .stepper.vertical .line {
      flex: 0 0 auto;
      width: 2px;
      height: 18px;
      margin: 0 0 0 30px;     /* aligns under the dot in column mode */
      align-self: flex-start;
    }
    .stepper.vertical .line.reached {
      background: linear-gradient(180deg, var(--snm-accent-dark), var(--snm-accent));
    }

    @media (max-width: 768px) {
      /* On phones the vertical rail flips back to a horizontal strip
         at the top so the active-stage card gets the full width. */
      .stepper.vertical {
        flex-direction: row;
        position: static;
        min-width: 0;
      }
      .stepper.vertical .stop {
        flex-direction: column;
        text-align: center;
        gap: 6px;
        padding: 4px 6px;
      }
      .stepper.vertical .line {
        width: auto;
        height: 2px;
        flex: 1 1 auto;
        margin-top: 17px;
        margin-left: 0;
      }
      .stepper.vertical .label { font-size: 11px; }
      .stepper.vertical .sub { display: none; }
    }
  `],
})
export class QuotationStepperComponent {
  @Input() set quotationStatus(v: QuotStatus | null | undefined) {
    this._status.set(v || 'Draft');
  }
  get quotationStatus(): QuotStatus { return this._status(); }

  @Input() set poStatus(v: PoStatus) { this._po.set(v || null); }
  get poStatus(): PoStatus { return this._po(); }

  @Input() set viabilityStatus(v: ViabilityStatus) { this._viab.set(v || null); }
  get viabilityStatus(): ViabilityStatus { return this._viab(); }

  @Input() set annexureStatus(v: AnnexureStatus) { this._ann.set(v || null); }
  get annexureStatus(): AnnexureStatus { return this._ann(); }

  @Input() set currentStage(v: StageKey) { this._current.set(v || 'quotation'); }
  get currentStage(): StageKey { return this._current(); }

  @Input() versionNo?: number;
  @Input() parentQuotId?: number | null;
  /** Layout orientation. ``horizontal`` (default) is the workspace
   *  header strip. ``vertical`` is the Phase-5 side-rail layout —
   *  stops stacked top-to-bottom in a sticky left column. */
  @Input() orientation: 'horizontal' | 'vertical' = 'horizontal';

  /** Emitted when the user clicks a station. Parent updates
   *  ``currentStage`` and re-renders the workspace's stage panel. */
  @Output() stageSelected = new EventEmitter<StageKey>();

  private _status = signal<QuotStatus>('Draft');
  private _po = signal<PoStatus>(null);
  private _viab = signal<ViabilityStatus>(null);
  private _ann = signal<AnnexureStatus>(null);
  private _current = signal<StageKey>('quotation');

  stops = computed<Stop[]>(() => {
    const s = this._status();
    const po = this._po();
    const v = this._viab();
    const a = this._ann();
    const isRevised = s === 'Revised';
    const isReject = s === 'Reject';

    // "Reached" = stage has been started (entity exists / status set).
    // The Quotation stage is always reached (always exists).
    const quotReached = true;
    // Stage 2 reached when the quotation is Converted OR a PO row
    // exists. (Phase-4 status simplification: legacy strings have
    // been migrated to ``Converted`` so we no longer enumerate them.)
    const poReached = po != null || s === 'Converted';
    const viabReached = v != null;
    const annReached = a != null;

    const current = this._current();
    const poDone = po === 'Submitted';
    const viabApproved = v === 'Approved';
    const annApproved = a === 'Approved';
    const poRejected = po === 'Rejected';

    return [
      {
        key: 'quotation',
        label: isRevised ? 'Quotation' : 'Quotation',
        icon: isReject ? 'cancel' : (isRevised ? 'history' : 'edit_note'),
        reached: quotReached,
        active: current === 'quotation',
        error: isReject,
        sub: this._quotSubLabel(s),
      },
      {
        key: 'po',
        label: 'Purchase Order',
        icon: poRejected ? 'cancel' : (poDone ? 'verified' : 'receipt_long'),
        reached: poReached,
        active: current === 'po',
        error: poRejected,
        future: !poReached,
        sub: poReached
          ? (po
              ? po.toLowerCase()
              : 'awaiting submit')
          : undefined,
      },
      {
        key: 'viability',
        label: 'Viability',
        icon: 'query_stats',
        reached: viabReached,
        active: current === 'viability',
        future: !viabReached,
        sub: viabReached
          ? (viabApproved ? 'approved' : 'draft')
          : undefined,
      },
      {
        key: 'annexure',
        label: 'Annexure',
        icon: 'description',
        reached: annReached,
        active: current === 'annexure',
        future: !annReached,
        sub: annReached
          ? (annApproved ? 'approved' : 'draft')
          : undefined,
      },
    ];
  });

  private _quotSubLabel(s: QuotStatus): string | undefined {
    switch (s) {
      case 'Draft': return 'draft';
      case 'Approved': return 'approved';
      case 'Converted': return 'converted';
      case 'Reject': return 'rejected';
      case 'Revised': return 'superseded';
      default: return undefined;
    }
  }

  connectorReached(i: number): boolean {
    const s = this.stops();
    return s[i].reached && s[i + 1]?.reached;
  }

  tooltipFor(s: Stop): string {
    switch (s.key) {
      case 'quotation':
        return s.error
          ? 'Quotation was rejected. Reactivate to resume.'
          : 'Stage 1 — Quotation: header, line items, terms & conditions.';
      case 'po':
        if (s.error) return 'PO was rejected; quotation is back at Approved.';
        if (!s.reached) return 'Stage 2 — Purchase Order. Locked until the quotation is Converted.';
        return 'Stage 2 — Purchase Order: PO header + final working sheet.';
      case 'viability':
        if (!s.reached) return 'Stage 3 — Viability. Locked until the PO is submitted.';
        return s.sub === 'approved'
          ? 'Stage 3 — Viability: approved.'
          : 'Stage 3 — Viability: draft, pending approval.';
      case 'annexure':
        if (!s.reached) return 'Stage 4 — Annexure. Locked until viability is approved.';
        return s.sub === 'approved'
          ? 'Stage 4 — Annexure: approved.'
          : 'Stage 4 — Annexure: draft, pending approval.';
    }
  }
}
