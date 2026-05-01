import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-item-size-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Item Size</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Name</mat-label>
          <mat-select formControlName="itemId">
            <mat-option *ngFor="let item of items" [value]="item.itemId">{{ item.itemName }}</mat-option>
          </mat-select>
          <mat-error *ngIf="form.get('itemId')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Size</mat-label>
          <input matInput formControlName="itemSize" placeholder="Enter item size" />
          <mat-error *ngIf="form.get('itemSize')?.hasError('required')">Required</mat-error>
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
export class ItemSizeDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  items: any[] = [];

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<ItemSizeDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    this.isEdit = !!this.data;
    this.form = this.fb.group({
      itemId: [this.data?.itemId || '', Validators.required],
      itemSize: [this.data?.itemSize || '', Validators.required],
    });
    this.api.get('/masters/item-names').subscribe({
      next: (res: any) => this.items = res || [],
      error: () => this.notify.error('Failed to load item names'),
    });
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/masters/item-sizes/${this.data.itemSizeId}`, payload)
      : this.api.post('/masters/item-sizes', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Item size ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
