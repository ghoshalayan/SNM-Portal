import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { EnquiryDetailDialogComponent } from './enquiry-detail-dialog.component';

export interface EnquiryDetail {
  enqdtlid?: number;
  enqid: number;
  itemid?: number;
  itemGradeName: string;
  itemDia: string;
  itemLength: string;
  itemUnit: string;
  quantity?: number;
  remarks?: string;
}

@Component({
  selector: 'app-enquiry-details',
  standalone: true,
  imports: [
    CommonModule, MatTableModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatTooltipModule, MatDialogModule,
  ],
  template: `
    <div class="section-header">
      <h3><mat-icon>list_alt</mat-icon> Line Items</h3>
      <button mat-raised-button color="accent" (click)="openDialog(null)" [disabled]="isLoading">
        <mat-icon>add</mat-icon> Add Line Item
      </button>
    </div>

    <div class="loading-row" *ngIf="isLoading">
      <mat-spinner diameter="36"></mat-spinner>
      <span>Loading...</span>
    </div>

    <div class="table-container" *ngIf="!isLoading">
      <table mat-table [dataSource]="dataSource" class="full-width">
        <ng-container matColumnDef="index">
          <th mat-header-cell *matHeaderCellDef>#</th>
          <td mat-cell *matCellDef="let row; let i = index">{{ i + 1 }}</td>
        </ng-container>
        <ng-container matColumnDef="itemGradeName">
          <th mat-header-cell *matHeaderCellDef>Grade</th>
          <td mat-cell *matCellDef="let row">{{ row.itemGradeName }}</td>
        </ng-container>
        <ng-container matColumnDef="itemDia">
          <th mat-header-cell *matHeaderCellDef>Dia</th>
          <td mat-cell *matCellDef="let row">{{ row.itemDia }}</td>
        </ng-container>
        <ng-container matColumnDef="itemLength">
          <th mat-header-cell *matHeaderCellDef>Length</th>
          <td mat-cell *matCellDef="let row">{{ row.itemLength }}</td>
        </ng-container>
        <ng-container matColumnDef="itemUnit">
          <th mat-header-cell *matHeaderCellDef>Unit</th>
          <td mat-cell *matCellDef="let row">{{ row.itemUnit }}</td>
        </ng-container>
        <ng-container matColumnDef="quantity">
          <th mat-header-cell *matHeaderCellDef>Qty</th>
          <td mat-cell *matCellDef="let row">{{ row.quantity }}</td>
        </ng-container>
        <ng-container matColumnDef="remarks">
          <th mat-header-cell *matHeaderCellDef>Remarks</th>
          <td mat-cell *matCellDef="let row" class="remarks-cell">{{ row.remarks }}</td>
        </ng-container>
        <ng-container matColumnDef="actions">
          <th mat-header-cell *matHeaderCellDef>Actions</th>
          <td mat-cell *matCellDef="let row; let i = index">
            <button mat-icon-button color="primary" matTooltip="Edit" (click)="openDialog(row)">
              <mat-icon>edit</mat-icon>
            </button>
            <button mat-icon-button color="warn" matTooltip="Delete" (click)="confirmDelete(row, i)">
              <mat-icon>delete</mat-icon>
            </button>
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="columns"></tr>
        <tr mat-row *matRowDef="let row; columns: columns"></tr>
        <tr class="mat-row" *matNoDataRow>
          <td class="mat-cell no-data" [attr.colspan]="columns.length">No line items.</td>
        </tr>
      </table>
    </div>

    <div class="summary" *ngIf="dataSource.data.length > 0">
      Total items: {{ dataSource.data.length }}
    </div>
  `,
  styles: [`
    .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .section-header h3 { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 15px; font-weight: 600; }
    .loading-row { display: flex; align-items: center; gap: 12px; padding: 24px; color: #9e9e9e; }
    .table-container { overflow-x: auto; }
    .full-width { width: 100%; }
    .remarks-cell { max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .no-data { text-align: center; padding: 24px; color: rgba(0,0,0,0.38); }
    .summary { text-align: right; padding: 8px 4px; font-size: 13px; color: #616161; }
  `],
})
export class EnquiryDetailsComponent implements OnInit, OnChanges {
  @Input() enqId!: number;

  columns = ['index', 'itemGradeName', 'itemDia', 'itemLength', 'itemUnit', 'quantity', 'remarks', 'actions'];
  dataSource = new MatTableDataSource<EnquiryDetail>([]);
  isLoading = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void { if (this.enqId) this.load(); }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['enqId'] && !changes['enqId'].firstChange && this.enqId) this.load();
  }

  load(): void {
    this.isLoading = true;
    this.api.get<EnquiryDetail[]>(`/enquiries/${this.enqId}/details`).subscribe({
      next: (data) => { this.dataSource.data = data; this.isLoading = false; },
      error: () => { this.notify.error('Failed to load line items'); this.isLoading = false; },
    });
  }

  openDialog(detail: EnquiryDetail | null): void {
    const ref = this.dialog.open(EnquiryDetailDialogComponent, {
      width: '960px',
      maxWidth: '95vw',
      data: { enqId: this.enqId, detail },
      disableClose: true,
    });
    ref.afterClosed().subscribe(result => { if (result) this.load(); });
  }

  confirmDelete(row: EnquiryDetail, index: number): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete Line Item', message: `Delete ${row.itemGradeName} Dia ${row.itemDia}?`, confirmText: 'Delete', cancelText: 'Cancel' },
    });
    ref.afterClosed().subscribe(confirmed => {
      if (confirmed && row.enqdtlid) {
        this.api.delete(`/enquiries/${this.enqId}/details/${row.enqdtlid}`).subscribe({
          next: () => { this.notify.success('Deleted'); this.load(); },
          error: () => this.notify.error('Failed to delete'),
        });
      }
    });
  }
}
