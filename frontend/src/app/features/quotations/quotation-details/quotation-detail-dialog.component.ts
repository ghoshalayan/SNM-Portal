import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDividerModule } from '@angular/material/divider';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { SearchFilterPipe } from '../../../shared/pipes/search-filter.pipe';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

const INHERITABLE_FIELDS = [
  'Marketing', 'FreightTrailer', 'FreightTruck', 'Unloading', 'OHD', 'IFC',
  'WeighmentDiff', 'CD', 'SWECharge', 'CRS', 'IncCharge', 'ShortLnthCharge',
  'SpeciFicLnthCharge', 'ExtraCharge', 'Fluctuation', 'Commission', 'Misc',
  'Testing', 'MOUTOD', 'SplDisc', 'JC',
];

// Non-cost fields that should also copy from previous line / template
const EXTRA_INHERITABLE = ['modeOfDispatch'];

const MODE_OF_DISPATCH_OPTIONS = [
  'By Truck in U-Bend shape',
  'By Trailer Straight length shape',
];

const COST_HEAD_LABELS: { [key: string]: string } = {
  TPWGST: 'T.P. w/o GST', Marketing: 'Marketing', FreightTrailer: 'Freight (Trailer)',
  FreightTruck: 'Freight (Truck)', Unloading: 'Unloading', OHD: 'OHD', IFC: 'IFC',
  WeighmentDiff: 'Weighment Diff.', CD: 'CD', SWECharge: 'SWE Charges', CRS: 'CRS',
  IncCharge: 'Incidental', ShortLnthCharge: 'Short Length', SpeciFicLnthCharge: 'Specific Length',
  ExtraCharge: 'Extra', Fluctuation: 'Fluctuation', Commission: 'Commission', Misc: 'Misc.',
  Testing: 'Testing', MOUTOD: 'MOU TOD', SplDisc: 'Spl. Discount', JC: 'JC',
};

const ALL_COST_HEADS = ['TPWGST', ...INHERITABLE_FIELDS];

