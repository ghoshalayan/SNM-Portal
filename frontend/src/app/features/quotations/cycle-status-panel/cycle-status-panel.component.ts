/**
 * Cycle status rollup panel (Slice F of the soft-flow rollout).
 *
 * A glanceable, single-row summary of where the current cycle sits
 * across all four stages. Self-fetching: takes ``quotId`` + ``cycleId``
 * + ``cycleNo`` and queries the four soft-flow endpoints in parallel.
 *
 *   PO/LOIs: 3        FWS: C1-V2 (3 versions)
 *   Viability: Approved C1-V1     Annexure: Draft
 *
 * Designed to mount above the stepper so the user can see, without
 * navigating stage-by-stage, what the cycle currently contains.
 *
 * Chip click emits ``stageClicked`` — the parent decides whether to
 * jump the stepper or ignore the event (currently used for navigation).
 */
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  OnInit,
  Output,
  SimpleChanges,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { ApiService } from '../../../core/services/api.service';

type Stage = 'po' | 'fws' | 'viability' | 'annexure';

interface CyclePoRowSlim {
  quotPOId: number;
  isLOI: boolean;
}

interface CycleBundleSlim {
  purchaseOrders: CyclePoRowSlim[];
}

interface FwsSnapshotSlim {
  snapshotId: number;
  versionNo: number;
  label: string;
}

interface ViabilityBundleSlim {
  viability: {
    viabilityId: number;
    versionNo: number;
    status: string;
  } | null;
}

interface AnnexureSlim {
  annexureId: number;
  versionNo: number;
  status: string;
}

interface RollupRow {
  stage: Stage;
  label: string;
  primary: string;     // e.g. "3 formal · 1 LOI", "C1-V2", "Approved"
  detail?: string;     // optional secondary line
  status?: 'ok' | 'warn' | 'idle' | 'approved';
}

@Component({
  selector: 'app-cycle-status-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatProgressSpinnerModule, MatTooltipModule],
  template: `
    <div class="csp-wrap">
      @if (loading) {
        <div class="csp-loading">
          <mat-spinner diameter="16"></mat-spinner>
          <span>Loading cycle status…</span>
        </div>
      } @else {
        @for (row of rows; track row.stage) {
          <button class="csp-chip"
                  [class.is-approved]="row.status === 'approved'"
                  [class.is-warn]="row.status === 'warn'"
                  [class.is-idle]="row.status === 'idle'"
                  (click)="onChipClick(row.stage)"
                  [matTooltip]="'Jump to ' + row.label">
            <mat-icon class="csp-icon">{{ iconFor(row.stage) }}</mat-icon>
            <div class="csp-text">
              <span class="csp-label">{{ row.label }}</span>
              <span class="csp-primary">{{ row.primary }}</span>
              @if (row.detail) {
                <span class="csp-detail">{{ row.detail }}</span>
              }
            </div>
          </button>
        }
      }
    </div>
  `,
  styles: [`
    .csp-wrap {
      display: flex; flex-wrap: wrap; gap: 8px;
      padding: 8px 10px;
      margin-bottom: 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
    }
    .csp-loading {
      display: flex; align-items: center; gap: 10px;
      padding: 4px 8px;
      color: var(--snm-text-muted);
      font-size: 12px;
    }
    .csp-chip {
      display: flex; align-items: center; gap: 8px;
      padding: 6px 12px;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-field);
      border-radius: 6px;
      cursor: pointer;
      font-family: inherit;
      transition: background 0.15s, border-color 0.15s;
      text-align: left;
    }
    .csp-chip:hover {
      background: var(--snm-glass-bg);
      border-color: var(--snm-accent);
    }
    .csp-chip.is-approved { border-left: 3px solid var(--snm-accent); }
    .csp-chip.is-warn { border-left: 3px solid rgba(200, 150, 30, 0.85); }
    .csp-chip.is-idle { opacity: 0.7; }

    .csp-icon {
      color: var(--snm-accent);
      flex: 0 0 auto;
    }
    .csp-text {
      display: flex; flex-direction: column;
      font-size: 12px;
      line-height: 1.3;
    }
    .csp-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--snm-text-secondary);
      letter-spacing: 0.3px;
    }
    .csp-primary {
      font-weight: 600;
      color: var(--snm-text-primary);
    }
    .csp-detail {
      font-size: 11px;
      color: var(--snm-text-muted);
    }
  `],
})
export class CycleStatusPanelComponent implements OnInit, OnChanges {
  @Input({ required: true }) quotId!: number;
  @Input({ required: true }) cycleId!: number;
  @Input({ required: true }) cycleNo!: number;

