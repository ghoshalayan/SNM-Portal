import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { ApiService, PaginatedResponse } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';
import { ServerSearchSelectComponent } from '../../../shared/components/server-search-select/server-search-select.component';

export interface Quotation {
  quotId: number;
  quotNo: string;
  quotDate: string;
  customerName: string;
  subject: string;
  versionNo: number;
  status: string;
  customerId: number;
}


@Component({
  selector: 'app-quotation-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatCardModule,
    MatTooltipModule,
    MatChipsModule,
    MatDialogModule,
    MatProgressSpinnerModule,
    MatDatepickerModule,
    MatNativeDateModule,
    SkeletonLoaderComponent,
    ServerSearchSelectComponent,
  ],
  template: `
    <div class="quotation-list-container">
      <mat-card>
        <mat-card-header>
          <mat-card-title>Quotations</mat-card-title>
          <div class="header-actions">
            <button mat-raised-button color="primary" (click)="addQuotation()">
              <mat-icon>add</mat-icon> New Quotation
            </button>
          </div>
        </mat-card-header>

        <mat-card-content>
          <!-- Filters -->
          <div class="filters-row">
            <div class="filter-field">
              <app-server-search-select
                endpoint="/customers/search"
                label="Filter by Customer"
                placeholder="Search customer..."
                [(ngModel)]="selectedCustomerId"
                (selectionChange)="applyFilters()">
              </app-server-search-select>
            </div>

            <mat-form-field appearance="outline" class="filter-field filter-date">
              <mat-label>From Date</mat-label>
              <input matInput [matDatepicker]="fromPicker" [(ngModel)]="dateFrom"
                (dateChange)="applyFilters()">
              <mat-datepicker-toggle matSuffix [for]="fromPicker"></mat-datepicker-toggle>
              <mat-datepicker #fromPicker></mat-datepicker>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field filter-date">
              <mat-label>To Date</mat-label>
              <input matInput [matDatepicker]="toPicker" [(ngModel)]="dateTo"
                (dateChange)="applyFilters()">
              <mat-datepicker-toggle matSuffix [for]="toPicker"></mat-datepicker-toggle>
              <mat-datepicker #toPicker></mat-datepicker>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field filter-status">
              <mat-label>Status</mat-label>
              <mat-select [(ngModel)]="selectedStatus" (selectionChange)="applyFilters()">
                <mat-option [value]="null">All</mat-option>
                @for (s of statusOptions; track s) {
                  <mat-option [value]="s">{{ s }}</mat-option>
                }
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>Search</mat-label>
              <input matInput [(ngModel)]="searchText" (input)="applyFilters()" placeholder="Quot No, Subject..." />
              <mat-icon matSuffix>search</mat-icon>
            </mat-form-field>

            <button mat-stroked-button (click)="clearFilters()">
              <mat-icon>clear</mat-icon> Clear
            </button>
          </div>

          <!-- Loading Skeleton -->
          @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="7"></app-skeleton-loader> }

          <!-- Table -->
          <div class="table-wrapper" [hidden]="loading">
            <table mat-table [dataSource]="dataSource" matSort class="quotation-table">

              <ng-container matColumnDef="quotNo">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Quot No</th>
                <td mat-cell *matCellDef="let row">{{ row.quotNo }}</td>
              </ng-container>

              <ng-container matColumnDef="quotDate">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Date</th>
                <td mat-cell *matCellDef="let row">{{ row.quotDate | date:'dd-MM-yyyy' }}</td>
              </ng-container>

              <ng-container matColumnDef="customerName">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Customer</th>
                <td mat-cell *matCellDef="let row">{{ row.customerName }}</td>
              </ng-container>

              <ng-container matColumnDef="subject">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Subject</th>
                <td mat-cell *matCellDef="let row">{{ row.subject }}</td>
              </ng-container>

              <ng-container matColumnDef="versionNo">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Version</th>
                <td mat-cell *matCellDef="let row">
                  <mat-chip-set>
                    <mat-chip>v{{ row.versionNo }}</mat-chip>
                  </mat-chip-set>
                </td>
              </ng-container>

              <ng-container matColumnDef="status">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Status</th>
                <td mat-cell *matCellDef="let row">
                  <span class="status-badge" [ngClass]="getStatusClass(row.status)">
                    {{ row.status }}
                  </span>
                </td>
              </ng-container>

              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let row">
                  <button mat-icon-button color="primary" (click)="editQuotation(row)" matTooltip="Edit">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button color="accent" (click)="printQuotation(row)" matTooltip="Print">
                    <mat-icon>print</mat-icon>
                  </button>
                  <button mat-icon-button color="warn" (click)="deleteQuotation(row)" matTooltip="Delete"
                    [disabled]="row.status === 'Approved'">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns;" class="table-row"></tr>

              <tr class="mat-row no-data-row" *matNoDataRow>
                <td class="mat-cell" [attr.colspan]="displayedColumns.length">
                  No quotations found.
                </td>
              </tr>
            </table>

            <mat-paginator
              [pageSizeOptions]="[10, 25, 50, 100, 250, 500]"
              [pageSize]="pageSize"
              [length]="totalRecords"
              [pageIndex]="currentPage - 1"
              showFirstLastButtons
              (page)="onPageChange($event)"
            ></mat-paginator>
          </div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .quotation-list-container {
      padding: 24px;
    }

    mat-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .header-actions {
      margin-left: auto;
    }

    .filters-row {
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }

    .filter-field {
      min-width: 200px;
    }
    .filter-date { min-width: 160px; max-width: 180px; }
    .filter-status { min-width: 140px; max-width: 160px; }

    .spinner-container {
      display: flex;
      justify-content: center;
      padding: 48px;
    }

    .table-wrapper {
      overflow-x: auto;
    }

    .quotation-table {
      width: 100%;
    }

    .table-row:hover {
      background-color: #f5f5f5;
      cursor: pointer;
    }

    .no-data-row td {
      text-align: center;
      padding: 24px;
      color: #666;
    }

  `],
})
export class QuotationListComponent implements OnInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  displayedColumns: string[] = ['quotNo', 'quotDate', 'customerName', 'subject', 'versionNo', 'status', 'actions'];
  dataSource = new MatTableDataSource<Quotation>();
  selectedCustomerId: number | null = null;
  searchText = '';
  dateFrom: Date | null = null;
  dateTo: Date | null = null;
  selectedStatus: string | null = null;
  // Phase-4 collapsed status set. The lifecycle position past
  // Convert lives on per-stage entities (PO / viability / annexure
  // statuses), not on QuotSummary.status — so the filter dropdown
  // only needs the five canonical values.
  statusOptions = [
    'Draft', 'Approved', 'Converted', 'Reject', 'Revised',
  ];
  loading = false;

  // Server-side pagination state
  currentPage = 1;
  pageSize = 25;
  totalRecords = 0;

  constructor(
    private router: Router,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.loadQuotations();
  }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  loadQuotations(): void {
    this.loading = true;
    const start = Date.now();
    const params: Record<string, string> = {
      page: String(this.currentPage),
      pageSize: String(this.pageSize),
    };
    if (this.selectedCustomerId) {
      params['customerId'] = String(this.selectedCustomerId);
    }
    if (this.dateFrom) {
      params['dateFrom'] = this.formatDate(this.dateFrom);
    }
    if (this.dateTo) {
      params['dateTo'] = this.formatDate(this.dateTo);
    }
    if (this.selectedStatus) {
      params['status'] = this.selectedStatus;
    }
    if (this.searchText?.trim()) {
      params['search'] = this.searchText.trim();
    }

    this.apiService.get<PaginatedResponse<Quotation>>('/quotations', params).subscribe({
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
        setTimeout(() => { this.notificationService.error('Failed to load quotations.'); this.loading = false; }, remaining);
      },
    });
  }

  onPageChange(event: any): void {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadQuotations();
  }

  applyFilters(): void {
    this.currentPage = 1;
    this.loadQuotations();
  }

  clearFilters(): void {
    this.searchText = '';
    this.selectedCustomerId = null;
    this.dateFrom = null;
    this.dateTo = null;
    this.selectedStatus = null;
    this.currentPage = 1;
    this.loadQuotations();
  }

  private formatDate(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  addQuotation(): void {
    this.router.navigate(['/quotations/new']);
  }

  editQuotation(row: Quotation): void {
    this.router.navigate(['/quotations', row.quotId, 'edit']);
  }

  printQuotation(row: Quotation): void {
    this.router.navigate(['/quotations', row.quotId, 'print']);
  }

  deleteQuotation(row: Quotation): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete Quotation',
        message: `Are you sure you want to delete quotation "${row.quotNo}"? This action cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean) => {
      if (confirmed) {
        this.apiService.delete(`/quotations/${row.quotId}`).subscribe({
          next: () => {
            this.notificationService.success('Quotation deleted successfully.');
            this.loadQuotations();
          },
          error: () => this.notificationService.error('Failed to delete quotation.'),
        });
      }
    });
  }

  getStatusClass(status: string): string {
    const map: Record<string, string> = {
      Draft: 'status-draft',
      Approved: 'status-approved',
      Matured: 'status-matured',
      Reject: 'status-reject',
      Revised: 'status-revised',
      ViabilityGenerated: 'status-viability-generated',
      ViabilityApproved: 'status-viability-approved',
      AnnexureGenerated: 'status-annexure-generated',
      AnnexureApproved: 'status-annexure-approved',
    };
    return map[status] ?? 'status-draft';
  }
}
