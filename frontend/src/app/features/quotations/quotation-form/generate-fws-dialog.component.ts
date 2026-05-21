/**
 * Re-generate FWS dialog — soft-flow Phase B follow-up.
 *
 * Lets the user pick the source for a fresh Final Working Sheet on
 * the current cycle. Three sources in one picker (sectioned), with
 * exactly one selected at a time:
 *
 *   * **Past FWS versions** — every approved snapshot in this cycle's
 *     chain. Same data the inline version chip exposes, but in dialog
 *     form so the user can preview metadata before committing.
 *   * **Quotation lines (fresh)** — re-clone from the quotation's
 *     ``QuotDetails``. Useful when the upstream quote was revised and
 *     the user wants the FWS to follow.
 *   * **Parent cycle** — pull forward the live FWS from a previous
 *     call-off. Only relevant on Cycle 2+; suppressed otherwise.
 *
 * On confirm the dialog returns the picked source as a tagged result
 * the host forwards to ``POST /cycles/{id}/fws/regenerate``. The
 * backend replaces the cycle's live working-sheet rows; the user then
 * edits and clicks Approve as usual.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialog,
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

export interface GenerateFwsDialogData {
  quotId: number;
  cycleId: number;
  cycleNo: number;
  /** Parent cycle id, if this is Cycle 2+. When unset, the parent-
   *  cycle section is hidden entirely. */
  parentCycleId?: number | null;
  /** Display label for the parent cycle (e.g. "Cycle 1"). Used in the
   *  picker row's secondary text. */
  parentCycleLabel?: string | null;
}

export interface GenerateFwsDialogResult {
  /** Exactly one of these is set on confirm. */
  sourcedFromSnapshotId: number | null;
  fromQuotation: boolean;
  parentCycleId: number | null;
}

interface FwsSnapshotRow {
  snapshotId: number;
  label: string;
  versionNo: number;
  approvedAt: string;
  approvedByName?: string | null;
}

/** Synthetic ids for the non-snapshot picker rows. Chosen well below
 *  any plausible auto-increment PK on the snapshot table. */
const QUOTATION_ID = -100;
const PARENT_CYCLE_ID = -200;

@Component({
  selector: 'app-generate-fws-dialog',
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
      Re-generate Final Working Sheet
    </h2>
    <mat-dialog-content class="content">
      <p class="hint">
        Pick a source for the new FWS draft. The cycle's current
        line items will be replaced with rows from the picked
        source — you'll then edit and Approve as usual.
      </p>

      <div class="picker-section">
        <div class="section-label">Past FWS versions</div>
        <app-version-picker
          [items]="snapshotItems"
          [selectedId]="pickedKind === 'snapshot' ? selectedId : null"
          [loading]="loading"
          [emptyMessage]="'No approved FWS versions yet in this cycle.'"
          (selected)="onPick('snapshot', $event)"
          (preview)="onPreview($event, 'snapshot')">
        </app-version-picker>
      </div>

      <div class="picker-section">
        <div class="section-label">Quotation lines (fresh)</div>
        <app-version-picker
          [items]="quotationItems"
          [selectedId]="pickedKind === 'quotation' ? selectedId : null"
          [loading]="false"
          [emptyMessage]="''"
          (selected)="onPick('quotation', $event)">
        </app-version-picker>
      </div>

      <div class="picker-section" *ngIf="data.parentCycleId">
        <div class="section-label">Parent cycle</div>
        <app-version-picker
          [items]="parentCycleItems"
          [selectedId]="pickedKind === 'parentCycle' ? selectedId : null"
          [loading]="false"
          [emptyMessage]="''"
          (selected)="onPick('parentCycle', $event)">
        </app-version-picker>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="cancel()">Cancel</button>
      <button
        mat-raised-button
        color="primary"
        (click)="confirm()"
        [disabled]="loading || pickedKind == null">
        <mat-icon>refresh</mat-icon> Re-generate
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
export class GenerateFwsDialogComponent implements OnInit {
  snapshotItems: VersionItem[] = [];
  /** Stable synthetic rows for the non-snapshot sections. */
  quotationItems: VersionItem[] = [
    {
      id: QUOTATION_ID,
      label: 'Re-clone from Quotation lines',
      sub: 'Pulls the quotation\'s current line items as the new FWS draft',
    },
  ];
  parentCycleItems: VersionItem[] = [];

  pickedKind: 'snapshot' | 'quotation' | 'parentCycle' | null = null;
  selectedId: number | null = null;
  loading = true;

  constructor(
    private api: ApiService,
    private dialog: MatDialog,
    public dialogRef: MatDialogRef<
      GenerateFwsDialogComponent,
      GenerateFwsDialogResult
    >,
    @Inject(MAT_DIALOG_DATA) public data: GenerateFwsDialogData,
  ) {}

  ngOnInit(): void {
    if (this.data.parentCycleId) {
      this.parentCycleItems = [
        {
          id: PARENT_CYCLE_ID,
          label: this.data.parentCycleLabel || 'Parent cycle — Live FWS',
          sub: 'Clones forward from the parent cycle\'s working sheet',
        },
      ];
    }

    const fws$ = this.api.get<{ items: FwsSnapshotRow[] }>(
      `/quotations/${this.data.quotId}/cycles/${this.data.cycleId}/fws/approval-snapshots`,
    ).pipe(catchError(() => of<{ items: FwsSnapshotRow[] } | null>(null)));

    forkJoin({ fws: fws$ }).subscribe(({ fws }) => {
      this.snapshotItems = (fws?.items || []).map((s) => ({
        id: s.snapshotId,
        label: s.label,
        isApproved: true,
        approvedAt: s.approvedAt,
        approvedByName: s.approvedByName ?? null,
        previewUrl: `/quotations/${this.data.quotId}/cycles/${this.data.cycleId}/fws/approval-snapshots/${s.snapshotId}`,
      }));
      this.loading = false;
    });
  }

  /** Coordinated selection across the sections — picking in one
   *  section clears the selection in the others. */
  onPick(kind: 'snapshot' | 'quotation' | 'parentCycle', id: number): void {
    this.pickedKind = kind;
    this.selectedId = id;
  }

  onPreview(item: VersionItem, kind: 'snapshot'): void {
    if (!item.previewUrl) return;
    this.dialog.open(SnapshotViewerDialogComponent, {
      data: { url: item.previewUrl, title: `${item.label} — Final Working Sheet` },
      width: '740px',
    });
  }

  confirm(): void {
    if (this.pickedKind == null) return;
    if (this.pickedKind === 'snapshot') {
      this.dialogRef.close({
        sourcedFromSnapshotId: this.selectedId,
        fromQuotation: false,
        parentCycleId: null,
      });
    } else if (this.pickedKind === 'quotation') {
      this.dialogRef.close({
        sourcedFromSnapshotId: null,
        fromQuotation: true,
        parentCycleId: null,
      });
    } else {
      this.dialogRef.close({
        sourcedFromSnapshotId: null,
        fromQuotation: false,
        parentCycleId: this.data.parentCycleId ?? null,
      });
    }
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
