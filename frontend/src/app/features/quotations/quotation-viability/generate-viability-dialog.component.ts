/**
 * Generate-Viability dialog.
 *
 * Lets the user pick the source for a fresh Viability sheet. Two
 * source sections in one dialog (Phase B):
 *
 *   * **FWS Versions** — Live FWS (default) + any approved FWS
 *     snapshot in the current cycle. Sources line items from the
 *     working sheet.
 *   * **Past Viability Versions** — any approved Viability snapshot
 *     of the current viability head. Carries goal-seek state and
 *     orderedQty forward; useful when the user wants to iterate
 *     from a prior approval rather than reset from FWS.
 *
 * Only one row across both pickers can be selected at a time; picking
 * in one section clears the other. On confirm the dialog returns
 * exactly one of ``sourcedFromFWSSnapshotId`` or
 * ``sourcedFromViabilitySnapshotId`` (or neither, meaning Live FWS).
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
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/services/api.service';
import {
  VersionItem,
  VersionPickerComponent,
} from '../../../shared/components/version-picker/version-picker.component';
import { SnapshotViewerDialogComponent } from '../../../shared/components/snapshot-viewer/snapshot-viewer-dialog.component';
import { MatDialog } from '@angular/material/dialog';

export interface GenerateViabilityDialogData {
  quotId: number;
  cycleId: number;
  cycleNo: number;
  /** Current viability head id. When set, the dialog also lists past
   *  Viability snapshots as a second source section. Omit for the
   *  first-time generate path (no viability head exists yet). */
  viabilityId?: number | null;
}

export interface GenerateViabilityDialogResult {
  /** Picked FWS snapshot id, or ``null`` for Live FWS. Mutually
   *  exclusive with ``sourcedFromViabilitySnapshotId``. */
  sourcedFromFWSSnapshotId: number | null;
  /** Picked past-Viability snapshot id. ``null`` when the user chose
   *  an FWS source instead. */
  sourcedFromViabilitySnapshotId: number | null;
}

interface FwsSnapshotRow {
  snapshotId: number;
  label: string;
  versionNo: number;
  approvedAt: string;
  approvedByName?: string;
}

interface ViabilitySnapshotRow {
  snapshotId: number;
  versionNo: number;
  approvedAt: string;
  approvedByName?: string;
}

type PickedKind = 'fws' | 'viability';

