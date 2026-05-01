import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-item-length-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
    MatIconModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Item Length</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Name</mat-label>
          <mat-select formControlName="itemId" panelClass="searchable-panel">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search items..."
                [value]="itemSearch"
                (input)="itemSearch = $any($event.target).value; filterItems()"
                (keydown)="$event.stopPropagation()">
            </div>
            @for (item of displayedItems; track item.itemId) {
              <mat-option [value]="item.itemId">{{ item.itemName }}</mat-option>
            }
          </mat-select>
          <mat-error *ngIf="form.get('itemId')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Length</mat-label>
          <input matInput formControlName="itemLength" placeholder="Enter item length" />
          <mat-error *ngIf="form.get('itemLength')?.hasError('required')">Required</mat-error>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid || saving">
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`.dialog-form { display: flex; flex-direction: column; gap: 12px; min-width: 360px; padding-top: 8px; } .full-width { width: 100%; }`],
})
export class ItemLengthDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  items: any[] = [];
  displayedItems: any[] = [];
  itemSearch = '';

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<ItemLengthDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    this.isEdit = !!this.data;
    this.form = this.fb.group({
      itemId: [this.data?.itemId || '', Validators.required],
      itemLength: [this.data?.itemLength || '', Validators.required],
    });
    this.api.get('/masters/item-names').subscribe({
      next: (res: any) => {
        this.items = res || [];
        this.displayedItems = [...this.items];
      },
      error: () => this.notify.error('Failed to load item names'),
    });
  }

  filterItems(): void {
    const term = this.itemSearch.toLowerCase();
    this.displayedItems = term
      ? this.items.filter(i => i.itemName.toLowerCase().includes(term))
      : [...this.items];
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/masters/item-lengths/${this.data.itemLengthId}`, payload)
      : this.api.post('/masters/item-lengths', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Item length ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
