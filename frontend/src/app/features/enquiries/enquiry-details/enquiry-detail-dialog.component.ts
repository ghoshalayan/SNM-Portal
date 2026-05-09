import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { SearchFilterPipe } from '../../../shared/pipes/search-filter.pipe';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

interface ItemGrade { itemGradeId: number; itemGradeName: string; }
interface ItemName { itemId: number; itemGradeId: number; itemName: string; }
interface Dia { diaid: number; itemid: number; diadescription: string; }
interface ItemLength { itemLengthId: number; itemId: number; itemLength: string; }

@Component({
  selector: 'app-enquiry-detail-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatButtonModule, MatIconModule, SearchFilterPipe,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Line Item</h2>
    <mat-dialog-content class="dialog-content">
      <div class="form-grid">
        <mat-form-field appearance="outline">
          <mat-label>Item Grade *</mat-label>
          <mat-select [(ngModel)]="row.itemGradeId" (ngModelChange)="onGradeChange()"
            (openedChange)="search.grade = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.grade" (keydown)="$event.stopPropagation()">
            </div>
            @for (g of itemGrades | searchFilter:search.grade:'itemGradeName'; track g.itemGradeId) {
              <mat-option [value]="g.itemGradeId">{{ g.itemGradeName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Item Name</mat-label>
          <mat-select [(ngModel)]="row.itemid" (ngModelChange)="onItemChange()"
            (openedChange)="search.item = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.item" (keydown)="$event.stopPropagation()">
            </div>
            @for (n of filteredItemNames | searchFilter:search.item:'itemName'; track n.itemId) {
              <mat-option [value]="n.itemId">{{ n.itemName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Dia</mat-label>
          <mat-select [(ngModel)]="row.itemDia" (openedChange)="search.dia = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <input placeholder="Search..." [(ngModel)]="search.dia" (keydown)="$event.stopPropagation()">
            </div>
            @for (d of uniqueDias | searchFilter:search.dia:'diadescription'; track d.diadescription) {
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

        <!-- Manual entry that appears when "Specified Length" is picked, or
             when editing a row whose length isn't in the master list. -->
        <mat-form-field appearance="outline" *ngIf="specifiedLengthMode">
          <mat-label>Specify Length *</mat-label>
          <input matInput [(ngModel)]="customLength" placeholder="e.g. 7.85 MTRS" />
          <mat-hint>Type the actual length; you'll be asked whether to save it for reuse.</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Unit</mat-label>
          <mat-select [(ngModel)]="row.itemUnit">
            <mat-option value="MM">MM</mat-option>
            <mat-option value="CM">CM</mat-option>
            <mat-option value="M">M</mat-option>
            <mat-option value="KG">KG</mat-option>
            <mat-option value="MT">MT</mat-option>
            <mat-option value="NOS">NOS</mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Quantity</mat-label>
          <input matInput type="number" [(ngModel)]="row.quantity" min="1" />
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Remarks</mat-label>
        <textarea matInput [(ngModel)]="row.remarks" rows="2"></textarea>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="saving || !row.itemGradeId">
        {{ saving ? 'Saving...' : (isEdit ? 'Update' : 'Add') }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    /* Top padding gives Material's floating outline labels room to render
       above the field; without it the title's bottom edge slices them. */
    .dialog-content { padding-top: 12px !important; }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px 16px;
      min-width: 880px;
      mat-form-field { width: 100%; }
    }
    .full-width { width: 100%; }
    .select-search {
      padding: 8px 16px 4px;
      position: sticky; top: 0;
      background: var(--mat-sys-surface, #fff);
      z-index: 1;
    }
    .select-search input {
      width: 100%; padding: 6px 8px;
      border: 1px solid #ccc; border-radius: 4px;
      font-size: 14px; outline: none;
    }
  `],
})
export class EnquiryDetailDialogComponent implements OnInit {
  isEdit: boolean;
  saving = false;
  row: any;
  search = { grade: '', item: '', dia: '', length: '' };

  itemGrades: ItemGrade[] = [];
  allItemNames: ItemName[] = [];
  allDias: Dia[] = [];
  allLengths: ItemLength[] = [];
  filteredItemNames: ItemName[] = [];
  // Dia and Length masters are FK-linked to itemid, so the same value
  // (e.g. "16 mm") often repeats once per associated item. We render a
  // de-duplicated list so the dropdowns show every distinct option
  // independently of the chosen grade or item.
  uniqueDias: Dia[] = [];
  uniqueLengths: ItemLength[] = [];

  // "Specified Length" combobox state — when the user picks the special
  // master entry whose name matches /specif/i, a free-text input appears
  // and replaces the dropdown's value on save.
  specifiedLengthMode = false;
  customLength = '';

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private dialogRef: MatDialogRef<EnquiryDetailDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { enqId: number; detail: any | null },
  ) {
    this.isEdit = !!data.detail?.enqdtlid;
    this.row = data.detail ? { ...data.detail } : {
      enqid: data.enqId,
      itemGradeId: null, itemid: null,
      itemGradeName: '', itemDia: '', itemLength: '',
      itemUnit: 'MT', quantity: 1, remarks: '',
    };
  }

  ngOnInit(): void {
    this.api.get<ItemGrade[]>('/masters/item-grades').subscribe({
      next: d => {
        this.itemGrades = d;
        // Default grade to whichever master row contains "550D"
        // (e.g. "550D", "Fe550D", "550D Plus") for net-new enquiry
        // lines only — tolerant match so the default still picks up
        // when the master uses a prefixed naming convention.
        if (!this.isEdit && !this.row.itemGradeId) {
          const def = d.find(g => (g.itemGradeName || '').toUpperCase().includes('550D'));
          if (def) {
            this.row.itemGradeId = def.itemGradeId;
            this.row.itemGradeName = def.itemGradeName;
          }
        }
      },
    });
    this.api.get<ItemName[]>('/masters/item-names').subscribe({
      next: d => {
        this.allItemNames = d;
        this.filteredItemNames = d;
        if (this.row.itemid && !this.row.itemGradeId) {
          const item = d.find(n => n.itemId === this.row.itemid);
          if (item) this.row.itemGradeId = item.itemGradeId;
        }
        // Default item name to "TMT Bar" for new items (after grade is set)
        if (!this.isEdit && !this.row.itemid && this.row.itemGradeId) {
          const filtered = d.filter(n => n.itemGradeId === this.row.itemGradeId);
          this.filteredItemNames = filtered;
          const defItem = filtered.find(n => n.itemName.toLowerCase().includes('tmt bar'));
          if (defItem) {
            this.row.itemid = defItem.itemId;
            this.onItemChange();
          }
        }
      },
    });
    this.api.get<Dia[]>('/masters/dia-masters').subscribe({
      next: d => {
        this.allDias = d;
        this.uniqueDias = this.dedupe(d, x => x.diadescription);
      },
    });
    this.api.get<ItemLength[]>('/masters/item-lengths').subscribe({
      next: d => {
        this.allLengths = d;
        this.uniqueLengths = this.dedupe(d, x => x.itemLength);
        // Default length to "12 MTRS" for new items
        if (!this.isEdit && !this.row.itemLength) {
          const def = d.find(l => l.itemLength === '12 MTRS' || l.itemLength === '12 Mtrs' || l.itemLength === '12MTRS');
          if (def) this.row.itemLength = def.itemLength;
        }
        this.detectSpecifiedLengthOnEdit();
      },
    });
  }

  /** Reading an existing row whose itemLength isn't in the master means
   *  it was a custom value. Promote the dialog into specified-length mode
   *  with the typed value pre-filled so the user can see / adjust it. */
  private detectSpecifiedLengthOnEdit(): void {
    if (!this.isEdit || !this.row.itemLength) return;
    const v = this.row.itemLength.trim();
    if (/specif/i.test(v)) {
      this.specifiedLengthMode = true;
      this.customLength = '';
      return;
    }
    const inMaster = this.uniqueLengths.some(
      l => (l.itemLength || '').trim().toLowerCase() === v.toLowerCase(),
    );
    if (!inMaster) {
      // Show the literal master option as the dropdown value, but keep
      // the actual saved string as the manual entry the user can edit.
      this.specifiedLengthMode = true;
      this.customLength = v;
      const specified = this.uniqueLengths.find(l => /specif/i.test(l.itemLength));
      if (specified) this.row.itemLength = specified.itemLength;
    }
  }

  /** Triggered by the Length dropdown. When the user picks the special
   *  "Specified Length" master entry, expose the free-text input. Picking
   *  any other value reverts to a normal dropdown selection. */
  onLengthChange(value: string): void {
    if (!value) {
      this.specifiedLengthMode = false;
      this.customLength = '';
      return;
    }
    this.specifiedLengthMode = /specif/i.test(value);
    if (!this.specifiedLengthMode) this.customLength = '';
  }

  /** Keep the first occurrence of each key — masters duplicate on itemid FK. */
  private dedupe<T>(arr: T[], keyFn: (x: T) => string): T[] {
    const seen = new Set<string>();
    const out: T[] = [];
    for (const x of arr) {
      const k = (keyFn(x) || '').trim();
      if (!k || seen.has(k)) continue;
      seen.add(k);
      out.push(x);
    }
    return out;
  }

  onGradeChange(): void {
    const grade = this.itemGrades.find(g => g.itemGradeId === this.row.itemGradeId);
    this.row.itemGradeName = grade?.itemGradeName ?? '';
    this.row.itemid = null;
    // Item Name still narrows by grade (that's the natural model), but Dia
    // and Length stay independent — switching grade no longer empties them.
    this.filteredItemNames = this.allItemNames.filter(n => n.itemGradeId === this.row.itemGradeId);
  }

  onItemChange(): void {
    // Intentionally a no-op for Dia / Length — they're independent
    // dropdowns, not narrowed by Item Name.
  }

  save(): void {
    if (!this.row.itemGradeId) { this.notify.error('Item Grade is required'); return; }

    // Specified-length flow: replace the dropdown sentinel with the typed
    // value so what gets persisted is the actual length.
    let lengthToSave = this.row.itemLength || null;
    let typedSpecific: string | null = null;
    if (this.specifiedLengthMode) {
      const typed = (this.customLength || '').trim();
      if (!typed) {
        this.notify.error('Please type the specific length value.');
        return;
      }
      lengthToSave = typed;
      typedSpecific = typed;
    }

    this.saving = true;
    const payload = {
      itemid: this.row.itemid || null,
      itemGradeName: this.row.itemGradeName,
      itemDia: this.row.itemDia || null,
      itemLength: lengthToSave,
      itemUnit: this.row.itemUnit,
      quantity: this.row.quantity || 1,
      remarks: this.row.remarks || null,
    };

    const req$ = this.isEdit
      ? this.api.put(`/enquiries/${this.data.enqId}/details/${this.row.enqdtlid}`, payload)
      : this.api.post(`/enquiries/${this.data.enqId}/details`, payload);

    req$.subscribe({
      next: () => {
        this.notify.success('Line item saved');
        this.maybePromptSaveLengthToMaster(typedSpecific);
      },
      error: () => { this.notify.error('Failed to save'); this.saving = false; },
    });
  }

  /** After a successful line-item save, ask whether to promote the typed
   *  length into the Item Lengths master. Skipped when the value is
   *  already in the master, when no Item Name is selected (master record
   *  needs an itemId FK), or when the user wasn't in specified-length
   *  mode. Closes the dialog regardless of the user's answer. */
  private maybePromptSaveLengthToMaster(typed: string | null): void {
    const close = () => this.dialogRef.close(true);
    if (!typed) return close();
    const exists = this.allLengths.some(
      l => (l.itemLength || '').trim().toLowerCase() === typed.toLowerCase()
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
