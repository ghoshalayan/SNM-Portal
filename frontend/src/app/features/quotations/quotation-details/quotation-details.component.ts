import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatBadgeModule } from '@angular/material/badge';
import { MatMenuModule } from '@angular/material/menu';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { DEDUCTED_COST_HEADS } from './quotation-detail-dialog.component';
import {
  BulkApplyCandidateRow,
  BulkApplyDialogComponent,
  BulkApplyDialogData,
  BulkApplyDialogResult,
} from '../shared/bulk-apply-dialog.component';
import {
  SheetPreviewColumn,
  SheetPreviewDialogComponent,
  SheetPreviewDialogData,
} from '../shared/sheet-preview-dialog.component';

/** All cost-head keys in display order */
const COST_HEADS: (keyof QuotLineItem)[] = [
  'TPWGST', 'Marketing', 'FreightTrailer', 'FreightTruck', 'Unloading',
  'OHD', 'IFC', 'WeighmentDiff', 'CD', 'SWECharge', 'CRS', 'IncCharge',
  'ShortLnthCharge', 'SpeciFicLnthCharge', 'ExtraCharge', 'Fluctuation',
  'Commission', 'Misc', 'Testing', 'MOUTOD', 'SplDisc', 'JC',
];

/** Human-readable labels */
const COST_HEAD_LABELS: Record<string, string> = {
  TPWGST: 'T.P. w/o GST', Marketing: 'Marketing',
  FreightTrailer: 'Freight (Trailer)', FreightTruck: 'Freight (Truck)',
  Unloading: 'Unloading', OHD: 'OHD', IFC: 'IFC',
  WeighmentDiff: 'Weighment Diff.', CD: 'CD',
  SWECharge: 'SWE Charges', CRS: 'CRS',
  IncCharge: 'Incidental', ShortLnthCharge: 'Short Length',
  SpeciFicLnthCharge: 'Specific Length', ExtraCharge: 'Extra',
  Fluctuation: 'Fluctuation', Commission: 'Commission',
  Misc: 'Misc.', Testing: 'Testing', MOUTOD: 'MOU TOD',
  SplDisc: 'Spl. Discount', JC: 'JC',
};

export interface QuotLineItem {
  quotDtlId?: number;
  quotId: number;
  itemid?: number;
  itemGradeName: string;
  itemDia: string;
  itemLength: string;
  itemUnit: string;
  quantity: number;
  // cost heads
  TPWGST?: number; Marketing?: number; FreightTrailer?: number; FreightTruck?: number;
  Unloading?: number; OHD?: number; IFC?: number; WeighmentDiff?: number;
  CD?: number; SWECharge?: number; CRS?: number; IncCharge?: number;
  ShortLnthCharge?: number; SpeciFicLnthCharge?: number; ExtraCharge?: number;
  Fluctuation?: number; Commission?: number; Misc?: number; Testing?: number;
  MOUTOD?: number; SplDisc?: number; JC?: number;
  // calculated
  totRate?: number;
  gstMode?: string;
  IGST?: number;
  CGST?: number;
  SGST?: number;
  totAmount?: number;
  // transient
  isEditing?: boolean;
  isDirty?: boolean;
  isSaving?: boolean;
  [key: string]: any;
}

interface ItemGrade { itemGradeId: number; itemGradeName: string; }
interface Dia { diaid: number; itemid: number; diadescription: string; }
interface ItemLength { itemLengthId: number; itemId: number; itemLength: string; }

