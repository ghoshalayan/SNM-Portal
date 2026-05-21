/**
 * Reusable version picker for the soft-flow approval-snapshot model.
 *
 * Shows a vertical list of version items (FWS, Viability, or Annexure
 * snapshots) with their ``C{cycleNo}-V{ver}`` labels, approval badges,
 * and approver/date metadata. The host component owns the data
 * loading; this component just renders and emits the selected id.
 *
 * Designed for use inside the Generate-Viability and Generate-Annexure
 * dialogs (Slice E of the soft-flow rollout) but generic enough to use
 * anywhere a version is picked from a finite list.
 */
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatRadioModule } from '@angular/material/radio';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

/** One row in the picker. The host loads + maps API rows into this
 *  shape before passing in. ``id`` is whatever opaque identifier the
 *  host wants to receive back via the (selected) emission. */
export interface VersionItem {
  id: number;
  /** Display label, e.g. ``"C1-V3"``. */
  label: string;
  /** True if this version was an approval point (renders a ✓ badge). */
  isApproved?: boolean;
  /** ISO datetime — formatted for display. */
  approvedAt?: string | null;
  /** Optional approver name; shown muted next to the timestamp. */
  approvedByName?: string | null;
  /** Optional sub-label rendered under the main label (e.g. for POs:
   *  the PO number; for viabilities: extra metadata). */
  sub?: string | null;
  /** Optional snapshot-detail URL. When set, the picker shows a
   *  "Preview" eye icon on the row; clicking it emits ``preview`` so
   *  the host can open the snapshot-viewer dialog. */
  previewUrl?: string | null;
}

@Component({
  selector: 'app-version-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatRadioModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  template: `
    <div class="vp-wrap">
      @if (loading) {
        <div class="vp-loading">
          <mat-spinner diameter="20"></mat-spinner>
          <span>Loading versions…</span>
        </div>
      } @else if (!items || items.length === 0) {
        <div class="vp-empty">
          <mat-icon>info</mat-icon>
          <span>{{ emptyMessage }}</span>
        </div>
      } @else {
        <mat-radio-group
          class="vp-list"
          [ngModel]="selectedId"
          (ngModelChange)="onSelectionChange($event)">
          @for (item of items; track item.id) {
            <div class="vp-item">
              <mat-radio-button [value]="item.id" class="vp-radio">
                <div class="vp-row">
                  <div class="vp-label">
                    <strong>{{ item.label }}</strong>
                    @if (item.isApproved) {
                      <mat-icon class="vp-tick" matTooltip="Approved version">verified</mat-icon>
                    }
                  </div>
                  <div class="vp-meta">
                    @if (item.approvedAt) {
                      <span class="vp-when">{{ item.approvedAt | date: 'dd MMM yyyy, HH:mm' }}</span>
                    }
                    @if (item.approvedByName) {
                      <span class="vp-who">by {{ item.approvedByName }}</span>
                    }
                  </div>
                  @if (item.sub) {
                    <div class="vp-sub">{{ item.sub }}</div>
                  }
                </div>
              </mat-radio-button>
              @if (item.previewUrl) {
                <button mat-icon-button class="vp-preview"
                  (click)="onPreview($event, item)"
                  matTooltip="Preview the frozen content of this version">
                  <mat-icon>visibility</mat-icon>
                </button>
              }
            </div>
          }
        </mat-radio-group>
      }
    </div>
  `,
  styles: [`
    .vp-wrap {
      display: flex; flex-direction: column;
      max-height: 320px; overflow-y: auto;
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      padding: 4px;
    }
    .vp-loading, .vp-empty {
      display: flex; align-items: center; gap: 10px;
      padding: 18px 14px;
      color: var(--snm-text-muted);
      font-size: 13px;
    }
    .vp-empty mat-icon { color: var(--snm-text-muted); }

    .vp-list {
      display: flex; flex-direction: column;
    }
    .vp-item {
      display: flex; align-items: flex-start; gap: 6px;
      padding: 8px 10px;
      border-radius: 4px;
    }
    .vp-item:hover { background: var(--snm-glass-bg); }
    .vp-radio { flex: 1; min-width: 0; }
    .vp-preview {
      flex: 0 0 auto;
      margin-top: -4px;
      color: var(--snm-text-secondary);
    }
    .vp-preview:hover { color: var(--snm-accent); }
    /* Material radio's content wrapper — let the row content stretch. */
    .vp-item ::ng-deep .mdc-form-field,
    .vp-item ::ng-deep .mdc-radio { align-items: flex-start; }
    .vp-item ::ng-deep label { width: 100%; }

    .vp-row { display: flex; flex-direction: column; gap: 2px; padding-top: 1px; }
    .vp-label {
      display: flex; align-items: center; gap: 6px;
      font-size: 14px;
    }
    .vp-tick {
      font-size: 16px; width: 16px; height: 16px;
      color: var(--snm-accent);
    }
    .vp-meta {
      display: flex; flex-wrap: wrap; gap: 8px;
      font-size: 12px;
      color: var(--snm-text-muted);
    }
    .vp-when { font-variant-numeric: tabular-nums; }
    .vp-who { font-style: italic; }
    .vp-sub {
      font-size: 12px;
      color: var(--snm-text-faint);
    }
  `],
})
export class VersionPickerComponent {
  /** The version rows to render. Empty array = "no versions available". */
  @Input() items: VersionItem[] = [];
  /** Current selection (echoes back via two-way binding through (selected)). */
  @Input() selectedId: number | null = null;
  /** Show a spinner instead of the list. */
  @Input() loading = false;
  /** Custom empty-state message. */
  @Input() emptyMessage = 'No versions available yet.';

  /** Emits the newly-selected id. */
  @Output() selected = new EventEmitter<number>();
  /** Emits when the user clicks the eye icon on a row that has a
   *  ``previewUrl``. Host opens the snapshot-viewer dialog with the
   *  url + a sensible title. */
  @Output() preview = new EventEmitter<VersionItem>();

  onSelectionChange(id: number): void {
    this.selectedId = id;
    this.selected.emit(id);
  }

  onPreview(ev: Event, item: VersionItem): void {
    // Don't let the click bubble into the radio (otherwise opening
    // the preview would also change the selection — confusing).
    ev.stopPropagation();
    ev.preventDefault();
    this.preview.emit(item);
  }
}
