/**
 * Generate-Annexure dialog (Slice E of the soft-flow rollout).
 *
 * Two source pickers per design:
 *
 *   * **Viability version** — defaults to the latest active viability
 *     sheet on the quotation. The picker is informational today
 *     (almost always one row visible). When fork-on-Approve produces
 *     multiple sheet rows the picker fills out naturally.
 *
 *   * **PO/LOI within the cycle** — the meaningful pick. Lists every
 *     active PO/LOI row in the cycle so the user can choose which
 *     one's header data (customer, billing, consignee, PO no/date)
 *     drives the annexure header. Defaults to the formal PO.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import { ApiService } from '../../../core/services/api.service';
import { MatDialog } from '@angular/material/dialog';
import {
  VersionPickerComponent,
  VersionItem,
} from '../../../shared/components/version-picker/version-picker.component';
import { SnapshotViewerDialogComponent } from '../../../shared/components/snapshot-viewer/snapshot-viewer-dialog.component';

export interface GenerateAnnexureDialogData {
  quotId: number;
  cycleId: number;
  cycleNo: number;
  /** Override the dialog title. Defaults to "Generate Annexure".
   *  Re-generate flow uses "Re-generate Annexure". */
  title?: string;
  /** Override the primary button label. Defaults to "Generate". */
  confirmLabel?: string;
  /** Override the intro hint paragraph. Defaults to the generate copy. */
  hint?: string;
  /** Pre-select a viability id on open. */
  preSelectedViabilityId?: number | null;
  /** Pre-select a PO/LOI id on open. */
  preSelectedPoId?: number | null;
  /** Phase B follow-up: list every Viability **snapshot** in the
   *  cycle (not just the current head). When true, the picker shows
   *  V1, V2, V3, … with the latest pre-selected; on confirm the
   *  result includes ``sourcedFromViabilitySnapshotId``. */
  listAllViabilityVersions?: boolean;
}

export interface GenerateAnnexureDialogResult {
  /** Specific viability sheet id; ``null`` = let backend pick latest. */
  sourcedFromViabilityId: number | null;
  /** Specific PO/LOI id within the cycle; ``null`` = legacy single-PO. */
  sourcedFromPOId: number | null;
  /** Phase B: picked viability snapshot id (when the dialog was
   *  opened in "list all versions" mode). Backend uses this to read
   *  the frozen lines from the snapshot blob instead of the live
   *  sheet head. */
  sourcedFromViabilitySnapshotId?: number | null;
}

interface CyclePoRow {
  quotPOId: number;
  poNo: string | null;
  poDate?: string | null;
  isLOI: boolean;
  loiSequence?: number | null;
  status?: string | null;
}

interface ViabilityBundle {
  viability: {
    viabilityId: number;
    versionNo: number;
    status: string;
    approvedon?: string | null;
  } | null;
}

interface CycleBundle {
  cycle: { quotOrderCycleId: number; cycleNo: number };
  purchaseOrders: CyclePoRow[];
}

interface ViabilitySnapshotRow {
  snapshotId: number;
  viabilityId: number;
  versionNo: number;
  approvedAt: string;
  approvedByName?: string | null;
}