@Component({
  selector: 'app-quotation-details',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatTableModule, MatButtonModule, MatIconModule,
    MatInputModule, MatFormFieldModule, MatSelectModule, MatTooltipModule,
    MatDialogModule, MatProgressSpinnerModule, MatSlideToggleModule, MatBadgeModule,
    MatMenuModule, MatCheckboxModule,
  ],
  template: `
    <div class="line-items-panel" [class.expanded]="isExpanded">

      <!-- Toolbar -->
      <div class="panel-toolbar">
        <div class="toolbar-left">
          <mat-icon class="toolbar-icon">list_alt</mat-icon>
          <span class="toolbar-title">Quotation Line Items (Working Sheet)</span>
          <span class="item-count" *ngIf="dataSource.data.length">
            {{ dataSource.data.length }} item{{ dataSource.data.length > 1 ? 's' : '' }}
          </span>
        </div>
        <div class="toolbar-right">
          <!-- GST Mode toggle -->
          <div class="gst-mode-toggle" *ngIf="!readOnly && dataSource.data.length > 0">
            <span class="gst-mode-label" [class.active]="!globalIGST">CGST+SGST</span>
            <mat-slide-toggle [checked]="globalIGST" (change)="setGlobalGstMode($event.checked)"
              color="primary" class="gst-global-toggle">
            </mat-slide-toggle>
            <span class="gst-mode-label" [class.active]="globalIGST">IGST</span>
          </div>

          <!-- Compact toggle: hides cost heads where every row is empty/zero -->
          <button mat-icon-button class="toolbar-icon-btn"
            *ngIf="dataSource.data.length > 0"
            (click)="toggleCompactMode()"
            [color]="compactMode ? 'primary' : undefined"
            [matTooltip]="compactMode ? 'Show all columns' : 'Compact view — hide empty columns'">
            <mat-icon>{{ compactMode ? 'unfold_more' : 'unfold_less' }}</mat-icon>
          </button>

          <!-- Column picker -->
          <button mat-icon-button class="toolbar-icon-btn"
            [matMenuTriggerFor]="colMenu"
            [matBadge]="hiddenHeadCount > 0 ? hiddenHeadCount : null"
            matBadgeColor="warn" matBadgeSize="small"
            matTooltip="Show / hide cost head columns">
            <mat-icon>view_column</mat-icon>
          </button>
          <mat-menu #colMenu="matMenu" class="col-picker-menu" xPosition="before">
            <div class="cp-header" (click)="$event.stopPropagation()">
              <span>Cost Head Columns</span>
              <button mat-button color="primary" type="button" (click)="showAllHeads()">Reset</button>
            </div>
            <div class="cp-body" (click)="$event.stopPropagation()">
              @for (h of costHeads; track h) {
                <mat-checkbox
                  [checked]="!hiddenCostHeads.has(h)"
                  (change)="toggleCostHead(h, $event.checked)"
                  class="cp-item">
                  {{ costHeadLabel(h) }}
                </mat-checkbox>
              }
            </div>
          </mat-menu>

          <!-- "Fetch from Enquiry" doesn't apply to the PO Working
               Sheet (PO BOM seeds from the quotation, not the
               enquiry). Excel export works in both modes; the URL
               flips per-mode inside the downloadExcel method. -->
          <button mat-stroked-button class="toolbar-btn fetch-btn"
            (click)="fetchFromEnquiry()"
            *ngIf="!isPoMode && enqId && dataSource.data.length === 0 && !readOnly" [disabled]="importing">
            <mat-icon>cloud_download</mat-icon>
            {{ importing ? 'Importing...' : 'Fetch from Enquiry' }}
          </button>
          <button mat-stroked-button class="toolbar-btn excel-btn"
            (click)="downloadExcel()"
            *ngIf="dataSource.data.length > 0"
            [disabled]="downloading"
            matTooltip="Download line items as Excel">
            <mat-icon>download</mat-icon>
            {{ downloading ? 'Downloading...' : 'Excel' }}
          </button>
          <button mat-stroked-button class="toolbar-btn preview-btn"
            (click)="openPreview()"
            *ngIf="dataSource.data.length > 0"
            matTooltip="Preview the sheet with blank columns hidden">
            <mat-icon>visibility</mat-icon> Preview
          </button>
          <button mat-stroked-button class="toolbar-btn add-btn" (click)="addRow()" *ngIf="!readOnly">
            <mat-icon>add_circle_outline</mat-icon> Add Item
          </button>
          <button mat-icon-button class="toolbar-icon-btn" (click)="toggleExpand()"
            [matTooltip]="isExpanded ? 'Collapse (Esc)' : 'Expand Wide'">
            <mat-icon>{{ isExpanded ? 'fullscreen_exit' : 'fullscreen' }}</mat-icon>
          </button>
        </div>
      </div>

      <!-- Loading -->
      <div class="loading-bar" *ngIf="loading">
        <mat-spinner diameter="32"></mat-spinner>
        <span>Loading line items...</span>
      </div>

      <!-- Table -->
      <div class="table-scroll" *ngIf="!loading">
        <table mat-table [dataSource]="dataSource" class="line-items-table">

          <!-- Sl No -->
          <ng-container matColumnDef="index" sticky>
            <th mat-header-cell *matHeaderCellDef class="col-index">#</th>
            <td mat-cell *matCellDef="let row; let i = index" class="col-index">{{ i + 1 }}</td>
          </ng-container>

          <!-- Item Name + Grade (combined column) -->
          <ng-container matColumnDef="itemGradeName" sticky>
            <th mat-header-cell *matHeaderCellDef class="col-item">Item / Grade</th>
            <td mat-cell *matCellDef="let row" class="col-item">
              <span class="display-val" *ngIf="!row.isEditing">
                <span *ngIf="row.itemName" class="item-name-tag">{{ row.itemName }}</span>
                {{ row.itemGradeName || '-' }}
              </span>
              <mat-form-field *ngIf="row.isEditing" appearance="outline" class="inline-field field-md">
                <mat-select [(ngModel)]="row._itemGradeId"
                  (ngModelChange)="onGradeChange(row)"
                  [ngModelOptions]="{standalone: true}"
                  (openedChange)="onDropdownOpen($event, 'grade')"
                  panelClass="searchable-panel"
                  placeholder="Select">
                  <div class="select-search" (click)="$event.stopPropagation()">
                    <mat-icon class="search-ico">search</mat-icon>
                    <input placeholder="Search..." [value]="search.grade"
                      (input)="search.grade = $any($event.target).value"
                      (keydown)="$event.stopPropagation()">
                  </div>
                  @for (g of filteredGrades(); track g.itemGradeId) {
                    <mat-option [value]="g.itemGradeId">{{ g.itemGradeName }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </td>
          </ng-container>

          <!-- Dia -->
          <ng-container matColumnDef="itemDia" sticky>
            <th mat-header-cell *matHeaderCellDef class="col-dia">Dia (mm)</th>
            <td mat-cell *matCellDef="let row" class="col-dia">
              <span class="display-val" *ngIf="!row.isEditing">{{ row.itemDia || '-' }}</span>
              <mat-form-field *ngIf="row.isEditing" appearance="outline" class="inline-field field-sm">
                <mat-select [(ngModel)]="row.itemDia" [ngModelOptions]="{standalone: true}"
                  (ngModelChange)="onDiaChange(row)"
                  (openedChange)="onDropdownOpen($event, 'dia')" panelClass="searchable-panel"
                  placeholder="Select">
                  <div class="select-search" (click)="$event.stopPropagation()">
                    <mat-icon class="search-ico">search</mat-icon>
                    <input placeholder="Search..." [value]="search.dia"
                      (input)="search.dia = $any($event.target).value"
                      (keydown)="$event.stopPropagation()">
                  </div>
                  @for (d of filteredDias(); track d.diaid) {
                    <mat-option [value]="d.diadescription">{{ d.diadescription }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </td>
          </ng-container>

          <!-- Length -->
          <ng-container matColumnDef="itemLength">
            <th mat-header-cell *matHeaderCellDef class="col-len">Length</th>
            <td mat-cell *matCellDef="let row" class="col-len">
              <span class="display-val" *ngIf="!row.isEditing">{{ row.itemLength || '-' }}</span>
              <mat-form-field *ngIf="row.isEditing" appearance="outline" class="inline-field field-sm">
                <mat-select [(ngModel)]="row.itemLength" [ngModelOptions]="{standalone: true}"
                  (openedChange)="onDropdownOpen($event, 'length')" panelClass="searchable-panel"
                  placeholder="Select">
                  <div class="select-search" (click)="$event.stopPropagation()">
                    <mat-icon class="search-ico">search</mat-icon>
                    <input placeholder="Search..." [value]="search.length"
                      (input)="search.length = $any($event.target).value"
                      (keydown)="$event.stopPropagation()">
                  </div>
                  @for (l of filteredLengths(); track l.itemLengthId) {
                    <mat-option [value]="l.itemLength">{{ l.itemLength }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </td>
          </ng-container>

          <!-- Unit -->
          <ng-container matColumnDef="itemUnit">
            <th mat-header-cell *matHeaderCellDef class="col-unit">Unit</th>
            <td mat-cell *matCellDef="let row" class="col-unit">
              <span class="display-val" *ngIf="!row.isEditing">{{ row.itemUnit }}</span>
              <mat-form-field *ngIf="row.isEditing" appearance="outline" class="inline-field field-xs">
                <mat-select [(ngModel)]="row.itemUnit" [ngModelOptions]="{standalone: true}">
                  <mat-option value="MT">MT</mat-option>
                  <mat-option value="KG">KG</mat-option>
                  <mat-option value="NOS">NOS</mat-option>
                </mat-select>
              </mat-form-field>
            </td>
          </ng-container>

          <!-- Qty -->
          <ng-container matColumnDef="quantity">
            <th mat-header-cell *matHeaderCellDef class="col-qty">Qty</th>
            <td mat-cell *matCellDef="let row" class="col-qty">
              <span class="display-val num" *ngIf="!row.isEditing">{{ row.quantity | number:'1.2-2' }}</span>
              <input *ngIf="row.isEditing" type="number" class="inline-num"
                [(ngModel)]="row.quantity" [ngModelOptions]="{standalone: true}"
                min="0" step="0.01" placeholder="0" />
            </td>
          </ng-container>

          <!-- Cost head columns -->
          @for (ch of costHeads; track ch) {
            <ng-container [matColumnDef]="ch">
              <th mat-header-cell *matHeaderCellDef class="col-cost"
                [matTooltip]="costHeadLabel(ch) + (isCellLocked(ch) ? lockReason(ch) : '')"
                [class.locked-col]="isCellLocked(ch)"
                [class.deducted]="isDeductedHead(ch)">
                {{ costHeadLabel(ch) }}
              </th>
              <td mat-cell *matCellDef="let row" class="col-cost"
                [class.tp-highlight]="ch === 'TPWGST' && row[ch]"
                [class.locked-cell]="isCellLocked(ch)"
                [class.deducted]="isDeductedHead(ch)">
                <span class="display-val num" *ngIf="!row.isEditing || isCellLocked(ch)">
                  {{ isCellLocked(ch) ? '0' : (row[ch] != null ? (row[ch] | number:'1.0-2') : '-') }}
                </span>
                <input *ngIf="row.isEditing && !isCellLocked(ch)" type="number" class="inline-num"
                  [(ngModel)]="row[ch]" [ngModelOptions]="{standalone: true}"
                  (ngModelChange)="onCostChange(row)" step="0.01" placeholder="0"
                  [class.tp-input]="ch === 'TPWGST'"
                  [class.deducted-input]="isDeductedHead(ch)" />
              </td>
            </ng-container>
          }

          <!-- Total (Rs/MT) -->
          <ng-container matColumnDef="totRate">
            <th mat-header-cell *matHeaderCellDef class="col-total">Total (Rs/MT)</th>
            <td mat-cell *matCellDef="let row" class="col-total">
              <strong>{{ row.totRate | number:'1.0-2' }}</strong>
            </td>
          </ng-container>

          <!-- GST -->
          <ng-container matColumnDef="gst">
            <th mat-header-cell *matHeaderCellDef class="col-gst">GST @ 18%</th>
            <td mat-cell *matCellDef="let row" class="col-gst">
              <div class="gst-cell">
                <span class="gst-amount">{{ getGstAmount(row) | number:'1.0-2' }}</span>
                <mat-slide-toggle *ngIf="row.isEditing"
                  [checked]="row.gstMode === 'CGST_SGST'"
                  (change)="toggleGstMode(row, $event.checked)"
                  class="gst-toggle">
                  <span class="gst-label">{{ row.gstMode === 'IGST' ? 'IGST' : 'C+S' }}</span>
                </mat-slide-toggle>
                <span class="gst-mode-badge" *ngIf="!row.isEditing">
                  {{ row.gstMode === 'CGST_SGST' ? 'C+S' : 'IGST' }}
                </span>
              </div>
            </td>
          </ng-container>

          <!-- EX/FOR Price -->
          <ng-container matColumnDef="totAmount" stickyEnd>
            <th mat-header-cell *matHeaderCellDef class="col-exfor">EX/FOR Price</th>
            <td mat-cell *matCellDef="let row" class="col-exfor">
              <strong class="exfor-val">{{ row.totAmount | number:'1.0-2' }}</strong>
            </td>
          </ng-container>

          <!-- Mode of Dispatch -->
          <ng-container matColumnDef="modeOfDispatch">
            <th mat-header-cell *matHeaderCellDef class="col-dispatch">Dispatch</th>
            <td mat-cell *matCellDef="let row" class="col-dispatch">
              <span class="display-val">{{ row.modeOfDispatch || '-' }}</span>
            </td>
          </ng-container>

          <!-- Actions -->
          <ng-container matColumnDef="actions" stickyEnd>
            <th mat-header-cell *matHeaderCellDef class="col-actions"></th>
            <td mat-cell *matCellDef="let row; let i = index" class="col-actions">
              <div class="action-group">
                <ng-container *ngIf="!row.isEditing && !readOnly">
                  <button mat-icon-button class="action-btn edit-btn" (click)="startEdit(row)" matTooltip="Edit">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button class="action-btn delete-btn" (click)="confirmDelete(row, i)" matTooltip="Delete">
                    <mat-icon>delete_outline</mat-icon>
                  </button>
                </ng-container>
              </div>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns; sticky: true"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"
            [class.editing-row]="row.isEditing"
            [class.dirty-row]="row.isDirty"></tr>

          <!-- Empty state -->
          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell empty-state" [attr.colspan]="displayedColumns.length">
              <div class="empty-content">
                <mat-icon>inventory_2</mat-icon>
                <h4>No Line Items</h4>
                <p *ngIf="enqId">Click <strong>Fetch from Enquiry</strong> to import items, or <strong>Add Item</strong> manually.</p>
                <p *ngIf="!enqId">Click <strong>Add Item</strong> to add quotation line items.</p>
              </div>
            </td>
          </tr>
        </table>
      </div>

      <!-- Footer summary -->
      <div class="panel-footer" *ngIf="dataSource.data.length > 0">
        <div class="summary-row">
          <span class="summary-label">Grand Total:</span>
          <span class="summary-val">{{ grandTotal | number:'1.0-2' }} Rs/MT</span>
          <span class="summary-sep">|</span>
          <span class="summary-label">Total Amount:</span>
          <span class="summary-val highlight">{{ grandTotalAmount | number:'1.0-2' }}</span>
        </div>
        <div class="footer-hint" *ngIf="!readOnly">
          Click <mat-icon class="hint-icon">edit</mat-icon> to edit a row inline, then <mat-icon class="hint-icon">check_circle</mat-icon> to save.
        </div>
      </div>
    </div>
  `,
  styleUrls: ['./quotation-details.component.scss'],
})
export class QuotationDetailsComponent implements OnInit, OnChanges {
  @Input() quotId!: number;
  @Input() enqId?: number;
  @Input() readOnly = false;
  /**
   * Delivery-term + delivery-mode together drive which freight column is
   * editable on each line:
   *   - Non-FOR (Ex-Factory etc.) → both FreightTrailer & FreightTruck open
   *     (buyer arranges transport but seller can still capture indicative
   *      freight on either mode).
   *   - FOR + Trailer → FreightTrailer open, FreightTruck locked at 0
   *   - FOR + Truck   → FreightTruck   open, FreightTrailer locked at 0
   *   - FOR + (no mode yet) → both open until the mode is picked, so the
   *     user isn't blocked from drafting numbers.
   */
  @Input() isForDeliveryTerm = false;
  @Input() deliveryModeName = '';
  /** Stage 1 (default) drives the quotation's QuotDetails endpoints.
   *  Stage 2 ('po') reuses the same grid + dialog but talks to the
   *  PO Working Sheet endpoints — full feature parity (cost-head
   *  editing, dia/length pickers, GST mode, TP-cost lookup, dialog
   *  add/edit) without duplicating any logic. The PO line response
   *  aliases ``poWorkingSheetId`` as ``quotDtlId`` so the existing
   *  PK references work uniformly. */
  @Input() mode: 'quotation' | 'po' = 'quotation';
  /** Cycle scope for the PO-mode listing. When supplied, the grid
   *  fetches via the cycle-aware endpoint so every active FWS row in
   *  the cycle is visible — independent of which PO/LOI owns the FK.
   *  Required for the soft-flow version switch to refresh correctly
   *  when a cycle has rows tied to multiple POs (formal + LOI). */
  @Input() cycleId?: number | null;
  @Output() expandedChange = new EventEmitter<boolean>();

