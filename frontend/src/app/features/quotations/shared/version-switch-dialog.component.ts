/**
 * Version-switch dialog (soft-flow Slice H).
 *
 * Lets the user pick an older snapshot of FWS, Viability, or Annexure
 * and load it into the live editor. Reuses the shared VersionPicker
 * for the list rendering. Three terminal actions:
 *
 *   * **Save as Draft & Switch** — first creates a fresh approval
 *     snapshot of the current live state (so the in-flight edits
 *     don't get lost), then loads the picked version. The freshly
 *     saved version is visible in the dropdown next time.
 *   * **Discard & Switch** — loads the picked version directly. Any
 *     unsaved live edits are overwritten.
 *   * **Cancel** — closes the dialog with no change.
 *
 * Stage-agnostic: the host supplies the picker items + the current
 * loaded id; the dialog returns `{ pickedId, action }`. The host
 * performs the actual approve-then-load (or load-only) calls via
 * the cycle service.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  VersionItem,
  VersionPickerComponent,
} from '../../../shared/components/version-picker/version-picker.component';

export type VersionSwitchAction = 'saveAndSwitch' | 'discardAndSwitch';

export interface VersionSwitchDialogData {
  /** Dialog title, e.g. "Switch Final Working Sheet Version". */
  title: string;
  /** Optional one-line intro under the title. */
  hint?: string;
  /** Snapshot rows for the picker. */
  items: VersionItem[];
  /** The id currently loaded into the editor (highlighted as
   *  "current" — picking it is a no-op). May be ``null`` when the
   *  editor's state was never loaded from a specific snapshot
   *  (e.g. fresh draft). */
  currentId: number | null;
  /** Whether the host supports the "Save as Draft" path. Disabled
   *  for stages that can't auto-approve (e.g. when the stage has
   *  no approval action available to this user). Defaults to true. */
  allowSaveAsDraft?: boolean;
  /** Optional: pre-select a specific snapshot id when the dialog
   *  opens. Used when the inline version picker already collected the
   *  user's choice and the dialog only needs to confirm the
   *  Save-as-Draft / Discard decision. Falls back to ``currentId``. */
  preSelectedId?: number | null;
}

export interface VersionSwitchDialogResult {
  pickedId: number;
  action: VersionSwitchAction;
}

@Component({
  selector: 'app-version-switch-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    VersionPickerComponent,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">history</mat-icon>
      {{ data.title }}
    </h2>
    <mat-dialog-content class="content">
      <p class="hint" *ngIf="data.hint">{{ data.hint }}</p>
      <p class="hint" *ngIf="!data.hint">
        Pick a past version to load into the editor. The next Approve
        will create a new version on top — past versions are never
        overwritten.
      </p>

      <app-version-picker
        [items]="data.items"
        [selectedId]="pickedId ?? data.currentId"
        [emptyMessage]="'No approved versions yet — Approve at least once to start building the history.'"
        (selected)="onSelect($event)">
      </app-version-picker>

      <div class="current-line" *ngIf="data.currentId != null">
        <mat-icon class="current-icon">check_circle</mat-icon>
        <span>
          Editor currently shows
          <strong>{{ currentLabel || ('version #' + data.currentId) }}</strong>.
        </span>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end" class="actions">
      <button mat-button (click)="cancel()">Cancel</button>
      <button mat-stroked-button color="warn"
              (click)="confirm('discardAndSwitch')"
              [disabled]="!canConfirm">
        <mat-icon>delete_sweep</mat-icon>
        Discard &amp; Switch
      </button>
      <button mat-raised-button color="primary"
              *ngIf="allowSaveAsDraft"
              (click)="confirm('saveAndSwitch')"
              [disabled]="!canConfirm">
        <mat-icon>save</mat-icon>
        Save as Draft &amp; Switch
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
      min-width: 500px;
      max-width: 620px;
      padding-top: 4px;
    }
    .hint {
      font-size: 13px;
      color: var(--snm-text-muted);
      margin: 0 0 12px;
      line-height: 1.5;
    }
    .current-line {
      display: flex; align-items: center; gap: 8px;
      margin-top: 12px;
      padding: 8px 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      font-size: 13px;
      color: var(--snm-text-secondary);
    }
    .current-line .current-icon {
      color: var(--snm-accent);
      font-size: 18px; width: 18px; height: 18px;
    }
    .actions button mat-icon { margin-right: 4px; }
  `],
})
export class VersionSwitchDialogComponent {
  /** Snapshot the user has selected in the picker (may differ from
   *  ``data.currentId`` — that's the whole point of switching). */
  pickedId: number | null = null;
  allowSaveAsDraft: boolean;

  constructor(
    public dialogRef: MatDialogRef<
      VersionSwitchDialogComponent,
      VersionSwitchDialogResult
    >,
    @Inject(MAT_DIALOG_DATA) public data: VersionSwitchDialogData,
  ) {
    this.pickedId = data.preSelectedId ?? data.currentId;
    this.allowSaveAsDraft = data.allowSaveAsDraft !== false;
  }

  /** Resolve the picker label for the currently-loaded version so the
   *  "Editor currently shows …" badge reads naturally. */
  get currentLabel(): string | null {
    if (this.data.currentId == null) return null;
    const item = this.data.items.find(i => i.id === this.data.currentId);
    return item?.label ?? null;
  }

  /** Confirm buttons disabled when nothing is picked, OR the user
   *  picked the currently-loaded version (switching to yourself is a
   *  no-op — better to gray it out than silently dismiss). */
  get canConfirm(): boolean {
    if (this.pickedId == null) return false;
    if (this.pickedId === this.data.currentId) return false;
    return true;
  }

  onSelect(id: number): void {
    this.pickedId = id;
  }

  confirm(action: VersionSwitchAction): void {
    if (!this.canConfirm || this.pickedId == null) return;
    this.dialogRef.close({ pickedId: this.pickedId, action });
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