@Component({
  selector: 'app-generate-annexure-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    VersionPickerComponent,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">description</mat-icon>
      {{ data.title || 'Generate Annexure' }}
    </h2>
    <mat-dialog-content class="content">
      <p class="hint">{{ effectiveHint }}</p>

      <div class="picker-section">
        <div class="section-label">Source viability sheet</div>
        <app-version-picker
          [items]="viabilityItems"
          [selectedId]="selectedViabilityId"
          [loading]="loadingViability"
          [emptyMessage]="'No approved viability — annexure generation will fail until viability is approved.'"
          (selected)="onViabilitySelect($event)"
          (preview)="onPreview($event, 'viability')">
        </app-version-picker>
      </div>

      <div class="picker-section">
        <div class="section-label">Source PO / LOI in this cycle</div>
        <app-version-picker
          [items]="poItems"
          [selectedId]="selectedPoId"
          [loading]="loadingPos"
          [emptyMessage]="'No PO/LOI in this cycle yet — append one first.'"
          (selected)="onPoSelect($event)">
        </app-version-picker>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="cancel()">Cancel</button>
      <button
        mat-raised-button
        color="primary"
        (click)="confirm()"
        [disabled]="loadingViability || loadingPos">
        <mat-icon>description</mat-icon> {{ data.confirmLabel || 'Generate' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon {
      vertical-align: middle;
      margin-right: 6px;
      color: var(--snm-accent);
    }
    .content {
      min-width: 480px;
      max-width: 580px;
      padding-top: 6px;
      max-height: 65vh;
      overflow-y: auto;
    }
    .hint {
      font-size: 13px;
      color: var(--snm-text-muted);
      margin: 0 0 16px;
      line-height: 1.5;
    }
    .picker-section {
      display: flex; flex-direction: column; gap: 6px;
      margin-bottom: 16px;
    }
    .picker-section:last-child { margin-bottom: 0; }
    .section-label {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--snm-text-secondary);
      letter-spacing: 0.4px;
    }
  `],
})
export class GenerateAnnexureDialogComponent implements OnInit {
  viabilityItems: VersionItem[] = [];
  poItems: VersionItem[] = [];

  /** Sheet-head id the user picked (or pre-selected). Sent to the
   *  backend as ``sourcedFromViabilityId``. In list-all-versions mode
   *  the items represent snapshots; we also track the picked snapshot
   *  id below. */
  selectedViabilityId: number | null = null;
  /** Snapshot id the user picked when running in list-all-versions
   *  mode. Sent as ``sourcedFromViabilitySnapshotId``. ``null`` when
   *  the dialog is in legacy single-head mode. */
  selectedViabilitySnapshotId: number | null = null;
  selectedPoId: number | null = null;

  loadingViability = true;
  loadingPos = true;

  /** Default intro hint, used when the caller doesn't pass one. */
  private readonly defaultHint =
    "Pick the upstream sources for the annexure. The defaults are " +
    "the latest approved viability and the cycle's formal PO — most " +
    "flows just confirm and continue.";

  get effectiveHint(): string {
    return this.data.hint || this.defaultHint;
  }

  constructor(
    private api: ApiService,
    private dialog: MatDialog,
    public dialogRef: MatDialogRef<
      GenerateAnnexureDialogComponent,
      GenerateAnnexureDialogResult
    >,
    @Inject(MAT_DIALOG_DATA) public data: GenerateAnnexureDialogData,
  ) {}

  ngOnInit(): void {
    if (this.data.listAllViabilityVersions) {
      this.loadViabilitySnapshotChain();
    } else {
      this.loadViabilityHeadOnly();
    }

    // PO/LOI list — pull the cycle bundle and surface every active
    // row. The first formal (non-LOI) PO gets pre-selected because
    // that's the canonical annexure header source.
    this.api
      .get<CycleBundle>(
        `/quotations/${this.data.quotId}/cycles/${this.data.cycleId}/bundle`,
      )
      .subscribe({
        next: (res) => {
          const pos = res?.purchaseOrders || [];
          this.poItems = pos.map((p) => ({
            id: p.quotPOId,
            label: p.poNo || `(no PO #) · id ${p.quotPOId}`,
            sub: this.formatPoSub(p),
            approvedAt: p.poDate ?? null,
          }));
          const formal = pos.find((p) => !p.isLOI);
          this.selectedPoId =
            this.data.preSelectedPoId
            ?? (formal ?? pos[0])?.quotPOId
            ?? null;
          this.loadingPos = false;
        },
        error: () => {
          this.poItems = [];
          this.loadingPos = false;
        },
      });
  }

  /** Legacy single-head mode: list just the current active Viability
   *  sheet (one row). Used by the first-time Generate path where the
   *  user only needs to confirm the head pick. */
  private loadViabilityHeadOnly(): void {
    this.api
      .get<ViabilityBundle>(`/quotations/${this.data.quotId}/viability`)
      .subscribe({
        next: (res) => {
          const v = res?.viability;
          if (v) {
            this.viabilityItems = [
              {
                id: v.viabilityId,
                label: `C${this.data.cycleNo}-V${v.versionNo}`,
                isApproved: v.status === 'Approved',
                approvedAt: v.approvedon ?? null,
                sub: v.status,
                previewUrl:
                  v.status === 'Approved'
                    ? `/viability/${v.viabilityId}/approval-snapshots/latest`
                    : null,
              },
            ];
            this.selectedViabilityId =
              this.data.preSelectedViabilityId ?? v.viabilityId;
          }
          this.loadingViability = false;
        },
        error: () => {
          this.viabilityItems = [];
          this.loadingViability = false;
        },
      });
  }

  /** Re-generate mode: list every Viability **snapshot** in the
   *  cycle, newest first, and pre-select the latest. The picker row
   *  carries a ``snapshotId`` plus the ``viabilityId`` of the sheet
   *  the snapshot came from; ``onViabilitySelect`` resolves both when
   *  the user clicks a row. */
  private loadViabilitySnapshotChain(): void {
    if (this.data.preSelectedViabilityId == null) {
      // No anchor sheet to start from — fall back to head-only.
      this.loadViabilityHeadOnly();
      return;
    }
    this.api
      .get<{ items: ViabilitySnapshotRow[] }>(
        `/viability/${this.data.preSelectedViabilityId}/approval-snapshots`,
      )
      .subscribe({
        next: (res) => {
          const snaps = res?.items || [];
          if (snaps.length === 0) {
            // No snapshots yet — fall back to head-only view so the
            // user can still confirm the current head.
            this.loadViabilityHeadOnly();
            return;
          }
          // Newest first; pre-select the latest (which the backend
          // returns as the first row of the descending-sorted list).
          this.viabilityItems = snaps.map((s) => ({
            id: s.snapshotId,
            label: `C${this.data.cycleNo}-V${s.versionNo}`,
            isApproved: true,
            approvedAt: s.approvedAt,
            approvedByName: s.approvedByName ?? null,
            previewUrl: `/viability/${s.viabilityId}/approval-snapshots/${s.snapshotId}`,
            // Stash the source sheet id so confirm() can fan it out
            // alongside the snapshot id.
            sub: `sheet id ${s.viabilityId}`,
          }));
          this.viabilityIdBySnapshot = new Map(
            snaps.map((s) => [s.snapshotId, s.viabilityId] as const),
          );
          const latest = snaps[0];
          this.selectedViabilitySnapshotId = latest.snapshotId;
          this.selectedViabilityId = latest.viabilityId;
          this.loadingViability = false;
        },
        error: () => {
          this.loadViabilityHeadOnly();
        },
      });
  }

  /** Lookup table populated by ``loadViabilitySnapshotChain``; lets
   *  ``onViabilitySelect`` resolve the source sheet for a picked
   *  snapshot id without re-querying. */
  private viabilityIdBySnapshot = new Map<number, number>();

  private formatPoSub(p: CyclePoRow): string {
    const kind = p.isLOI ? 'LOI' : 'PO';
    const status = p.status ? ` · ${p.status}` : '';
    const seq =
      p.loiSequence != null ? ` · seq ${p.loiSequence}` : '';
    return `${kind}${status}${seq}`;
  }

  onViabilitySelect(id: number): void {
    // Only treat the id as a snapshot id when it was actually emitted
    // by a snapshot-row pick — detect this via the lookup map populated
    // by loadViabilitySnapshotChain. If the dialog ran in
    // ``listAllViabilityVersions`` mode but the snapshot fetch returned
    // empty (and we fell back to loadViabilityHeadOnly), the picker
    // rows carry sheet ids; treating those as snapshot ids causes a
    // 404 like "Viability snapshot 32 not found" on confirm.
    if (this.viabilityIdBySnapshot.has(id)) {
      this.selectedViabilitySnapshotId = id;
      this.selectedViabilityId = this.viabilityIdBySnapshot.get(id)!;
    } else {
      this.selectedViabilityId = id;
      this.selectedViabilitySnapshotId = null;
    }
  }
  onPoSelect(id: number): void {
    this.selectedPoId = id;
  }

  /** Slice G — open the snapshot viewer for the previewed row.
   *  ``kind`` is passed to compose the dialog title; PO rows
   *  don't carry a ``previewUrl`` so this only ever fires on
   *  viability rows today. */
  onPreview(item: VersionItem, kind: 'viability' | 'po'): void {
    if (!item.previewUrl) return;
    const label =
      kind === 'viability' ? 'Viability Sheet' : 'Purchase Order';
    this.dialog.open(SnapshotViewerDialogComponent, {
      data: { url: item.previewUrl, title: `${item.label} — ${label}` },
      width: '740px',
    });
  }

  confirm(): void {
    this.dialogRef.close({
      sourcedFromViabilityId: this.selectedViabilityId,
      sourcedFromPOId: this.selectedPoId,
      sourcedFromViabilitySnapshotId: this.selectedViabilitySnapshotId,
    });
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
