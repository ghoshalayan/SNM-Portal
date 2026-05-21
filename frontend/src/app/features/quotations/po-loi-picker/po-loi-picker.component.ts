import {
  Component, EventEmitter, Input, OnChanges, OnInit, Output, SimpleChanges,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  CycleService, CyclePurchaseOrder,
} from '../services/cycle.service';
import { NotificationService } from '../../../core/services/notification.service';

/**
 * Picker for the cycle's PO/LOI siblings. The version-selector
 * conflated cycle-siblings with version-chain rows (both surfaced as
 * "v1 HEAD" lines), making it impossible to switch between them.
 * This component owns that interaction: lists the active cycle's
 * POs/LOIs in a mat-menu, emits the picked id on row click. Parent
 * rebinds the PO Header form + attachments panel accordingly.
 *
 * Loads its own data via ``cycleService.bundle()`` and refreshes
 * whenever ``cycleId`` changes (e.g. user flipped the cycle pill on
 * the strip above). Parent can force a reload via ``reload()`` after
 * an append.
 */
@Component({
  selector: 'app-po-loi-picker',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <button type="button" class="pop-btn"
            [matMenuTriggerFor]="popMenu"
            [matTooltip]="tooltipText()">
      <mat-icon class="pop-ico">{{ activeRowIsLOI() ? 'edit_note' : 'receipt_long' }}</mat-icon>
      <span class="pop-label">{{ activeLabel() }}</span>
      <mat-icon class="pop-caret">expand_more</mat-icon>
    </button>

    <mat-menu #popMenu="matMenu" class="pop-menu" xPosition="before">
      <div class="pop-menu-head" (click)="$event.stopPropagation()">
        <mat-icon>list_alt</mat-icon>
        <span>POs &amp; LOIs in this cycle</span>
      </div>

      <div *ngIf="loading" class="pop-menu-loading">
        <mat-spinner diameter="24"></mat-spinner>
      </div>

      <div *ngIf="!loading && rows.length === 0" class="pop-menu-empty">
        No POs or LOIs in this cycle yet.
      </div>

      <div *ngIf="!loading && rows.length > 0" class="pop-list">
        <button mat-menu-item *ngFor="let r of rows"
                [class.is-active]="r.quotPOId === selectedPoId"
                (click)="onRowClick(r)">
          <div class="pop-row">
            <span class="pop-kind" [class.is-loi]="r.isLOI">
              {{ r.isLOI ? 'LOI' : 'PO' }}
            </span>
            <div class="pop-row-main">
              <div class="pop-row-title">
                <span class="pop-po-no">{{ r.poNo }}</span>
                <span class="pop-status">{{ r.status }}</span>
                <mat-icon *ngIf="r.quotPOId === selectedPoId"
                          class="pop-active-tick"
                          matTooltip="Currently shown">check_circle</mat-icon>
              </div>
              <div class="pop-row-meta">
                seq {{ r.loiSequence ?? '—' }} ·
                dated {{ r.poDate | date:'dd-MMM-yyyy' }}
              </div>
            </div>
          </div>
        </button>
      </div>
    </mat-menu>
  `,
  styles: [`
    .pop-btn {
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
    .pop-btn:hover { background: rgba(58, 107, 181, 0.18); }
    .pop-ico { font-size: 14px; width: 14px; height: 14px; }
    .pop-caret { font-size: 16px; width: 16px; height: 16px; opacity: 0.7; }
    .pop-label { line-height: 1; }

    ::ng-deep .pop-menu .mat-mdc-menu-content { padding: 0 !important; min-width: 320px; }
    .pop-menu-head {
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
    .pop-menu-head mat-icon {
      font-size: 18px; width: 18px; height: 18px;
      color: var(--snm-accent-dark);
    }
    .pop-menu-loading, .pop-menu-empty {
      display: flex; justify-content: center; align-items: center;
      padding: 24px 16px;
      color: var(--snm-text-muted);
      font-size: 13px;
    }
    .pop-list { max-height: 360px; overflow-y: auto; }
    .pop-row {
      display: flex; align-items: flex-start; gap: 10px;
      padding: 2px 0;
    }
    .pop-kind {
      padding: 2px 8px; border-radius: 10px;
      background: rgba(25,118,210,.12); color: #1976d2;
      font-size: 10px; font-weight: 700;
      letter-spacing: 0.4px;
      margin-top: 2px;
      flex-shrink: 0;
    }
    .pop-kind.is-loi { background: rgba(245,124,0,.14); color: #f57c00; }
    .pop-row-main { flex: 1; min-width: 0; }
    .pop-row-title {
      display: flex; align-items: center; gap: 6px;
      font-weight: 600; font-size: 13px;
      color: var(--snm-text-primary);
    }
    .pop-po-no { line-height: 1.1; }
    .pop-status {
      font-size: 10px; text-transform: uppercase;
      color: var(--snm-text-muted);
      font-weight: 600;
      letter-spacing: 0.3px;
    }
    .pop-active-tick {
      font-size: 14px; width: 14px; height: 14px;
      color: #2e7d32;
    }
    .pop-row-meta {
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }
    button[mat-menu-item].is-active {
      background: rgba(46,125,50,0.06);
    }
  `],
})
export class PoLoiPickerComponent implements OnInit, OnChanges {
  /** Parent quotation. Required so the picker can call the cycle
   *  bundle endpoint. */
  @Input({ required: true }) quotId!: number;

  /** Active cycle id from the cycle-pill strip above the picker.
   *  Re-fetches the bundle whenever this changes. */
  @Input() cycleId: number | null = null;

  /** Currently-selected PO/LOI id; parent owns the state and passes
   *  it back so the dropdown can highlight the active row. */
  @Input() selectedPoId: number | null = null;

  /** Emits the picked PO id when the user clicks a row. Parent
   *  rebinds the PO Header form + Attachments panel. */
  @Output() poSelected = new EventEmitter<CyclePurchaseOrder>();

  /** Emits the full list whenever a fetch completes — lets the parent
   *  auto-select the first row on initial load or a freshly appended
   *  row after a cycle append. */
  @Output() rowsLoaded = new EventEmitter<CyclePurchaseOrder[]>();

  rows: CyclePurchaseOrder[] = [];
  loading = false;

  constructor(
    private cycleService: CycleService,
    private notifications: NotificationService,
  ) {}

  ngOnInit(): void {
    if (this.quotId && this.cycleId) this.reload();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (
      (changes['cycleId'] && !changes['cycleId'].firstChange)
      || (changes['quotId'] && !changes['quotId'].firstChange)
    ) {
      if (this.quotId && this.cycleId) this.reload();
      else this.rows = [];
    }
  }

  /** Re-fetch the cycle bundle. Parent calls this after appending a
   *  new PO/LOI so the dropdown picks up the new row. */
  reload(): void {
    if (!this.quotId || !this.cycleId) return;
    this.loading = true;
    this.cycleService.bundle(this.quotId, this.cycleId).subscribe({
      next: (bundle) => {
        this.rows = bundle.purchaseOrders || [];
        this.rowsLoaded.emit(this.rows);
        this.loading = false;
      },
      error: (e) => {
        this.loading = false;
        this.notifications.error(
          e?.error?.message || e?.error?.detail || 'Failed to load POs/LOIs.',
        );
      },
    });
  }

  onRowClick(r: CyclePurchaseOrder): void {
    if (r.quotPOId === this.selectedPoId) return;
    this.poSelected.emit(r);
  }

  activeRow(): CyclePurchaseOrder | undefined {
    return this.rows.find(r => r.quotPOId === this.selectedPoId);
  }

  activeRowIsLOI(): boolean {
    return !!this.activeRow()?.isLOI;
  }

  activeLabel(): string {
    const r = this.activeRow();
    if (!r) {
      return this.rows.length ? 'Select PO/LOI' : 'No POs/LOIs';
    }
    const kind = r.isLOI ? 'LOI' : 'PO';
    return `${kind} ${r.poNo}`;
  }

  tooltipText(): string {
    return this.rows.length > 1
      ? 'Switch between POs and LOIs in this cycle'
      : 'PO/LOI selector';
  }
}
