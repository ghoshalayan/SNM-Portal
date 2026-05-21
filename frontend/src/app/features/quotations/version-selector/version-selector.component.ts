import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

export type LifecycleStageSlug = 'purchase-order' | 'viability' | 'annexure';

interface StageVersion {
  entityId: number;
  versionNo: number;
  isHead: boolean;
  status: string | null;
  parentVersionId: number | null;
  createdon: string | null;
  createdby: number | null;
  summary: string | null;
}

/**
 * Time-travel selector for the four lifecycle stage cards.
 *
 * Renders as the same accent-tinted version pill the cards used in
 * Phase 1 (``v3``), but the pill is now a button that opens a
 * ``mat-menu`` listing every version of the stage on this quotation.
 * Each non-head version gets a "Restore" button that clones the past
 * row forward as a new head; gated by the per-stage Unlock-and-Edit
 * permission.
 *
 * Inputs: ``quotId`` + ``stage`` (URL slug) + ``headVersion`` for the
 * pill label + ``canRestore`` for the action gate.
 *
 * Emits ``restored`` after a successful restore so the parent can
 * reload its underlying entity (the head row has changed).
 */
@Component({
  selector: 'app-version-selector',
  standalone: true,
  imports: [
    CommonModule, MatButtonModule, MatIconModule, MatMenuModule,
    MatTooltipModule, MatProgressSpinnerModule, MatDialogModule,
  ],
  template: `
    <button type="button" class="stage-version-pill ver-btn"
      [matMenuTriggerFor]="versionMenu"
      (menuOpened)="loadVersions()"
      [matTooltip]="tooltipText()">
      <mat-icon class="ver-ico">history</mat-icon>
      v{{ headVersion || 1 }}
      <mat-icon class="ver-caret">expand_more</mat-icon>
    </button>

    <mat-menu #versionMenu="matMenu" class="ver-menu" xPosition="before">
      <div class="ver-menu-head" (click)="$event.stopPropagation()">
        <mat-icon>history</mat-icon>
        <span>{{ stageLabel() }} versions</span>
      </div>

      @if (loading) {
        <div class="ver-menu-loading"><mat-spinner diameter="24"></mat-spinner></div>
      } @else if (!versions.length) {
        <div class="ver-menu-empty">No versions yet.</div>
      } @else {
        <div class="ver-list">
          @for (v of versions; track v.entityId) {
            <div class="ver-row" [class.is-head]="v.isHead"
                 [class.is-clickable]="true"
                 (click)="onRowClick(v); $event.stopPropagation()"
                 [matTooltip]="v.isHead
                   ? 'Already the head — already displayed.'
                   : 'Click to load this version (read-only).'">
              <div class="ver-row-main">
                <div class="ver-row-title">
                  <span class="ver-no">v{{ v.versionNo }}</span>
                  @if (v.isHead) { <span class="ver-head-chip">head</span> }
                  @if (v.status) {
                    <span class="ver-status">{{ v.status }}</span>
                  }
                </div>
                <div class="ver-row-meta">
                  {{ v.summary || '—' }}
                  @if (v.createdon) {
                    <span class="ver-dot">·</span>
                    {{ v.createdon | date:'dd-MM-yyyy HH:mm' }}
                  }
                </div>
              </div>
              <button mat-stroked-button color="warn"
                *ngIf="!v.isHead && canRestore"
                class="ver-restore-btn"
                (click)="confirmRestore(v); $event.stopPropagation()"
                [disabled]="restoring === v.entityId"
                matTooltip="Restore this version as the new head (audited)">
                @if (restoring === v.entityId) {
                  <mat-spinner diameter="14" class="inline-spinner"></mat-spinner>
                } @else {
                  <mat-icon>restore</mat-icon>
                }
                Restore
              </button>
            </div>
          }
        </div>
        <div class="ver-menu-foot" *ngIf="!canRestore">
          <mat-icon>info_outline</mat-icon>
          Restore is gated by the Unlock-and-Edit permission for this stage.
        </div>
      }
    </mat-menu>
  `,
  styles: [`
    .ver-btn {
      cursor: pointer;
      border: 1px solid rgba(58, 107, 181, 0.22);
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 6px 2px 8px;
      transition: background 0.15s ease;
    }
    .ver-btn:hover { background: rgba(58, 107, 181, 0.16); }
    .ver-ico { font-size: 12px; width: 12px; height: 12px; opacity: 0.85; }
    .ver-caret { font-size: 14px; width: 14px; height: 14px; margin-left: 2px; opacity: 0.7; }

    /* The mat-menu's panel is rendered into an overlay portal — the
       :host-scoped styles below have to be ::ng-deep'd via the panel
       class. Keeping them in the component for locality. */
    ::ng-deep .ver-menu .mat-mdc-menu-content { padding: 0 !important; min-width: 320px; }
    .ver-menu-head {
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
    .ver-menu-head mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--snm-accent-dark); }

    .ver-menu-loading, .ver-menu-empty {
      display: flex; justify-content: center; align-items: center;
      padding: 28px 16px; color: var(--snm-text-muted);
      font-size: 13px;
    }

    .ver-list { max-height: 360px; overflow-y: auto; }
    .ver-row {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 14px;
      border-bottom: 1px solid rgba(0,0,0,0.05);
    }
    .ver-row.is-head { background: rgba(58, 107, 181, 0.05); }
    .ver-row.is-clickable:not(.is-head) { cursor: pointer; }
    .ver-row.is-clickable:not(.is-head):hover {
      background: rgba(58, 107, 181, 0.07);
    }
    .ver-row:last-child { border-bottom: 0; }
    .ver-row-main { flex: 1; min-width: 0; }
    .ver-row-title {
      display: flex; align-items: center; gap: 8px;
      font-weight: 600;
      font-size: 13px;
    }
    .ver-no { color: var(--snm-accent-dark); }
    .ver-head-chip {
      padding: 2px 8px;
      border-radius: 10px;
      background: rgba(46,125,50,0.15);
      color: #4caf50;
      border: 1px solid rgba(46,125,50,0.3);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }
    .ver-status {
      font-size: 11px;
      color: var(--snm-text-muted);
      font-weight: 400;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .ver-row-meta {
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }
    .ver-dot { margin: 0 5px; opacity: 0.5; }
    .ver-restore-btn {
      flex-shrink: 0;
      min-width: 96px;
      font-size: 12px !important;
      line-height: 1.2 !important;
      padding: 0 10px !important;
    }
    .ver-restore-btn mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .inline-spinner { display: inline-block; margin-right: 6px; }

    .ver-menu-foot {
      display: flex; align-items: center; gap: 6px;
      padding: 10px 14px;
      font-size: 11px;
      color: var(--snm-text-faint);
      background: rgba(0,0,0,0.02);
      border-top: 1px solid rgba(0,0,0,0.05);
    }
    .ver-menu-foot mat-icon { font-size: 14px; width: 14px; height: 14px; }
  `],
})
export class VersionSelectorComponent {
  @Input({ required: true }) quotId!: number;
  @Input({ required: true }) stage!: LifecycleStageSlug;
  /** Display label on the pill. The component doesn't independently
   *  derive this — parent passes the head's versionNo so the pill
   *  matches what the rest of the card shows. */
  @Input() headVersion = 1;
  /** Per-stage Unlock-and-Edit permission gates the Restore action. */
  @Input() canRestore = false;

