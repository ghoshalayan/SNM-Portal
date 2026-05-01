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
import { MatChipsModule } from '@angular/material/chips';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { FinancialYearDialogComponent } from './financial-year-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

interface FinancialYear {
  fyId: number;
  fyName: string;
  fyCode: string;
  isCurrent: boolean;
}

@Component({
  selector: 'app-financial-year-list',
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
    MatChipsModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>Financial Years</mat-card-title>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="search-field">
            <mat-label>Search</mat-label>
            <input matInput (keyup)="applyFilter($event)" placeholder="Search financial years..." />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon> Add Financial Year
          </button>
        </div>
      </mat-card-header>
      <mat-card-content>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="4"></app-skeleton-loader> }
        @if (!loading) {
        <div class="table-container">
          <table mat-table [dataSource]="dataSource" matSort class="full-width-table">
            <ng-container matColumnDef="fyName">
              <th mat-header-cell *matHeaderCellDef mat-sort-header>FY Name</th>
              <td mat-cell *matCellDef="let row">{{ row.fyName }}</td>
            </ng-container>
            <ng-container matColumnDef="fyCode">
              <th mat-header-cell *matHeaderCellDef mat-sort-header>FY Code</th>
              <td mat-cell *matCellDef="let row">{{ row.fyCode }}</td>
            </ng-container>
            <ng-container matColumnDef="isCurrent">
              <th mat-header-cell *matHeaderCellDef mat-sort-header>Current</th>
              <td mat-cell *matCellDef="let row">
                <mat-chip-set>
                  <mat-chip [highlighted]="row.isCurrent" [color]="row.isCurrent ? 'primary' : ''">
                    {{ row.isCurrent ? 'Yes' : 'No' }}
                  </mat-chip>
                </mat-chip-set>
              </td>
            </ng-container>
            <ng-container matColumnDef="actions">
              <th mat-header-cell *matHeaderCellDef>Actions</th>
              <td mat-cell *matCellDef="let row">
                <button mat-icon-button color="primary" (click)="openDialog(row)"><mat-icon>edit</mat-icon></button>
                <button mat-icon-button color="warn" (click)="delete(row)"><mat-icon>delete</mat-icon></button>
              </td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
            <tr class="mat-row" *matNoDataRow>
              <td class="mat-cell" [attr.colspan]="displayedColumns.length" style="text-align:center;padding:24px;color:rgba(0,0,0,0.54);">
                No financial years found.
              </td>
            </tr>
          </table>
        </div>
        <mat-paginator [pageSizeOptions]="[10, 25, 50]" [pageSize]="25" showFirstLastButtons></mat-paginator>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    mat-card-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .search-field { width: 260px; font-size: 14px; }
    .table-container { overflow-x: auto; }
    .full-width-table { width: 100%; }
  `],
})
export class FinancialYearListComponent implements OnInit, AfterViewInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  displayedColumns = ['fyName', 'fyCode', 'isCurrent', 'actions'];
  dataSource = new MatTableDataSource<FinancialYear>([]);
  loading = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnInit() { this.load(); }

  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  load() {
    this.loading = true;
    this.api.get<FinancialYear[]>('/masters/financial-years').subscribe({
      next: (data) => { this.dataSource.data = data; this.loading = false; },
      error: () => { this.notify.error('Failed to load financial years'); this.loading = false; },
    });
  }

  applyFilter(event: Event) {
    this.dataSource.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
  }

  openDialog(row?: FinancialYear) {
    const ref = this.dialog.open(FinancialYearDialogComponent, { data: row || null, width: '440px' });
    ref.afterClosed().subscribe((result) => { if (result) this.load(); });
  }

  delete(row: FinancialYear) {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete Financial Year', message: `Delete "${row.fyName}"?`, confirmText: 'Delete', cancelText: 'Cancel' },
    });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/masters/financial-years/${row.fyId}`).subscribe({
          next: () => { this.notify.success('Deleted'); this.load(); },
          error: () => this.notify.error('Delete failed'),
        });
      }
    });
  }
}