@Component({
  selector: 'app-generate-viability-dialog',
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
      <mat-icon class="title-icon">refresh</mat-icon>
      Generate Viability Sheet
    </h2>
    <mat-dialog-content class="content">
      <p class="hint">
        Pick the source for the new Viability sheet. Live FWS is the
        default — sourcing from an approved FWS or a past Viability
        version is non-destructive (the chosen snapshot stays frozen).
      </p>

      <div class="picker-section">
        <div class="section-label">FWS versions</div>
        <app-version-picker
          [items]="fwsItems"
          [selectedId]="pickedKind === 'fws' ? selectedId : null"
          [loading]="loading"
          [emptyMessage]="'No approved FWS versions yet — Live FWS will be used.'"
          (selected)="onPick('fws', $event)"
          (preview)="onPreview($event, 'fws')">
        </app-version-picker>
      </div>

      <div class="picker-section" *ngIf="data.viabilityId">
        <div class="section-label">Past Viability versions</div>
        <app-version-picker
          [items]="viabilityItems"
          [selectedId]="pickedKind === 'viability' ? selectedId : null"
          [loading]="loading"
          [emptyMessage]="'No past Viability snapshots — Approve at least once to start the history.'"
          (selected)="onPick('viability', $event)"
          (preview)="onPreview($event, 'viability')">
        </app-version-picker>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="cancel()">Cancel</button>
      <button
        mat-raised-button
        color="primary"
        (click)="confirm()"
        [disabled]="loading">
        <mat-icon>refresh</mat-icon> Generate
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
      max-width: 600px;
      padding-top: 6px;
      /* Cap the dialog body so two source sections + long lists scroll
         inside the modal rather than pushing the action buttons off
         the viewport. mat-dialog-content already has overflow:auto by
         default; pinning a max-height makes the constraint kick in. */
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
      margin-bottom: 14px;
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
export class GenerateViabilityDialogComponent implements OnInit {
  /** Sentinel id meaning "no snapshot, use live FWS". Outside the
   *  range of any real auto-increment PK on the snapshot table — the
   *  dialog translates back to ``null`` on confirm. */
  static readonly LIVE_FWS_ID = -1;

  fwsItems: VersionItem[] = [];
  viabilityItems: VersionItem[] = [];

  /** Tracks which section the user picked from. Pairs with
   *  ``selectedId`` to identify the exact row. Defaults to ``fws`` +
   *  the Live FWS sentinel so the legacy default still works for
   *  users who confirm without picking. */
  pickedKind: PickedKind = 'fws';
  selectedId: number | null = GenerateViabilityDialogComponent.LIVE_FWS_ID;
  loading = true;

  constructor(
    private api: ApiService,
    private dialog: MatDialog,
    public dialogRef: MatDialogRef<
      GenerateViabilityDialogComponent,
      GenerateViabilityDialogResult
    >,
    @Inject(MAT_DIALOG_DATA) public data: GenerateViabilityDialogData,
  ) {}

  ngOnInit(): void {
    const fws$ = this.api.get<{ items: FwsSnapshotRow[] }>(
      `/quotations/${this.data.quotId}/cycles/${this.data.cycleId}/fws/approval-snapshots`,
    ).pipe(catchError(() => of<{ items: FwsSnapshotRow[] } | null>(null)));

    const viab$ = this.data.viabilityId
      ? this.api.get<{ items: ViabilitySnapshotRow[] }>(
          `/viability/${this.data.viabilityId}/approval-snapshots`,
        ).pipe(catchError(() => of<{ items: ViabilitySnapshotRow[] } | null>(null)))
      : of<{ items: ViabilitySnapshotRow[] } | null>(null);

    forkJoin({ fws: fws$, viab: viab$ }).subscribe(({ fws, viab }) => {
      // FWS section — always leads with the synthetic Live FWS row so
      // the default is obvious.
      this.fwsItems = [
        {
          id: GenerateViabilityDialogComponent.LIVE_FWS_ID,
          label: `C${this.data.cycleNo} — Live FWS`,
          sub: 'Current state (default)',
        },
        ...((fws?.items || []).map(s => ({
          id: s.snapshotId,
          label: s.label,
          isApproved: true,
          approvedAt: s.approvedAt,
          approvedByName: s.approvedByName ?? null,
          previewUrl: `/quotations/${this.data.quotId}/cycles/${this.data.cycleId}/fws/approval-snapshots/${s.snapshotId}`,
        }))),
      ];

      // Past Viability section (only present when the host passed a
      // viabilityId — i.e. when a head already exists).
      this.viabilityItems = (viab?.items || []).map(s => ({
        id: s.snapshotId,
        label: `V${s.versionNo}`,
        isApproved: true,
        approvedAt: s.approvedAt,
        approvedByName: s.approvedByName ?? null,
        previewUrl: `/viability/${this.data.viabilityId}/approval-snapshots/${s.snapshotId}`,
      }));

      this.loading = false;
    });
  }

  /** Coordinated selection across the two sections — picking in one
   *  clears the other. */
  onPick(kind: PickedKind, id: number): void {
    this.pickedKind = kind;
    this.selectedId = id;
  }

  onPreview(item: VersionItem, kind: PickedKind): void {
    if (!item.previewUrl) return;
    const subtitle = kind === 'fws' ? 'Final Working Sheet' : 'Viability Sheet';
    this.dialog.open(SnapshotViewerDialogComponent, {
      data: { url: item.previewUrl, title: `${item.label} — ${subtitle}` },
      width: '740px',
    });
  }

  confirm(): void {
    const id = this.selectedId;
    if (this.pickedKind === 'fws') {
      this.dialogRef.close({
        sourcedFromFWSSnapshotId:
          id === GenerateViabilityDialogComponent.LIVE_FWS_ID || id == null
            ? null
            : id,
        sourcedFromViabilitySnapshotId: null,
      });
    } else {
      this.dialogRef.close({
        sourcedFromFWSSnapshotId: null,
        sourcedFromViabilitySnapshotId: id,
      });
    }
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