  /** Endpoint base for line CRUD. Switches per mode.
   *
   *  In PO mode, the LIST endpoint prefers the cycle-aware path
   *  (``/cycles/{id}/working-sheet``) when a cycleId is supplied, so
   *  all of the cycle's working-sheet rows are returned regardless of
   *  which PO/LOI they're linked to. Per-line CRUD still goes through
   *  the legacy ``/purchase-order/working-sheet/{lineId}`` path because
   *  that route is line-PK-based and works the same either way. */
  get linesEndpoint(): string {
    if (this.mode === 'po') {
      if (this.cycleId) {
        return `/quotations/${this.quotId}/cycles/${this.cycleId}/working-sheet`;
      }
      return `/quotations/${this.quotId}/purchase-order/working-sheet`;
    }
    return `/quotations/${this.quotId}/details`;
  }
  /** Per-line CRUD endpoint base (PUT / DELETE / POST a single line).
   *  Stays on the legacy single-PO path because the route is line-PK
   *  driven — backend resolves the line by id, no cycle filter needed. */
  get lineCrudEndpoint(): string {
    return this.mode === 'po'
      ? `/quotations/${this.quotId}/purchase-order/working-sheet`
      : `/quotations/${this.quotId}/details`;
  }
  /** Some quotation-mode actions don't apply to the PO Working Sheet
   *  (e.g. "Import from Enquiry", "Export Excel"). Templates gate
   *  those buttons behind this flag. */
  get isPoMode(): boolean { return this.mode === 'po'; }