  /** Emitted when the user clicks a stage chip — parent decides whether
   *  to navigate the stepper. */
  @Output() stageClicked = new EventEmitter<Stage>();

  rows: RollupRow[] = [];
  loading = false;

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.refresh();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Re-fetch on cycle change so the panel always reflects the
    // currently selected cycle.
    if (changes['cycleId'] && !changes['cycleId'].firstChange) {
      this.refresh();
    }
  }

  iconFor(stage: Stage): string {
    switch (stage) {
      case 'po': return 'receipt_long';
      case 'fws': return 'inventory_2';
      case 'viability': return 'analytics';
      case 'annexure': return 'description';
    }
  }

  onChipClick(stage: Stage): void {
    this.stageClicked.emit(stage);
  }

  private refresh(): void {
    if (!this.quotId || !this.cycleId) return;
    this.loading = true;
    const base = `/quotations/${this.quotId}`;
    forkJoin({
      cycleBundle: this.api.get<CycleBundleSlim>(
        `${base}/cycles/${this.cycleId}/bundle`,
      ).pipe(catchError(() => of<CycleBundleSlim | null>(null))),
      fwsSnapshots: this.api.get<{ items: FwsSnapshotSlim[] }>(
        `${base}/cycles/${this.cycleId}/fws/approval-snapshots`,
      ).pipe(
        map((r) => r?.items || []),
        catchError(() => of<FwsSnapshotSlim[]>([])),
      ),
      viability: this.api.get<ViabilityBundleSlim>(
        `${base}/viability`,
      ).pipe(catchError(() => of<ViabilityBundleSlim | null>(null))),
      annexure: this.api.get<AnnexureSlim | null>(
        `${base}/annexure`,
      ).pipe(catchError(() => of<AnnexureSlim | null>(null))),
    }).subscribe({
      next: ({ cycleBundle, fwsSnapshots, viability, annexure }) => {
        this.rows = this.buildRows(cycleBundle, fwsSnapshots, viability, annexure);
        this.loading = false;
        // OnPush: subscribe callbacks don't auto-mark the view dirty,
        // so without this the spinner stays on-screen forever.
        this.cdr.markForCheck();
      },
      error: () => {
        // Best-effort — if even the forkJoin fails outright we hide
        // the panel rather than show errors. The user can still
        // navigate the stages manually via the stepper.
        this.rows = [];
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  private buildRows(
    bundle: CycleBundleSlim | null,
    fws: FwsSnapshotSlim[],
    viab: ViabilityBundleSlim | null,
    ann: AnnexureSlim | null,
  ): RollupRow[] {
    // PO/LOI
    const formalCount = (bundle?.purchaseOrders || []).filter((p) => !p.isLOI).length;
    const loiCount = (bundle?.purchaseOrders || []).filter((p) => p.isLOI).length;
    const poParts: string[] = [];
    if (formalCount) poParts.push(`${formalCount} formal`);
    if (loiCount) poParts.push(`${loiCount} LOI`);

    // FWS
    const fwsLatest = fws[0];
    const fwsRow: RollupRow = {
      stage: 'fws',
      label: 'Final Working Sheet',
      primary: fwsLatest ? fwsLatest.label : 'Not approved yet',
      detail:
        fws.length > 1
          ? `${fws.length} versions`
          : fws.length === 1
            ? '1 version'
            : 'Live draft only',
      status: fws.length ? 'approved' : 'idle',
    };

    // Viability
    const v = viab?.viability;
    const vRow: RollupRow = {
      stage: 'viability',
      label: 'Viability',
      primary: v ? `${v.status} · C${this.cycleNo}-V${v.versionNo}` : 'Not generated',
      status: v?.status === 'Approved' ? 'approved' : v ? 'warn' : 'idle',
    };

    // Annexure
    const aRow: RollupRow = {
      stage: 'annexure',
      label: 'Annexure',
      primary: ann ? `${ann.status} · C${this.cycleNo}-V${ann.versionNo}` : 'Not generated',
      status: ann?.status === 'Approved' ? 'approved' : ann ? 'warn' : 'idle',
    };

    return [
      {
        stage: 'po',
        label: 'PO / LOI',
        primary: poParts.length ? poParts.join(' · ') : 'None yet',
        status: formalCount ? 'approved' : 'idle',
      },
      fwsRow,
      vRow,
      aRow,
    ];
  }
}
