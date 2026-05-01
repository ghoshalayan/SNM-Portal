import { Component, OnInit, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { RawMaterialCostDialogComponent } from './raw-material-cost-dialog.component';
import { RawMaterialCostLogsDialogComponent } from './raw-material-cost-logs-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

@Component({
  selector: 'app-raw-material-cost-list',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatPaginatorModule,
    MatSortModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>Raw Material Costs</mat-card-title>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="search-field">
            <mat-label>Search</mat-label>
            <input matInput (keyup)="applyFilter($event)" placeholder="Search raw material costs..." />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon> Add Raw Material Cost
          </button>
        </div>
      </mat-card-header>
      <mat-card-content>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="9"></app-skeleton-loader> }
        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="rawMaterialCostId">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>#</th>
            <td mat-cell *matCellDef="let row">{{ row.rawMaterialCostId }}</td>
          </ng-container>
          <ng-container matColumnDef="dia">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Dia</th>
            <td mat-cell *matCellDef="let row">
              {{ row.dia }}
              <span *ngIf="row.isBasePrice" class="base-badge">BASE</span>
            </td>
          </ng-container>
          <ng-container matColumnDef="tpcost">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>TP Cost</th>
            <td mat-cell *matCellDef="let row" [class.base-cost]="row.isBasePrice">
              {{ row.tpcost | number:'1.2-2' }}
            </td>
          </ng-container>
          <ng-container matColumnDef="diffFromBase">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Diff from Base</th>
            <td mat-cell *matCellDef="let row">
              {{ row.isBasePrice ? '—' : (row.diffFromBase | number:'1.2-2') }}
            </td>
          </ng-container>
          <ng-container matColumnDef="effectedFrom">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Effected From</th>
            <td mat-cell *matCellDef="let row">{{ row.effectedFrom | date:'dd-MM-yyyy' }}</td>
          </ng-container>
          <ng-container matColumnDef="createdbyName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Created By</th>
            <td mat-cell *matCellDef="let row">{{ row.createdbyName }}</td>
          </ng-container>
          <ng-container matColumnDef="createdon">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Created On</th>
            <td mat-cell *matCellDef="let row">{{ row.createdon | date:'dd-MM-yyyy HH:mm' }}</td>
          </ng-container>
          <ng-container matColumnDef="lastupdatebyName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Updated By</th>
            <td mat-cell *matCellDef="let row">{{ row.lastupdatebyName }}</td>
          </ng-container>
          <ng-container matColumnDef="lastupdateon">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Updated On</th>
            <td mat-cell *matCellDef="let row">{{ row.lastupdateon | date:'dd-MM-yyyy HH:mm' }}</td>
          </ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button mat-icon-button color="primary" (click)="openDialog(row)" title="Edit">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button (click)="openLogs(row)" title="Update Logs" class="logs-btn">
                <mat-icon>history</mat-icon>
              </button>
              <button mat-icon-button color="warn" (click)="deleteItem(row)" title="Delete">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data" [attr.colspan]="displayedColumns.length">No records found.</td>
          </tr>
        </table>
        <mat-paginator [pageSizeOptions]="[10, 25, 50]" [pageSize]="10" showFirstLastButtons [hidden]="loading"></mat-paginator>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding-bottom: 16px; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .search-field { width: 250px; }
    .full-width { width: 100%; }
    .no-data { padding: 24px; text-align: center; color: #888; }
    .logs-btn { color: #6a1b9a; }
    .base-badge {
      display: inline-block; font-size: 10px; font-weight: 700;
      padding: 1px 6px; border-radius: 3px; margin-left: 6px;
      background: #e3f2fd; color: #1565c0; vertical-align: middle;
    }
    .base-cost { font-weight: 700; color: #1565c0; }
  `],
})
export class RawMaterialCostListComponent implements OnInit, AfterViewInit {
  dataSource = new MatTableDataSource<any>([]);
  displayedColumns = ['rawMaterialCostId', 'dia', 'tpcost', 'diffFromBase', 'effectedFrom', 'createdbyName', 'createdon', 'lastupdatebyName', 'lastupdateon', 'actions'];
  loading = true;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnInit() {
    this.load();
  }

  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  load() {
    this.loading = true;
    const start = Date.now();
    this.api.get('/masters/raw-material-costs').subscribe({
      next: (res: any) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.dataSource.data = res || []; this.loading = false; }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load raw material costs'); this.loading = false; }, remaining);
      },
    });
  }

  applyFilter(event: Event) {
    this.dataSource.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
  }

  openDialog(row?: any) {
    const ref = this.dialog.open(RawMaterialCostDialogComponent, {
      width: '480px',
      data: row || null,
    });
    ref.afterClosed().subscribe((saved) => { if (saved) this.load(); });
  }

  openLogs(row: any) {
    this.dialog.open(RawMaterialCostLogsDialogComponent, {
      width: '1100px',
      maxWidth: '95vw',
      data: {
        rawMaterialCostId: row.rawMaterialCostId,
        dia: row.dia,
        currentCost: row.tpcost,
      },
    });
  }

  deleteItem(row: any) {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { message: `Delete raw material cost (Dia: ${row.dia})?` },
    });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/masters/raw-material-costs/${row.rawMaterialCostId}`).subscribe({
          next: () => { this.notify.success('Deleted successfully'); this.load(); },
          error: () => this.notify.error('Delete failed'),
        });
      }
    });
  }
}
