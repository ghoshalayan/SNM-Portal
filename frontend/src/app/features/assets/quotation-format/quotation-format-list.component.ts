import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, MatPaginator, PageEvent } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { QuotationFormatDialogComponent } from './quotation-format-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

interface FormatListItem {
  qfId: number;
  formatName: string;
  isCurrent: boolean;
  createdon: string | null;
}

@Component({
  selector: 'app-quotation-format-list',
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
    MatTooltipModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>Quotation Formats</mat-card-title>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="search-field">
            <mat-label>Search</mat-label>
            <input matInput (keyup)="applyFilter($event)" placeholder="Search formats..." />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon> Add Format
          </button>
        </div>
      </mat-card-header>
      <mat-card-content>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="4"></app-skeleton-loader> }

        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="formatName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Format Name</th>
            <td mat-cell *matCellDef="let row">{{ row.formatName }}</td>
          </ng-container>

          <ng-container matColumnDef="isCurrent">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Status</th>
            <td mat-cell *matCellDef="let row">
              @if (row.isCurrent) {
                <mat-chip-set><mat-chip color="primary" highlighted>Current</mat-chip></mat-chip-set>
              }
            </td>
          </ng-container>

          <ng-container matColumnDef="createdon">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Created</th>
            <td mat-cell *matCellDef="let row">{{ row.createdon | date:'dd-MM-yyyy' }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button mat-icon-button color="primary" (click)="openDialog(row)" matTooltip="Edit">
                <mat-icon>edit</mat-icon>
              </button>
              @if (!row.isCurrent) {
                <button mat-icon-button color="accent" (click)="setCurrent(row)" matTooltip="Set as Current">
                  <mat-icon>check_circle</mat-icon>
                </button>
              }
              <button mat-icon-button color="warn" (click)="deleteItem(row)" matTooltip="Delete">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data" [attr.colspan]="displayedColumns.length">No formats found.</td>
          </tr>
        </table>

        <mat-paginator
          [pageSizeOptions]="[10, 25, 50]"
          [pageSize]="pageSize"
          [length]="totalRecords"
          [pageIndex]="currentPage - 1"
          showFirstLastButtons
          (page)="onPageChange($event)"
          [hidden]="loading">
        </mat-paginator>
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
export class QuotationFormatListComponent implements OnInit {
  dataSource = new MatTableDataSource<FormatListItem>([]);
  displayedColumns = ['formatName', 'isCurrent', 'createdon', 'actions'];
  loading = true;

  currentPage = 1;
  pageSize = 25;
  totalRecords = 0;

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

  load() {
    this.loading = true;
    const start = Date.now();
    const params: any = { page: this.currentPage, page_size: this.pageSize };
    this.api.get<any>('/quotation-formats', params).subscribe({
      next: (res) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => {
          this.dataSource.data = res.items;
          this.totalRecords = res.total;
          this.loading = false;
        }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load formats'); this.loading = false; }, remaining);
      },
    });
  }

  onPageChange(event: PageEvent) {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.load();
  }

  applyFilter(event: Event) {
    this.dataSource.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
  }

  openDialog(row?: FormatListItem) {
    const ref = this.dialog.open(QuotationFormatDialogComponent, {
      width: '100vw',
      maxWidth: '100vw',
      height: '100vh',
      panelClass: 'fullscreen-dialog',
      data: row ? { qfId: row.qfId } : null,
    });
    ref.afterClosed().subscribe((saved) => { if (saved) this.load(); });
  }

  setCurrent(row: FormatListItem) {
    this.api.patch(`/quotation-formats/${row.qfId}/set-current`, {}).subscribe({
      next: () => { this.notify.success(`"${row.formatName}" set as current`); this.load(); },
      error: () => this.notify.error('Failed to set current format'),
    });
  }

  deleteItem(row: FormatListItem) {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { message: `Delete format "${row.formatName}"?` },
    });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/quotation-formats/${row.qfId}`).subscribe({
          next: () => { this.notify.success('Format deleted'); this.load(); },
          error: () => this.notify.error('Delete failed'),
        });
      }
    });
  }
}