  isExpanded = false;
  costHeads = COST_HEADS as string[];
  dataSource = new MatTableDataSource<QuotLineItem>([]);

  // Cost-head columns a user has explicitly hidden via the column picker.
  // Persisted per-user in localStorage so the choice survives page reloads.
  private readonly COL_PREFS_KEY = 'snm-quot-cols';
  hiddenCostHeads = new Set<string>();

  /** Compact = only show cost heads that have non-zero values across all rows. */
  compactMode = false;

  displayedColumns: string[] = [];

  // Master data
  itemGrades: ItemGrade[] = [];
  allDias: Dia[] = [];
  allLengths: ItemLength[] = [];
  search = { grade: '', dia: '', length: '' };

  loading = false;
  importing = false;
  downloading = false;
  globalIGST = true;  // default to IGST

  private originalRowData = new Map<number, Partial<QuotLineItem>>();

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private http: HttpClient,
  ) {}

  ngOnInit(): void {
    this.loadColumnPrefs();
    this.rebuildDisplayedColumns();
    this.loadMasters();
    if (this.quotId) this.loadDetails();
  }

  // ---- Column visibility (compact + picker) ----
  private rebuildDisplayedColumns(): void {
    const visibleHeads = this.costHeads.filter(h => this.isCostHeadVisible(h));
    const cols: string[] = [
      'index', 'itemGradeName', 'itemDia', 'itemLength', 'itemUnit', 'quantity',
      ...visibleHeads,
      'totRate', 'gst', 'totAmount', 'modeOfDispatch',
    ];
    if (!this.readOnly) cols.push('actions');
    this.displayedColumns = cols;
  }

  isCostHeadVisible(key: string): boolean {
    if (this.hiddenCostHeads.has(key)) return false;
    if (this.compactMode) {
      // Hide heads where every row is null / 0 — treats the column as dead weight
      const rows = this.dataSource.data;
      if (rows.length === 0) return true;
      return rows.some(r => {
        const v = (r as any)[key];
        return v != null && Number(v) !== 0;
      });
    }
    return true;
  }

  toggleCompactMode(): void {
    this.compactMode = !this.compactMode;
    this.rebuildDisplayedColumns();
  }

  toggleCostHead(key: string, visible: boolean): void {
    if (visible) this.hiddenCostHeads.delete(key);
    else this.hiddenCostHeads.add(key);
    this.saveColumnPrefs();
    this.rebuildDisplayedColumns();
  }

  showAllHeads(): void {
    this.hiddenCostHeads.clear();
    this.compactMode = false;
    this.saveColumnPrefs();
    this.rebuildDisplayedColumns();
  }

  get hiddenHeadCount(): number {
    return this.hiddenCostHeads.size;
  }

  private loadColumnPrefs(): void {
    try {
      const raw = localStorage.getItem(this.COL_PREFS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed?.hidden)) {
        this.hiddenCostHeads = new Set(parsed.hidden);
      }
      if (typeof parsed?.compact === 'boolean') {
        this.compactMode = parsed.compact;
      }
    } catch { /* ignore corrupt prefs */ }
  }

  private saveColumnPrefs(): void {
    try {
      localStorage.setItem(this.COL_PREFS_KEY, JSON.stringify({
        hidden: Array.from(this.hiddenCostHeads),
        compact: this.compactMode,
      }));
    } catch { /* ignore quota errors */ }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && !changes['quotId'].firstChange && this.quotId) {
      this.loadDetails();
    }
    // Cycle scope change (PO mode, soft-flow) — re-fetch from the
    // cycle-aware endpoint so the grid reflects whatever cycle the
    // user just flipped to (and so version-switches that overwrite
    // the cycle's working sheet show up immediately).
    if (changes['cycleId'] && !changes['cycleId'].firstChange && this.quotId) {
      this.loadDetails();
    }
    // Whenever the delivery term or mode changes, re-evaluate which freight
    // column is locked and zero out the side that's now read-only so the
    // total reflects the locked state immediately.
    if (
      (changes['isForDeliveryTerm'] && !changes['isForDeliveryTerm'].firstChange)
      || (changes['deliveryModeName'] && !changes['deliveryModeName'].firstChange)
    ) {
      this.applyFreightLockState();
    }
  }

  /** True for the freight cost-head keys subject to the term/mode rules. */
  isFreightCol(ch: string): boolean {
    return ch === 'FreightTrailer' || ch === 'FreightTruck';
  }

  /** Tolerant matchers: cope with misspellings ("Trailor"), short forms
   *  ("Trk"), and synonyms ("Lorry") so the lock state mirrors whatever
   *  is in the company's DeliveryMode master. Same patterns the form-
   *  level validator uses. */
  private static readonly TRAILER_RE = /trail|trial/i;
  private static readonly TRUCK_RE = /truck|trk|lorr/i;

  /**
   * Per spec:
   *   Non-FOR (Ex-Factory etc.) → BOTH freight cells locked. Buyer arranges
   *     transport, so seller-side freight is irrelevant and forced to 0.
   *   FOR + Trailer mode → FreightTrailer open, FreightTruck locked
   *   FOR + Truck   mode → FreightTruck   open, FreightTrailer locked
   *   FOR + no mode chosen yet → both locked (force the user to pick a mode
   *     before entering freight numbers).
   */
  isCellLocked(ch: string): boolean {
    if (!this.isFreightCol(ch)) return false;
    if (!this.isForDeliveryTerm) return true;
    const mode = (this.deliveryModeName || '').trim();
    if (!mode) return true;
    const isTrailer = QuotationDetailsComponent.TRAILER_RE.test(mode);
    const isTruck = QuotationDetailsComponent.TRUCK_RE.test(mode);
    if (ch === 'FreightTrailer') return !isTrailer;
    if (ch === 'FreightTruck') return !isTruck;
    return false;
  }

  /** Tooltip suffix explaining why a freight cell is locked, so the user
   *  knows whether to change the term or the mode to unlock it. */
  lockReason(ch: string): string {
    if (!this.isCellLocked(ch)) return '';
    if (!this.isForDeliveryTerm) {
      return ' — locked (delivery term is not FOR)';
    }
    const mode = (this.deliveryModeName || '').trim();
    if (!mode) {
      return ' — locked (delivery mode not selected)';
    }
    if (ch === 'FreightTrailer') return ` — locked (delivery mode is ${mode})`;
    if (ch === 'FreightTruck') return ` — locked (delivery mode is ${mode})`;
    return '';
  }

  /**
   * Zero the LOCKED freight column on every line so totals don't carry a
   * stale value from the column that's now read-only. The unlocked side is
   * left untouched. Saves are pushed by row-level edit; this just keeps the
   * grid totals consistent with what the user can actually edit.
   */
  private applyFreightLockState(): void {
    let touched = false;
    for (const row of this.dataSource.data) {
      const trailerLocked = this.isCellLocked('FreightTrailer');
      const truckLocked = this.isCellLocked('FreightTruck');
      if (trailerLocked && (row.FreightTrailer ?? 0) !== 0) {
        row.FreightTrailer = 0;
        row.isDirty = true;
        touched = true;
      }
      if (truckLocked && (row.FreightTruck ?? 0) !== 0) {
        row.FreightTruck = 0;
        row.isDirty = true;
        touched = true;
      }
      if (touched) this.recalcRow(row);
    }
    if (touched) this.refresh();
  }

  // ---- Expand / Collapse ----

  toggleExpand(): void {
    this.isExpanded = !this.isExpanded;
    this.expandedChange.emit(this.isExpanded);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.isExpanded) {
      this.isExpanded = false;
      this.expandedChange.emit(false);
    }
  }

  // ---- Summaries ----

  get grandTotal(): number {
    return this.dataSource.data.reduce((s, r) => s + (r.totRate || 0), 0);
  }

  get grandTotalAmount(): number {
    return this.dataSource.data.reduce((s, r) => s + (r.totAmount || 0), 0);
  }

  costHeadLabel(key: string): string {
    return COST_HEAD_LABELS[key] || key;
  }

  /** True for cost heads stored as positive but subtracted in totRate
   *  (CR #2). Drives red-tinted header/cell/input styling. */
  isDeductedHead(key: string): boolean {
    return DEDUCTED_COST_HEADS.has(key);
  }

  // ---- Masters ----

  loadMasters(): void {
    this.api.get<ItemGrade[]>('/masters/item-grades').subscribe({
      next: d => this.itemGrades = d,
    });
    this.api.get<Dia[]>('/masters/dia-masters').subscribe({
      next: d => this.allDias = d,
    });
    this.api.get<ItemLength[]>('/masters/item-lengths').subscribe({
      next: d => this.allLengths = d,
    });
  }

  onDropdownOpen(opened: boolean, key: keyof typeof this.search): void {
    if (opened) this.search[key] = '';
  }

  filteredGrades(): ItemGrade[] {
    const t = this.search.grade.toLowerCase();
    return t ? this.itemGrades.filter(g => g.itemGradeName.toLowerCase().includes(t)) : this.itemGrades;
  }
  filteredDias(): Dia[] {
    const t = this.search.dia.toLowerCase();
    return t ? this.allDias.filter(d => d.diadescription.toLowerCase().includes(t)) : this.allDias;
  }
  filteredLengths(): ItemLength[] {
    const t = this.search.length.toLowerCase();
    return t ? this.allLengths.filter(l => l.itemLength.toLowerCase().includes(t)) : this.allLengths;
  }

  onGradeChange(row: QuotLineItem): void {
    const g = this.itemGrades.find(x => x.itemGradeId === row['_itemGradeId']);
    row.itemGradeName = g?.itemGradeName ?? '';
    row.isDirty = true;
  }

  onDiaChange(row: QuotLineItem): void {
    row.isDirty = true;
    if (!row.itemDia) return;
    // Auto-fetch TP cost from RawMaterialCost
    this.api.get<{ dia: string; tpcost: number | null }>(`/quotations/tp-cost/${row.itemDia}`).subscribe({
      next: res => {
        if (res.tpcost != null) {
          row.TPWGST = res.tpcost;
          this.recalcRow(row);
          this.refresh();
        }
      },
    });
  }

  // ---- Data ----

  loadDetails(): void {
    this.loading = true;
    this.api.get<QuotLineItem[]>(this.linesEndpoint).subscribe({
      next: data => {
        this.dataSource.data = data.map(d => ({ ...d, isEditing: false, isDirty: false, isSaving: false }));
        this.rebuildDisplayedColumns();
        // Detect global GST mode from first row
        if (data.length > 0) {
          this.globalIGST = data[0].gstMode !== 'CGST_SGST';
        }
        this.loading = false;
      },
      error: () => { this.notify.error('Failed to load line items'); this.loading = false; },
    });
  }

  fetchFromEnquiry(): void {
    if (!this.enqId) return;
    this.importing = true;
    this.api.post<QuotLineItem[]>(
      `/quotations/${this.quotId}/details/from-enquiry/${this.enqId}`, {}
    ).subscribe({
      next: data => {
        this.dataSource.data = data.map(d => ({ ...d, isEditing: false, isDirty: false, isSaving: false }));
        this.rebuildDisplayedColumns();
        this.importing = false;
        this.notify.success(`Imported ${data.length} line items from enquiry`);
      },
      error: () => { this.notify.error('Failed to import from enquiry'); this.importing = false; },
    });
  }

  /** Download line items as XLSX in standard quotation working format.
   *  In PO mode the URL flips to the PO Working Sheet export — the
   *  backend reuses the same xlsx builder, only the header context
   *  (customer / site / PO No / PO Date) swaps to come off the PO. */
  downloadExcel(): void {
    if (!this.quotId || this.downloading) return;
    this.downloading = true;
    const path = this.isPoMode
      ? `/quotations/${this.quotId}/purchase-order/working-sheet/export-excel`
      : `/quotations/${this.quotId}/details/export-excel`;
    const url = `${environment.apiUrl}${path}`;
    this.http.get(url, { responseType: 'blob', observe: 'response' }).subscribe({
      next: (resp) => {
        const blob = resp.body;
        if (!blob) {
          this.notify.error('Empty response');
          this.downloading = false;
          return;
        }
        // Extract filename from Content-Disposition header
        let filename = this.isPoMode
          ? `po-${this.quotId}-final-working-sheet.xlsx`
          : `quotation-${this.quotId}-line-items.xlsx`;
        const cd = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
        if (cd) {
          const match = /filename="?([^";]+)"?/i.exec(cd);
          if (match && match[1]) filename = match[1];
        }
        // Trigger browser download
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
        this.notify.success('Excel downloaded');
        this.downloading = false;
      },
      error: () => {
        this.notify.error('Failed to download Excel');
        this.downloading = false;
      },
    });
  }

  // ---- Preview (CR #3) ----

  /** Opens the preview modal showing the same columns but with a
   *  hide-blank-columns toggle and Print/Excel actions. Title flips per
   *  mode so the same component covers Working Sheet and FWS. */
  openPreview(): void {
    const columns: SheetPreviewColumn[] = [
      { key: 'itemName', label: 'Item' },
      { key: 'itemGradeName', label: 'Grade' },
      { key: 'itemDia', label: 'Dia' },
      { key: 'itemLength', label: 'Length' },
      { key: 'itemUnit', label: 'Unit' },
      { key: 'quantity', label: 'Qty', format: 'number' },
      ...COST_HEADS.map(ch => ({
        key: ch as string,
        label: this.costHeadLabel(ch as string),
        format: 'number' as const,
        cellClass: this.isDeductedHead(ch as string) ? 'neg' : undefined,
      })),
      { key: 'totRate', label: 'Total Rs/MT', format: 'number' },
      { key: 'IGST', label: 'IGST', format: 'number' },
      { key: 'CGST', label: 'CGST', format: 'number' },
      { key: 'SGST', label: 'SGST', format: 'number' },
      { key: 'totAmount', label: 'EX/FOR Price', format: 'number' },
      { key: 'modeOfDispatch', label: 'Dispatch' },
    ];
    const data: SheetPreviewDialogData = {
      title: this.isPoMode ? 'Final Working Sheet — Preview' : 'Working Sheet — Preview',
      caption: `${this.dataSource.data.length} line${this.dataSource.data.length === 1 ? '' : 's'}`,
      columns,
      rows: this.dataSource.data,
      hideBlankByDefault: true,
      onExportExcel: () => this.downloadExcel(),
    };
    this.dialog.open(SheetPreviewDialogComponent, {
      width: 'auto',
      maxWidth: '95vw',
      data,
    });
  }

  // ---- Calculations ----

  onCostChange(row: QuotLineItem): void {
    row.isDirty = true;
    this.recalcRow(row);
  }

  recalcRow(row: QuotLineItem): void {
    let total = 0;
    for (const ch of COST_HEADS) {
      const v = Number(row[ch as string]) || 0;
      total += DEDUCTED_COST_HEADS.has(ch as string) ? -v : v;
    }
    row.totRate = Math.round(total * 100) / 100;

    const gst = Math.round(row.totRate * 0.18 * 100) / 100;
    if (row.gstMode === 'CGST_SGST') {
      row.IGST = 0;
      row.CGST = Math.round(gst / 2 * 100) / 100;
      row.SGST = Math.round(gst / 2 * 100) / 100;
    } else {
      row.IGST = gst;
      row.CGST = 0;
      row.SGST = 0;
    }
    row.totAmount = Math.round((row.totRate + gst) * 100) / 100;
  }

  getGstAmount(row: QuotLineItem): number {
    return Math.round((row.totRate || 0) * 0.18 * 100) / 100;
  }

  toggleGstMode(row: QuotLineItem, isCgstSgst: boolean): void {
    row.gstMode = isCgstSgst ? 'CGST_SGST' : 'IGST';
    row.isDirty = true;
    this.recalcRow(row);
  }

  /** Switch ALL rows to IGST or CGST+SGST at once and persist */
  setGlobalGstMode(isIGST: boolean): void {
    this.globalIGST = isIGST;
    const mode = isIGST ? 'IGST' : 'CGST_SGST';
    for (const row of this.dataSource.data) {
      if (row.gstMode !== mode) {
        row.gstMode = mode;
        this.recalcRow(row);
        if (row.quotDtlId) {
          const payload: Record<string, any> = {};
          for (const key of ['itemid', 'itemGradeName', 'itemDia', 'itemLength', 'itemUnit', 'quantity',
            'gstMode', 'IGST', 'CGST', 'SGST', 'totRate', 'totAmount', ...COST_HEADS as string[]]) {
            payload[key] = row[key] ?? null;
          }
          payload['quantity'] = payload['quantity'] || 1;
          payload['basicRate'] = payload['totRate'];
          this.api.put(`${this.lineCrudEndpoint}/${row.quotDtlId}`, payload).subscribe();
        }
      }
    }
  }

  // ---- Row CRUD ----

  addRow(): void {
    this.openDetailDialog(null);
  }

  startEdit(row: QuotLineItem): void {
    this.openDetailDialog(row);
  }

  private openDetailDialog(detail: QuotLineItem | null): void {
    const items = this.dataSource.data;
    let previousRow: QuotLineItem | null = null;
    if (detail) {
      // Editing: previous = the row just before this one in the list
      const idx = items.findIndex(r => r.quotDtlId === detail.quotDtlId);
      if (idx > 0) previousRow = items[idx - 1];
    } else {
      // Adding: previous = last row in the list
      if (items.length > 0) previousRow = items[items.length - 1];
    }

    import('./quotation-detail-dialog.component').then(m => {
      const ref = this.dialog.open(m.QuotationDetailDialogComponent, {
        width: '820px',
        maxWidth: '95vw',
        data: {
          quotId: this.quotId,
          detail,
          previousRow,
          isForDeliveryTerm: this.isForDeliveryTerm,
          deliveryModeName: this.deliveryModeName,
          mode: this.mode,
        },
        disableClose: true,
      });
      ref.afterClosed().subscribe(result => {
        if (!result) return;
        this.loadDetails();
        // CR #1 — FWS bulk-apply prompt. Only fires in PO (Final
        // Working Sheet) mode and only when exactly one cost-head
        // field changed. Multi-field edits skip the prompt to avoid
        // chaining N modals; user can re-edit a row to propagate
        // additional fields.
        if (typeof result === 'object'
            && result.mode === 'po'
            && Array.isArray(result.changedCostHeads)
            && result.changedCostHeads.length === 1
            && result.sourceRowId != null) {
          this.promptFwsBulkApply(
            result.sourceRowId,
            result.changedCostHeads[0],
          );
        }
      });
    });
  }

  /** Opens the bulk-apply modal for one cost-head change captured by
   *  the line-item dialog (CR #1, FWS mode). Confirmed propagation
   *  fires per-row PUTs against the FWS endpoint. */
  private promptFwsBulkApply(
    sourceRowId: number,
    change: { key: string; oldValue: number | null; newValue: number | null },
  ): void {
    const rows = this.dataSource.data;
    const source = rows.find(r => r.quotDtlId === sourceRowId);
    const otherRows = rows.filter(r => r.quotDtlId !== sourceRowId && r.quotDtlId != null);
    if (!otherRows.length) return;  // nothing to propagate to

    const data: BulkApplyDialogData = {
      fieldLabel: this.costHeadLabel(change.key),
      oldValue: change.oldValue,
      newValue: change.newValue,
      sourceRowLabel: this.rowSummary(source),
      candidateRows: otherRows.map((r): BulkApplyCandidateRow => ({
        id: r.quotDtlId as number,
        label: this.rowSummary(r),
        currentValue: (r as any)[change.key] ?? null,
      })),
    };
    const ref = this.dialog.open<
      BulkApplyDialogComponent, BulkApplyDialogData, BulkApplyDialogResult
    >(BulkApplyDialogComponent, { width: '640px', data });

    ref.afterClosed().subscribe(result => {
      if (!result || !result.confirmed) return;
      if (!result.applyToRowIds.length) return;  // user confirmed source only
      this.fanOutFwsBulkApply(result.applyToRowIds, change.key, change.newValue);
    });
  }

  /** One-line summary used in the bulk-apply modal (source preface and
   *  per-row picker). */
  private rowSummary(row: any): string {
    if (!row) return '';
    const parts = [
      row.itemName,
      row.itemGradeName,
      row.itemDia ? `Ø ${row.itemDia}` : '',
      row.itemLength,
      row.quantity != null ? `${row.quantity} MT` : '',
    ].filter(Boolean);
    return parts.join(' · ');
  }

  /** Apply the bulk change to N rows via PUT. The full row is recalc'd
   *  locally and the totRate/totAmount are recomputed before sending so
   *  the server stays consistent without a second round-trip. */
  private fanOutFwsBulkApply(
    targetRowIds: (number | string)[],
    key: string,
    value: number | null,
  ): void {
    const rowsById = new Map<number | string, any>();
    for (const r of this.dataSource.data) {
      if (r.quotDtlId != null) rowsById.set(r.quotDtlId, r);
    }
    let ok = 0;
    let failed = 0;
    const finish = () => {
      if (ok + failed === targetRowIds.length) {
        if (failed === 0) {
          this.notify.success(`Applied to ${ok} additional line${ok === 1 ? '' : 's'}.`);
        } else {
          this.notify.error(`Applied to ${ok}; ${failed} failed.`);
        }
        this.loadDetails();
      }
    };
    for (const id of targetRowIds) {
      const row = rowsById.get(id);
      if (!row) { failed++; finish(); continue; }
      (row as any)[key] = value;
      this.recalcRow(row);
      // Build payload mirroring the dialog save shape — every cost head
      // + the recomputed totals so the server has a consistent row.
      const payload: any = { basicRate: row.totRate };
      for (const col of [...COST_HEADS, 'totRate', 'totAmount', 'IGST', 'CGST', 'SGST', 'gstMode']) {
        payload[col as string] = (row as any)[col as string] ?? null;
      }
      this.api.put(`${this.lineCrudEndpoint}/${row.quotDtlId}`, payload).subscribe({
        next: () => { ok++; finish(); },
        error: () => { failed++; finish(); },
      });
    }
  }

  confirmDelete(row: QuotLineItem, index: number): void {
    if (!row.quotDtlId) {
      this.dataSource.data = this.dataSource.data.filter((_, i) => i !== index);
      return;
    }
    const ref = this.dialog.open(ConfirmDialogComponent, {
      width: '380px',
      data: {
        title: 'Delete Line Item',
        message: `Delete ${row.itemGradeName} Dia ${row.itemDia}?`,
        confirmLabel: 'Delete', confirmColor: 'warn',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) {
        this.api.delete(`${this.lineCrudEndpoint}/${row.quotDtlId}`).subscribe({
          next: () => {
            this.dataSource.data = this.dataSource.data.filter((_, i) => i !== index);
            this.notify.success('Deleted');
          },
          error: () => this.notify.error('Failed to delete'),
        });
      }
    });
  }

  private refresh(): void {
    this.dataSource.data = [...this.dataSource.data];
  }
}
