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
import { ItemGradeDialogComponent } from './item-grade-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

@Component({
  selector: 'app-item-grade-list',
  standalone: true,
  imports: [
    CommonModule, MatTableModule, MatButtonModule, MatIconModule,
    MatDialogModule, MatCardModule, MatFormFieldModule, MatInputModule,
    MatPaginatorModule, MatSortModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>Item Grades</mat-card-title>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="search-field">
            <mat-label>Search</mat-label>
            <input matInput (keyup)="applyFilter($event)" placeholder="Search item grades..." />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon> Add Item Grade
          </button>
        </div>
      </mat-card-header>
      <mat-card-content>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="3"></app-skeleton-loader> }
        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="itemGradeId">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>#</th>
            <td mat-cell *matCellDef="let row">{{ row.itemGradeId }}</td>
          </ng-container>
          <ng-container matColumnDef="itemGradeName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Item Grade Name</th>
            <td mat-cell *matCellDef="let row">{{ row.itemGradeName }}</td>
          </ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button mat-icon-button color="primary" (click)="openDialog(row)" title="Edit">
                <mat-icon>edit</mat-icon>
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
  `],
})
export class ItemGradeListComponent implements OnInit, AfterViewInit {
  dataSource = new MatTableDataSource<any>([]);
  displayedColumns = ['itemGradeId', 'itemGradeName', 'actions'];
  loading = true;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor(private api: ApiService, private notify: NotificationService, private dialog: MatDialog) {}

  ngOnInit() { this.load(); }

  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  load() {
    this.loading = true;
    const start = Date.now();
    this.api.get('/masters/item-grades').subscribe({
      next: (res: any) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.dataSource.data = res || []; this.loading = false; }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load item grades'); this.loading = false; }, remaining);
      },
    });
  }

  applyFilter(event: Event) {
    const value = (event.target as HTMLInputElement).value.trim().toLowerCase();
    this.dataSource.filter = value;
  }

  openDialog(row?: any) {
    const ref = this.dialog.open(ItemGradeDialogComponent, { width: '480px', data: row || null });
    ref.afterClosed().subscribe((saved) => { if (saved) this.load(); });
  }

  deleteItem(row: any) {
    const ref = this.dialog.open(ConfirmDialogComponent, { data: { message: `Delete item grade "${row.itemGradeName}"?` } });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/masters/item-grades/${row.itemGradeId}`).subscribe({
          next: () => { this.notify.success('Deleted successfully'); this.load(); },
          error: () => this.notify.error('Delete failed'),
        });
      }
    });
  }
}