@Component({
  selector: 'app-quotation-detail-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatButtonModule, MatIconModule,
    MatCheckboxModule, MatDividerModule, MatSlideToggleModule, MatTooltipModule,
    SearchFilterPipe,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Quotation Line Item</h2>
    <mat-dialog-content class="dialog-content">

      <!-- Item Info -->
      <div class="form-row-2">
        <mat-form-field appearance="outline">
          <mat-label>Item *</mat-label>
          <mat-select [(ngModel)]="row.itemName" (openedChange)="search.item = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search item..." [(ngModel)]="search.item" (keydown)="$event.stopPropagation()">
            </div>
            @for (n of itemNames | searchFilter:search.item:'itemName'; track n.itemId) {
              <mat-option [value]="n.itemName" (click)="onItemNameSelect(n)">{{ n.itemName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Grade *</mat-label>
          <mat-select [(ngModel)]="row.itemGradeName" (openedChange)="search.grade = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.grade" (keydown)="$event.stopPropagation()">
            </div>
            @for (g of itemGrades | searchFilter:search.grade:'itemGradeName'; track g.itemGradeId) {
              <mat-option [value]="g.itemGradeName">{{ g.itemGradeName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      </div>

      <div class="form-row-3">
        <mat-form-field appearance="outline">
          <mat-label>Dia</mat-label>
          <mat-select [(ngModel)]="row.itemDia" (ngModelChange)="onDiaChange()" (openedChange)="search.dia = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.dia" (keydown)="$event.stopPropagation()">
            </div>
            @for (d of dias | searchFilter:search.dia:'diadescription'; track d.diaid) {
              <mat-option [value]="d.diadescription">{{ d.diadescription }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Length</mat-label>
          <mat-select [(ngModel)]="row.itemLength"
            (ngModelChange)="onLengthChange($event)"
            (openedChange)="search.length = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.length" (keydown)="$event.stopPropagation()">
            </div>
            @for (l of uniqueLengths | searchFilter:search.length:'itemLength'; track l.itemLength) {
              <mat-option [value]="l.itemLength">{{ l.itemLength }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Unit</mat-label>
          <mat-select [(ngModel)]="row.itemUnit">
            <mat-option value="MM">MM</mat-option>
            <mat-option value="MT">MT</mat-option>
            <mat-option value="KG">KG</mat-option>
            <mat-option value="NOS">NOS</mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <!-- Specified-length manual entry — appears when the user picks the
           "Specified Length" master entry, or when editing a row whose
           saved length isn't in the master list. -->
      <mat-form-field appearance="outline" *ngIf="specifiedLengthMode" class="full-width-row">
        <mat-label>Specify Length *</mat-label>
        <input matInput [(ngModel)]="customLength" placeholder="e.g. 7.85 MTRS" />
        <mat-hint>Type the actual length; you'll be asked whether to save it for reuse.</mat-hint>
      </mat-form-field>

      <div class="form-row-3">
        <mat-form-field appearance="outline">
          <mat-label>Quantity</mat-label>
          <input matInput type="number" [(ngModel)]="row.quantity" min="1" />
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Mode of Dispatch</mat-label>
          <mat-select [(ngModel)]="row.modeOfDispatch">
            @for (m of dispatchModes; track m) {
              <mat-option [value]="m">{{ m }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <div class="gst-toggle">
          <mat-slide-toggle [(ngModel)]="isCGST" (change)="onGstModeChange()" color="primary">
            {{ isCGST ? 'CGST+SGST' : 'IGST' }}
          </mat-slide-toggle>
        </div>
      </div>

      <mat-divider></mat-divider>

      <!-- Cost source controls -->
      <div class="cost-source-row">
        <mat-checkbox [(ngModel)]="usePreviousLine" (change)="onPreviousLineToggle()" color="primary"
          *ngIf="hasPreviousRow" matTooltip="Copies 21 cost fields from previous line item">
          Copy from previous line
        </mat-checkbox>

        <div class="template-controls">
          <mat-form-field appearance="outline" class="template-select">
            <mat-label>Load from template</mat-label>
            <mat-select [(ngModel)]="selectedTemplateId" (selectionChange)="onTemplateSelect()"
              (openedChange)="templateSearch = ''">
              <div class="select-search" (click)="$event.stopPropagation()">
                <input placeholder="Search..." [(ngModel)]="templateSearch" (keydown)="$event.stopPropagation()">
              </div>
              <mat-option [value]="null">-- None --</mat-option>
              @for (t of templates | searchFilter:templateSearch:'templateName'; track t.templateId) {
                <mat-option [value]="t.templateId">{{ t.templateName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <button mat-stroked-button (click)="saveAsTemplate()" matTooltip="Save current cost values as a reusable template"
            class="save-template-btn">
            <mat-icon>bookmark_add</mat-icon> Save as Template
          </button>
        </div>
      </div>

      <!-- Cost Heads Grid -->
      <h4 class="cost-title">Cost Heads (Rs/MT)</h4>
      <div class="cost-grid">
        @for (key of costHeadKeys; track key) {
          <mat-form-field appearance="outline" class="cost-field"
            [class.locked-field]="isCellLocked(key)"
            [matTooltip]="lockReason(key)" matTooltipPosition="above">
            <mat-label>{{ getLabel(key) }}</mat-label>
            <input matInput type="number" [(ngModel)]="row[key]"
              (ngModelChange)="recalculate()"
              [readonly]="isCellLocked(key)" />
            <mat-icon matSuffix *ngIf="isCellLocked(key)" class="lock-icon">lock</mat-icon>
          </mat-form-field>
        }
      </div>

      <mat-divider></mat-divider>

      <!-- Totals -->
      <div class="totals-row">
        <span><strong>Total (Rs/MT):</strong> {{ row.totRate | number:'1.2-2' }}</span>
        <span *ngIf="!isCGST"><strong>IGST:</strong> {{ row.IGST | number:'1.2-2' }}</span>
        <span *ngIf="isCGST"><strong>CGST:</strong> {{ row.CGST | number:'1.2-2' }}</span>
        <span *ngIf="isCGST"><strong>SGST:</strong> {{ row.SGST | number:'1.2-2' }}</span>
        <span><strong>Amount:</strong> {{ row.totAmount | number:'1.2-2' }}</span>
      </div>

    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="saving || !row.itemGradeName">
        {{ saving ? 'Saving...' : (isEdit ? 'Update' : 'Add') }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-content { min-width: 700px; max-height: 75vh; }
    .form-row-2 {
      display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px;
      mat-form-field { width: 100%; }
    }
    .form-row-3 {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0 12px;
      mat-form-field { width: 100%; }
    }
    .gst-toggle { display: flex; align-items: center; padding-top: 12px; }
    .cost-source-row {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; padding: 10px 0; flex-wrap: wrap;
    }
    .template-controls { display: flex; align-items: center; gap: 8px; }
    .template-select { width: 240px; }
    .save-template-btn { height: 40px; white-space: nowrap; font-size: 13px; }
    .cost-title { margin: 6px 0; font-size: 14px; font-weight: 600; }
    .cost-grid {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 0 10px;
      mat-form-field { width: 100%; }
    }
    .cost-field ::ng-deep .mat-mdc-form-field-infix { padding-top: 8px !important; padding-bottom: 8px !important; }
    .cost-field.locked-field ::ng-deep .mat-mdc-text-field-wrapper {
      background: repeating-linear-gradient(
        135deg,
        rgba(0,0,0,0.04),
        rgba(0,0,0,0.04) 4px,
        transparent 4px,
        transparent 8px
      );
    }
    .cost-field.locked-field ::ng-deep input { color: rgba(0,0,0,0.45); font-style: italic; }
    .lock-icon { font-size: 16px; width: 16px; height: 16px; color: rgba(0,0,0,0.45); }
    .totals-row {
      display: flex; gap: 24px; padding: 12px 0; font-size: 14px; flex-wrap: wrap;
    }
    mat-divider { margin: 8px 0; }
    .select-search {
      padding: 8px 16px 4px; position: sticky; top: 0;
      background: var(--mat-sys-surface, #fff); z-index: 1;
    }
    .select-search input {
      width: 100%; padding: 6px 8px; border: 1px solid #ccc;
      border-radius: 4px; font-size: 14px; outline: none;
    }
  `],
})
export class QuotationDetailDialogComponent implements OnInit {
  isEdit: boolean;
  saving = false;
  row: any;
  isCGST = false;
  search = { item: '', grade: '', dia: '', length: '' };
  templateSearch = '';

  // Copy from previous line
  usePreviousLine = false;
  hasPreviousRow = false;
  private backupValues: { [key: string]: number } = {};

  // Templates
  templates: any[] = [];
  selectedTemplateId: number | null = null;

  costHeadKeys = ALL_COST_HEADS;
  dispatchModes = MODE_OF_DISPATCH_OPTIONS;
  itemNames: any[] = [];
  itemGrades: any[] = [];
  dias: any[] = [];
  lengths: any[] = [];
  // De-duplicated by itemLength so the dropdown shows every distinct
  // option once (the master is itemId-keyed and routinely repeats).
  uniqueLengths: any[] = [];

  // Specified-length combobox state (mirrors the enquiry-detail-dialog).
  specifiedLengthMode = false;
  customLength = '';

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private dialogRef: MatDialogRef<QuotationDetailDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: {
      quotId: number;
      detail: any | null;
      previousRow: any | null;
      isForDeliveryTerm?: boolean;
      deliveryModeName?: string;
      /** 'quotation' (default) drives the QuotDetails endpoints.
       *  'po' drives the PO Working Sheet endpoints — same dialog,
       *  same fields, different URL base. */
      mode?: 'quotation' | 'po';
    },
  ) {
    this.isEdit = !!data.detail?.quotDtlId;
    this.hasPreviousRow = !!data.previousRow;
    this.isForDeliveryTerm = !!data.isForDeliveryTerm;
    this.deliveryModeName = (data.deliveryModeName || '').trim();

    if (data.detail) {
      this.row = { ...data.detail };
    } else {
      this.row = {
        quotId: data.quotId,
        itemName: '', itemGradeName: '', itemDia: '', itemLength: '',
        itemUnit: 'MT', quantity: 1, gstMode: 'IGST',
        modeOfDispatch: null,
        TPWGST: 0, Marketing: 0, FreightTrailer: 0, FreightTruck: 0,
        Unloading: 0, OHD: 0, IFC: 0, WeighmentDiff: 0, CD: 0,
        SWECharge: 0, CRS: 0, IncCharge: 0, ShortLnthCharge: 0,
        SpeciFicLnthCharge: 0, ExtraCharge: 0, Fluctuation: 0,
        Commission: 0, Misc: 0, Testing: 0, MOUTOD: 0, SplDisc: 0, JC: 0,
        totRate: 0, IGST: 0, CGST: 0, SGST: 0, totAmount: 0,
      };
    }
    this.isCGST = this.row.gstMode === 'CGST_SGST';
    // Force-zero any freight columns the term/mode rules currently lock,
    // so the dialog never opens with a stale value the user can't edit.
    this.zeroLockedFreight();
    // Auto-pick the dispatch mode that matches the selected Delivery Mode
    // (Trailer / Truck). "No Mode" or unrecognised values are left blank so
    // the user can pick. Existing saved values are preserved on edit.
    this.autoFillDispatch();
    // Take backup of current inheritable values AFTER zeroing so a "Copy
    // from previous line" + restore round-trip respects the lock state.
    this.snapshotBackup();
  }

  private autoFillDispatch(): void {
    if (this.row.modeOfDispatch) return;
    const mode = (this.deliveryModeName || '').trim();
    if (!mode) return;
    if (QuotationDetailDialogComponent.TRAILER_RE.test(mode)) {
      this.row.modeOfDispatch = 'By Trailer Straight length shape';
    } else if (QuotationDetailDialogComponent.TRUCK_RE.test(mode)) {
      this.row.modeOfDispatch = 'By Truck in U-Bend shape';
    }
  }

  // ---- Freight lock (mirrors quotation-details.component) ----

  isForDeliveryTerm = false;
  deliveryModeName = '';
  // Tolerant matchers — same patterns the parent form-level validator
  // uses. Catch misspellings ("Trailor"), short forms ("Trk"), and
  // synonyms ("Lorry") so the lock follows whatever string is in the
  // master, not a single literal spelling.
  private static readonly TRAILER_RE = /trail|trial/i;
  private static readonly TRUCK_RE = /truck|trk|lorr/i;

  isCellLocked(key: string): boolean {
    if (key !== 'FreightTrailer' && key !== 'FreightTruck') return false;
    if (!this.isForDeliveryTerm) return true;
    const mode = (this.deliveryModeName || '').trim();
    if (!mode) return true;
    const isTrailer = QuotationDetailDialogComponent.TRAILER_RE.test(mode);
    const isTruck = QuotationDetailDialogComponent.TRUCK_RE.test(mode);
    if (key === 'FreightTrailer') return !isTrailer;
    if (key === 'FreightTruck') return !isTruck;
    return false;
  }

  lockReason(key: string): string {
    if (!this.isCellLocked(key)) return '';
    if (!this.isForDeliveryTerm) return 'Locked — delivery term is not FOR';
    const mode = (this.deliveryModeName || '').trim();
    if (!mode) return 'Locked — pick a Delivery Mode first';
    return `Locked — delivery mode is ${mode}`;
  }

  private zeroLockedFreight(): void {
    if (this.isCellLocked('FreightTrailer')) this.row.FreightTrailer = 0;
    if (this.isCellLocked('FreightTruck')) this.row.FreightTruck = 0;
  }

  ngOnInit(): void {
    this.api.get<any[]>('/masters/item-names').subscribe({
      next: d => {
        this.itemNames = d;
        // Default item name to "TMT Bar" for new items
        if (!this.isEdit && !this.row.itemName) {
          const def = d.find((n: any) => n.itemName?.toLowerCase().includes('tmt bar'));
          if (def) {
            this.row.itemName = def.itemName;
            this.row.itemid = def.itemId;
          }
        }
      },
    });
    this.api.get<any[]>('/masters/item-grades').subscribe({
      next: d => {
        this.itemGrades = d;
        // Default grade to whichever master row contains "550D"
        // (e.g. "550D", "Fe550D", "550D Plus") for net-new lines only.
        // Imported lines (from-enquiry) bypass this dialog so their
        // grade is preserved as-quoted.
        if (!this.isEdit && !this.row.itemGradeName) {
          const def = d.find((g: any) => (g.itemGradeName || '').toUpperCase().includes('550D'));
          if (def) this.row.itemGradeName = def.itemGradeName;
        }
      },
    });
    this.api.get<any[]>('/masters/dia-masters').subscribe({ next: d => this.dias = d });
    this.api.get<any[]>('/masters/item-lengths').subscribe({
      next: d => {
        this.lengths = d;
        const seen = new Set<string>();
        this.uniqueLengths = (d || []).filter((l: any) => {
          const k = (l.itemLength || '').trim();
          if (!k || seen.has(k)) return false;
          seen.add(k);
          return true;
        });
        // Default length to "12 MTRS" for new items
        if (!this.isEdit && !this.row.itemLength) {
          const def = d.find((l: any) => l.itemLength === '12 MTRS' || l.itemLength === '12 Mtrs' || l.itemLength === '12MTRS');
          if (def) this.row.itemLength = def.itemLength;
        }
        this.detectSpecifiedLengthOnEdit();
      },
    });
    this.api.get<any[]>('/cost-templates').subscribe({ next: d => this.templates = d });
  }

  getLabel(key: string): string { return COST_HEAD_LABELS[key] || key; }

  onItemNameSelect(item: any): void {
    this.row.itemid = item.itemId;
    this.row.itemName = item.itemName;
    // Auto-select grade from item's grade if available
    if (item.itemGradeId) {
      const grade = this.itemGrades.find(g => g.itemGradeId === item.itemGradeId);
      if (grade) this.row.itemGradeName = grade.itemGradeName;
    }
  }

  // --- Snapshot / Restore ---

  private snapshotBackup(): void {
    for (const key of INHERITABLE_FIELDS) {
      this.backupValues[key] = this.row[key] ?? 0;
    }
    for (const key of EXTRA_INHERITABLE) {
      this.backupValues[key] = this.row[key] ?? null;
    }
  }

  private applySource(source: any): void {
    for (const key of INHERITABLE_FIELDS) {
      this.row[key] = source[key] ?? 0;
    }
    for (const key of EXTRA_INHERITABLE) {
      this.row[key] = source[key] ?? null;
    }
    // Re-apply the freight lock so a copied value never bypasses the rule.
    this.zeroLockedFreight();
    this.recalculate();
  }

  private restoreBackup(): void {
    for (const key of INHERITABLE_FIELDS) {
      this.row[key] = this.backupValues[key] ?? 0;
    }
    for (const key of EXTRA_INHERITABLE) {
      this.row[key] = this.backupValues[key] ?? null;
    }
    this.recalculate();
  }

  // --- Copy from previous line ---

  onPreviousLineToggle(): void {
    if (this.usePreviousLine && this.data.previousRow) {
      // Backup is already taken once at dialog open — don't re-snapshot
      this.selectedTemplateId = null;
      this.applySource(this.data.previousRow);
    } else {
      this.restoreBackup();
    }
  }

  // --- Templates ---

  onTemplateSelect(): void {
    if (!this.selectedTemplateId) return;
    const t = this.templates.find(x => x.templateId === this.selectedTemplateId);
    if (t) {
      this.usePreviousLine = false;
      this.applySource(t);
    }
  }

  saveAsTemplate(): void {
    const name = prompt('Enter template name:');
    if (!name?.trim()) return;
    const payload: any = { templateName: name.trim() };
    for (const key of INHERITABLE_FIELDS) {
      payload[key] = this.row[key] ?? 0;
    }
    this.api.post('/cost-templates', payload).subscribe({
      next: (created: any) => {
        this.templates.push(created);
        this.notify.success('Template saved');
      },
      error: () => this.notify.error('Failed to save template'),
    });
  }

  // --- Item / GST ---

  onDiaChange(): void {
    if (this.row.itemDia) {
      this.api.get<any>(`/quotations/tp-cost/${this.row.itemDia}`).subscribe({
        next: (res) => {
          if (res?.tpcost != null) {
            this.row.TPWGST = res.tpcost;
            this.recalculate();
          }
        },
      });
    }
  }

  onGstModeChange(): void {
    this.row.gstMode = this.isCGST ? 'CGST_SGST' : 'IGST';
    this.recalculate();
  }

  recalculate(): void {
    let sum = 0;
    for (const key of ALL_COST_HEADS) sum += (Number(this.row[key]) || 0);
    this.row.totRate = sum;
    const gstRate = 0.18;
    if (this.row.gstMode === 'CGST_SGST') {
      this.row.IGST = 0;
      this.row.CGST = +(sum * gstRate / 2).toFixed(2);
      this.row.SGST = +(sum * gstRate / 2).toFixed(2);
    } else {
      this.row.IGST = +(sum * gstRate).toFixed(2);
      this.row.CGST = 0;
      this.row.SGST = 0;
    }
    this.row.totAmount = +(sum + (this.row.IGST || 0) + (this.row.CGST || 0) + (this.row.SGST || 0)).toFixed(2);
  }

  // --- Specified Length combobox ---

  /** Activates manual entry mode when the row's existing length isn't in
   *  the master list (custom value carried over from a prior save). */
  private detectSpecifiedLengthOnEdit(): void {
    if (!this.isEdit || !this.row.itemLength) return;
    const v = (this.row.itemLength + '').trim();
    if (/specif/i.test(v)) {
      this.specifiedLengthMode = true;
      this.customLength = '';
      return;
    }
    const inMaster = this.uniqueLengths.some(
      (l: any) => (l.itemLength || '').trim().toLowerCase() === v.toLowerCase(),
    );
    if (!inMaster) {
      this.specifiedLengthMode = true;
      this.customLength = v;
      const specified = this.uniqueLengths.find((l: any) => /specif/i.test(l.itemLength));
      if (specified) this.row.itemLength = specified.itemLength;
    }
  }

  onLengthChange(value: string): void {
    if (!value) {
      this.specifiedLengthMode = false;
      this.customLength = '';
      return;
    }
    this.specifiedLengthMode = /specif/i.test(value);
    if (!this.specifiedLengthMode) this.customLength = '';
  }

  // --- Save ---

  save(): void {
    if (!this.row.itemGradeName) { this.notify.error('Item Grade is required'); return; }

    // Specified-length flow: substitute the typed value before sending.
    let typedSpecific: string | null = null;
    if (this.specifiedLengthMode) {
      const typed = (this.customLength || '').trim();
      if (!typed) {
        this.notify.error('Please type the specific length value.');
        return;
      }
      this.row.itemLength = typed;
      typedSpecific = typed;
    }

    // Zero locked freight values one last time so a stale entry can't slip
    // through (e.g. user edited then term/mode shifted while dialog was open).
    this.zeroLockedFreight();
    this.recalculate();
    this.saving = true;
    const payload: any = {};
    for (const key of ['itemid', 'itemName', 'itemGradeName', 'itemDia', 'itemLength', 'itemUnit', 'quantity',
      'gstMode', 'IGST', 'CGST', 'SGST', 'totRate', 'totAmount', 'modeOfDispatch', ...ALL_COST_HEADS]) {
      payload[key] = this.row[key] ?? null;
    }
    payload.quantity = payload.quantity || 1;
    payload.basicRate = payload.totRate;

    const base = this.data.mode === 'po'
      ? `/quotations/${this.data.quotId}/purchase-order/working-sheet`
      : `/quotations/${this.data.quotId}/details`;
    const req$ = this.isEdit
      ? this.api.put(`${base}/${this.row.quotDtlId}`, payload)
      : this.api.post(base, payload);

    req$.subscribe({
      next: () => {
        this.notify.success('Line item saved');
        this.maybePromptSaveLengthToMaster(typedSpecific);
      },
      error: () => { this.notify.error('Failed to save'); this.saving = false; },
    });
  }

  /** After a successful line-item save, prompt the user about adding the
   *  typed length to the Item Lengths master so it shows up in the
   *  dropdown next time. Skipped when no Item Name is selected (master
   *  needs the itemId FK) or when the value already exists for that item. */
  private maybePromptSaveLengthToMaster(typed: string | null): void {
    const close = () => this.dialogRef.close(true);
    if (!typed) return close();
    const exists = this.lengths.some(
      (l: any) => (l.itemLength || '').trim().toLowerCase() === typed.toLowerCase()
        && l.itemId === this.row.itemid,
    );
    if (exists || !this.row.itemid) return close();

    const ref = this.dialog.open(ConfirmDialogComponent, {
      width: '420px',
      data: {
        title: 'Save length for reuse?',
        message: `Add "${typed}" to the Item Lengths master so you can pick it next time?`,
        confirmText: 'Save to Master',
        cancelText: 'Skip',
        confirmColor: 'primary',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return close();
      this.api.post('/masters/item-lengths', {
        itemId: this.row.itemid,
        itemLength: typed,
      }).subscribe({
        next: () => this.notify.success(`"${typed}" added to Item Lengths master.`),
        error: () => this.notify.error('Saved the line item, but failed to add to master.'),
        complete: close,
      });
    });
  }
}
