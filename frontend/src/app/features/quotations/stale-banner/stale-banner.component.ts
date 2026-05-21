import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

/**
 * Stale-source banner for the Phase 3 lifecycle workspace.
 *
 * Renders inline at the top of a stage card when the stage's
 * stamped ``sourcedFromXxxVersion`` is older than the upstream
 * head's current ``versionNo`` — i.e. an upstream stage moved on
 * after this stage was sourced. The user can click **Re-source**
 * to re-run the auto-population from current heads, creating a new
 * version of this stage.
 *
 * Pure presentation: parents compute the ``stale`` boolean and the
 * ``message`` describing why; this component renders the chrome and
 * fires ``(resource)`` on confirmed click. ``canResource`` gates
 * the action button (per-stage Unlock-and-Edit permission).
 */
@Component({
  selector: 'app-stale-banner',
  standalone: true,
  imports: [
    CommonModule, MatButtonModule, MatIconModule, MatTooltipModule,
    MatProgressSpinnerModule, MatDialogModule,
  ],
  template: `
    @if (stale) {
      <div class="stale-banner">
        <mat-icon class="stale-ico">history_toggle_off</mat-icon>
        <div class="stale-text">
          <div class="stale-title">{{ title || 'Stale relative to upstream' }}</div>
          <div class="stale-msg">{{ message }}</div>
        </div>
        <button mat-stroked-button color="warn" class="stale-btn"
          *ngIf="canResource && !hideAction"
          (click)="confirmResource()" [disabled]="busy"
          matTooltip="Refresh this stage by re-running auto-population from the current upstream heads. Creates a new version (audited).">
          @if (busy) {
            <mat-spinner diameter="14" class="inline-spinner"></mat-spinner>
          } @else {
            <mat-icon>refresh</mat-icon>
          }
          Re-source
        </button>
        <span *ngIf="!canResource && !hideAction" class="stale-perm-hint"
              matTooltip="Re-source needs the same Unlock-and-Edit permission as Restore for this stage.">
          <mat-icon>lock</mat-icon>
        </span>
      </div>
    }
  `,
  styles: [`
    .stale-banner {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      margin: 0 0 14px;
      background: rgba(245, 124, 0, 0.10);
      border-left: 3px solid #f57c00;
      border-radius: 4px;
      color: rgba(0,0,0,.78);
    }
    .stale-ico {
      color: #f57c00;
      flex-shrink: 0;
    }
    .stale-text { flex: 1; min-width: 0; }
    .stale-title {
      font-size: 13px; font-weight: 600;
      color: var(--snm-text-primary, #1a1a1a);
    }
    .stale-msg {
      font-size: 12px;
      color: var(--snm-text-secondary, rgba(0,0,0,0.65));
      margin-top: 2px;
    }
    .stale-btn {
      flex-shrink: 0;
      min-width: 110px;
      font-size: 12px !important;
      line-height: 1.2 !important;
    }
    .stale-btn mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .stale-perm-hint {
      flex-shrink: 0;
      color: var(--snm-text-faint);
      display: inline-flex; align-items: center;
    }
    .stale-perm-hint mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .inline-spinner { display: inline-block; margin-right: 6px; }
  `],
})
export class StaleBannerComponent {
  /** Whether to render the banner. Parent computes from upstream
   *  version comparison. */
  @Input() stale = false;
  /** Optional title; defaults to "Stale relative to upstream". */
  @Input() title?: string;
  /** Required when ``stale`` is true. Explains what's out of date. */
  @Input() message = '';
  /** Gates the Re-source button. */
  @Input() canResource = false;
  /** Inline spinner / disabled state on the Re-source button. */
  @Input() busy = false;
  /** Plain-English label for the confirm dialog (e.g. "Purchase Order"). */
  @Input() stageLabel = 'this stage';
  /** Hide both the Re-source button and the lock-hint icon — for
   *  hosts that surface a dedicated Re-source action elsewhere (e.g.
   *  the action cluster on Viability + Annexure). Keeps the banner
   *  as an informational notice only. */
  @Input() hideAction = false;

  @Output() resource = new EventEmitter<void>();

  constructor(private dialog: MatDialog) {}

  confirmResource(): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: `Re-source ${this.stageLabel}?`,
        message:
          `This archives the current head and creates a new version ` +
          `auto-populated from the current upstream heads. The new ` +
          `version starts as Draft and goes through normal approval. ` +
          `Action is logged in the audit trail.`,
        confirmText: 'Re-source',
        confirmColor: 'warn',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.resource.emit();
    });
  }
}