  /** Emitted after a successful restore. Parent should reload the
   *  underlying entity since the head row has changed. */
  @Output() restored = new EventEmitter<void>();

  /** Emitted when the user clicks a non-head version row. Parent
   *  decides what to do — typically open the row in a read-only
   *  preview pane (the deeper per-stage time-travel UX) or pre-
   *  select the version in another picker (e.g. annexure's source-
   *  viability dropdown). Head clicks are no-ops since the page is
   *  already displaying the head. */
  @Output() versionSelected = new EventEmitter<number>();

  versions: StageVersion[] = [];
  loading = false;
  /** entityId of the row currently being restored (for the inline
   *  spinner in the menu). null when idle. */
  restoring: number | null = null;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
  ) {}

  stageLabel(): string {
    switch (this.stage) {
      case 'purchase-order': return 'Purchase Order';
      case 'viability': return 'Viability';
      case 'annexure': return 'Annexure';
    }
  }

  tooltipText(): string {
    return `View ${this.stageLabel()} version history`;
  }

  loadVersions(): void {
    this.loading = true;
    this.api.get<StageVersion[]>(
      `/quotations/${this.quotId}/${this.stage}/versions`,
    ).subscribe({
      next: (rs) => {
        this.versions = rs || [];
        this.loading = false;
      },
      error: () => {
        this.versions = [];
        this.loading = false;
      },
    });
  }

  /** Fired when the user clicks anywhere on a version row (not the
   *  Restore button — that has its own handler with stopPropagation).
   *  Head clicks are no-ops; non-head clicks emit ``versionSelected``
   *  so the parent can react (load preview, pre-select a picker, etc.). */
  onRowClick(version: StageVersion): void {
    if (version.isHead) return;
    this.versionSelected.emit(version.entityId);
  }

  confirmRestore(version: StageVersion): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: `Restore ${this.stageLabel()} v${version.versionNo}?`,
        message:
          `This archives the current head and creates a new active version ` +
          `(v${this.maxVersionNo() + 1}) cloned from v${version.versionNo}. ` +
          `The new version starts as Draft and goes through normal approval. ` +
          `The action is logged in the audit trail.`,
        confirmText: 'Restore',
        confirmColor: 'warn',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.runRestore(version);
    });
  }

  private maxVersionNo(): number {
    return this.versions.reduce((m, v) => (v.versionNo > m ? v.versionNo : m), 0);
  }

  private runRestore(version: StageVersion): void {
    this.restoring = version.entityId;
    this.api.post<any>(
      `/quotations/${this.quotId}/${this.stage}/versions/${version.entityId}/restore`,
      {},
    ).subscribe({
      next: () => {
        this.restoring = null;
        this.notify.success(`${this.stageLabel()} restored as new head.`);
        this.restored.emit();
      },
      error: (err) => {
        this.restoring = null;
        this.notify.error(err?.error?.detail || 'Restore failed.');
      },
    });
  }
}
