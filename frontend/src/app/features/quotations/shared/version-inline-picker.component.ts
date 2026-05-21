/**
 * Inline version picker — chip + mat-menu, modelled on the LOI/PO
 * picker so the UX for switching versions matches the UX for
 * switching POs.
 *
 * Mounted in each stage's StageShell header. The trigger is a compact
 * chip showing the currently-loaded version label (e.g. "C1-V2") with
 * a caret; clicking opens a menu listing every snapshot for that
 * stage's current cycle. Picking a different row emits ``picked``,
 * the host opens the Save-as-Draft / Discard switch dialog.
 *
 * Stage-agnostic: takes a flat list of ``VersionInlineItem`` rows and
 * a ``currentId``. The host maps its FWS / Viability / Annexure
 * snapshot rows into this shape before passing in.
 */
import { CommonModule, DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

export interface VersionInlineItem {
  /** Opaque id passed back via ``picked``. */
  id: number;
  /** Display label, e.g. ``"C1-V2"``. */
  label: string;
  /** ISO datetime; rendered as the dated sub-line. */
  approvedAt?: string | null;
  /** Optional approver name; rendered next to the date. */
  approvedByName?: string | null;
  /** Render an "approved" tick badge on the row. Defaults to true
   *  since every snapshot is an approval point by definition. */
  isApproved?: boolean;
}

@Component({
  selector: 'app-version-inline-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatIconModule, MatMenuModule,
    MatProgressSpinnerModule, MatTooltipModule,
  ],
  template: `
    <button type="button" class="vip-btn"
            [matMenuTriggerFor]="vipMenu"
            [disabled]="busy || items.length === 0"
            [matTooltip]="tooltipText()">
      <mat-icon class="vip-ico">history</mat-icon>
      <span class="vip-label">{{ activeLabel() }}</span>
      <mat-icon class="vip-caret">expand_more</mat-icon>
    </button>

    <mat-menu #vipMenu="matMenu" class="vip-menu" xPosition="before">
      <div class="vip-menu-head" (click)="$event.stopPropagation()">
        <mat-icon>history</mat-icon>
        <span>{{ headLabel || 'Approved versions' }}</span>
      </div>

      <div *ngIf="busy" class="vip-menu-loading">
        <mat-spinner diameter="22"></mat-spinner>
      </div>

      <div *ngIf="!busy && items.length === 0" class="vip-menu-empty">
        No approved versions yet — approve at least once to start the history.
      </div>

      <div *ngIf="!busy && items.length > 0" class="vip-list">
        <button mat-menu-item *ngFor="let v of items"
                [class.is-active]="v.id === currentId"
                (click)="onRowClick(v)">
          <div class="vip-row">
            <span class="vip-kind">V</span>
            <div class="vip-row-main">
              <div class="vip-row-title">
                <span class="vip-ver">{{ v.label }}</span>
                <span class="vip-status">{{ v.isApproved !== false ? 'Approved' : 'Draft' }}</span>
                <mat-icon *ngIf="v.id === currentId"
                          class="vip-active-tick"
                          matTooltip="Currently shown in the editor">check_circle</mat-icon>
              </div>
              <div class="vip-row-meta">
                <span *ngIf="v.approvedAt">{{ v.approvedAt | date:'dd-MMM-yyyy' }}</span>
                <span *ngIf="v.approvedByName"> · by {{ v.approvedByName }}</span>
                <span *ngIf="!v.approvedAt && !v.approvedByName">no metadata</span>
              </div>
            </div>
          </div>
        </button>
      </div>
    </mat-menu>
  `,
  styles: [`
    .vip-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 10px 4px 8px;
      border: 1px solid rgba(58, 107, 181, 0.22);
      border-radius: 14px;
      background: var(--snm-accent-shadow, rgba(25,118,210,0.10));
      color: var(--snm-accent, #1976d2);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      transition: background 0.15s ease;
    }
    .vip-btn:hover:not(:disabled) { background: rgba(58, 107, 181, 0.18); }
    .vip-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .vip-ico { font-size: 14px; width: 14px; height: 14px; }
    .vip-caret { font-size: 16px; width: 16px; height: 16px; opacity: 0.7; }
    .vip-label { line-height: 1; }

    ::ng-deep .vip-menu .mat-mdc-menu-content { padding: 0 !important; min-width: 320px; }
    .vip-menu-head {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 14px;
      font-size: 13px; font-weight: 600;
      color: var(--snm-text-primary);
      background: linear-gradient(
        90deg,
        rgba(58, 107, 181, 0.08),
        rgba(58, 107, 181, 0.02)
      );
      border-bottom: 1px solid rgba(0,0,0,0.08);
    }
    .vip-menu-head mat-icon {
      font-size: 18px; width: 18px; height: 18px;
      color: var(--snm-accent-dark);
    }
    .vip-menu-loading, .vip-menu-empty {
      display: flex; justify-content: center; align-items: center;
      padding: 24px 16px;
      color: var(--snm-text-muted);
      font-size: 13px;
      text-align: center;
    }
    .vip-list { max-height: 360px; overflow-y: auto; }
    .vip-row {
      display: flex; align-items: flex-start; gap: 10px;
      padding: 2px 0;
    }
    .vip-kind {
      padding: 2px 8px; border-radius: 10px;
      background: rgba(25,118,210,.12); color: #1976d2;
      font-size: 10px; font-weight: 700;
      letter-spacing: 0.4px;
      margin-top: 2px;
      flex-shrink: 0;
    }
    .vip-row-main { flex: 1; min-width: 0; }
    .vip-row-title {
      display: flex; align-items: center; gap: 6px;
      font-weight: 600; font-size: 13px;
      color: var(--snm-text-primary);
    }
    .vip-ver { line-height: 1.1; }
    .vip-status {
      font-size: 10px; text-transform: uppercase;
      color: var(--snm-text-muted);
      font-weight: 600;
      letter-spacing: 0.3px;
    }
    .vip-active-tick {
      font-size: 14px; width: 14px; height: 14px;
      color: #2e7d32;
    }
    .vip-row-meta {
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }
    button[mat-menu-item].is-active {
      background: rgba(46,125,50,0.06);
    }
  `],
})
export class VersionInlinePickerComponent {
  /** Snapshot rows, newest first. Empty array hides the chip. */
  @Input() items: VersionInlineItem[] = [];

  /** Id of the version currently loaded into the editor. Highlighted
   *  in the menu with a green tick. */
  @Input() currentId: number | null = null;

  /** Disable the picker while a switch is in flight. */
  @Input() busy = false;

  /** Optional header text for the menu, e.g. "Final Working Sheet
   *  versions" / "Viability versions". Falls back to a generic label
   *  when unset. */
  @Input() headLabel: string | null = null;

  /** Fires when the user picks a row from the menu. Host opens the
   *  Save-as-Draft / Discard switch dialog. We do NOT no-op when the
   *  picked row matches ``currentId`` — the host may still want to
   *  flash a "you're already on this" toast. */
  @Output() picked = new EventEmitter<number>();

  activeLabel(): string {
    if (this.busy) return 'Loading…';
    if (this.items.length === 0) return 'No versions yet';
    const active = this.items.find(v => v.id === this.currentId);
    return active?.label ?? this.items[0].label;
  }

  tooltipText(): string {
    if (this.items.length === 0) {
      return 'No versions to switch to yet';
    }
    return 'Switch to a different version of this stage';
  }

  onRowClick(item: VersionInlineItem): void {
    this.picked.emit(item.id);
  }
}
