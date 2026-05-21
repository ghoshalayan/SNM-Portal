/**
 * Snapshot viewer dialog (Slice G of the soft-flow rollout).
 *
 * Generic "view-as-approved" surface. Takes any approval-snapshot
 * detail URL, fetches the body, and renders the frozen state in a
 * readable form. Used from the version-picker's preview button so a
 * reviewer can verify what a version contains before binding to it.
 *
 * The body shape varies across entity types (FWS snapshot is a flat
 * list of line rows; viability is sheet + lines; annexure is one
 * row). The viewer renders whatever it gets as a structured key-value
 * tree — generic enough to handle all three without each entity
 * needing its own dialog.
 */
import { CommonModule, KeyValuePipe } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApiService } from '../../../core/services/api.service';

export interface SnapshotViewerDialogData {
  /** Endpoint that returns the snapshot detail (with parsed body). */
  url: string;
  /** Human-readable header for the dialog, e.g. ``C1-V3 — Viability``. */
  title: string;
}

interface SnapshotDetail {
  snapshotId: number;
  versionNo: number;
  approvedAt?: string;
  approvedByName?: string;
  label?: string;
  snapshot: unknown;
}

@Component({
  selector: 'app-snapshot-viewer-dialog',
  standalone: true,
  imports: [
    CommonModule,
    KeyValuePipe,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">visibility</mat-icon>
      {{ data.title }}
    </h2>
    <mat-dialog-content class="content">
      @if (loading) {
        <div class="snap-loading">
          <mat-spinner diameter="32"></mat-spinner>
          <span>Loading snapshot…</span>
        </div>
      } @else if (error) {
        <div class="snap-error">
          <mat-icon>error_outline</mat-icon>
          <span>{{ error }}</span>
        </div>
      } @else if (detail) {
        <div class="snap-meta">
          @if (detail.label) {
            <span class="meta-chip"><strong>{{ detail.label }}</strong></span>
          }
          @if (detail.approvedAt) {
            <span class="meta-when">Approved {{ detail.approvedAt | date: 'dd MMM yyyy, HH:mm' }}</span>
          }
          @if (detail.approvedByName) {
            <span class="meta-who">by {{ detail.approvedByName }}</span>
          }
        </div>
        <div class="snap-body">
          <ng-container *ngTemplateOutlet="valueT; context: { $implicit: detail.snapshot, depth: 0 }"></ng-container>
        </div>
      }
    </mat-dialog-content>

    <ng-template #valueT let-value let-depth="depth">
      @if (value === null || value === undefined) {
        <span class="value null">(none)</span>
      } @else if (isArray(value)) {
        @if (value.length === 0) {
          <span class="value empty">(empty list)</span>
        } @else {
          <ol class="list">
            @for (item of value; track $index) {
              <li>
                <ng-container *ngTemplateOutlet="valueT; context: { $implicit: item, depth: depth + 1 }"></ng-container>
              </li>
            }
          </ol>
        }
      } @else if (isObject(value)) {
        <dl class="obj">
          @for (kv of value | keyvalue; track kv.key) {
            <dt>{{ kv.key }}</dt>
            <dd>
              <ng-container *ngTemplateOutlet="valueT; context: { $implicit: kv.value, depth: depth + 1 }"></ng-container>
            </dd>
          }
        </dl>
      } @else {
        <span class="value scalar">{{ value }}</span>
      }
    </ng-template>

    <mat-dialog-actions align="end">
      @if (detail) {
        <button mat-stroked-button (click)="downloadJson()">
          <mat-icon>download</mat-icon> Download JSON
        </button>
      }
      <button mat-raised-button color="primary" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon { vertical-align: middle; margin-right: 6px; color: var(--snm-accent); }
    .content {
      min-width: 540px;
      max-width: 740px;
      max-height: 64vh;
      overflow-y: auto;
      padding-top: 6px;
    }
    .snap-loading, .snap-error {
      display: flex; align-items: center; gap: 10px;
      padding: 24px;
      color: var(--snm-text-muted);
      font-size: 13px;
    }
    .snap-error mat-icon { color: var(--snm-error); }

    .snap-meta {
      display: flex; flex-wrap: wrap; gap: 12px;
      padding: 8px 12px;
      margin-bottom: 12px;
      background: var(--snm-bg-panel);
      border-radius: 6px;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .meta-chip strong { font-size: 13px; color: var(--snm-text-primary); }
    .meta-when { font-variant-numeric: tabular-nums; }
    .meta-who { font-style: italic; }

    .snap-body { font-size: 12px; }
    .obj { margin: 0; padding: 0; }
    .obj dt {
      font-weight: 600;
      color: var(--snm-text-secondary);
      margin-top: 4px;
    }
    .obj dd { margin: 0 0 4px 12px; }

    .list { margin: 0 0 0 16px; padding: 0; }
    .list li { margin: 2px 0; }

    .value.null { color: var(--snm-text-faint); font-style: italic; }
    .value.empty { color: var(--snm-text-faint); font-style: italic; }
    .value.scalar { color: var(--snm-text-primary); font-family: monospace; word-break: break-word; }
  `],
})
export class SnapshotViewerDialogComponent implements OnInit {
  detail: SnapshotDetail | null = null;
  loading = true;
  error: string | null = null;

  constructor(
    private api: ApiService,
    public dialogRef: MatDialogRef<SnapshotViewerDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: SnapshotViewerDialogData,
  ) {}

  ngOnInit(): void {
    this.api.get<SnapshotDetail>(this.data.url).subscribe({
      next: (res) => {
        this.detail = res;
        this.loading = false;
      },
      error: (e) => {
        this.error = e?.error?.detail || 'Failed to load snapshot.';
        this.loading = false;
      },
    });
  }

  isArray(v: unknown): boolean {
    return Array.isArray(v);
  }
  isObject(v: unknown): boolean {
    return typeof v === 'object' && v !== null && !Array.isArray(v);
  }

  /** Save the snapshot's frozen body as a JSON file. Useful for
   *  auditors who want an offline copy. */
  downloadJson(): void {
    if (!this.detail) return;
    const blob = new Blob([JSON.stringify(this.detail.snapshot, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `snapshot-${this.data.title.replace(/[^\w-]+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  close(): void {
    this.dialogRef.close();
  }
}
