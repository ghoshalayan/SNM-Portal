import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, FormGroup } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ApiService, PaginatedResponse } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';
import { ServerSearchSelectComponent } from '../../../shared/components/server-search-select/server-search-select.component';

export interface Enquiry {
  enqid: number;
  enqNo: string;
  enqDate: string;
  customerId: number;
  customerName: string;
  enqMode: string;
  status: string;
}

@Component({
  selector: 'app-enquiry-list',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatChipsModule,
    MatDialogModule,
    SkeletonLoaderComponent,
    ServerSearchSelectComponent,
  ],
  template: `
    <div class="enquiry-list-container">
      <mat-card class="header-card">
        <mat-card-header>
          <mat-card-title>Enquiry Management</mat-card-title>
          <mat-card-subtitle>Manage all customer enquiries</mat-card-subtitle>
        </mat-card-header>
        <mat-card-actions align="end">
          <button mat-raised-button color="primary" (click)="navigateToNew()">
            <mat-icon>add</mat-icon>
            New Enquiry
          </button>
        </mat-card-actions>
      </mat-card>

      <!-- Filters -->
      <mat-card class="filter-card">
        <mat-card-content>
          <form [formGroup]="filterForm" class="filter-form">
            <div class="filter-field">
              <app-server-search-select
                endpoint="/customers/search"
                label="Customer"
                placeholder="Search customer..."
                formControlName="customerId">
              </app-server-search-select>
            </div>

            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>From Date</mat-label>
              <input matInput [matDatepicker]="fromPicker" formControlName="fromDate" />
              <mat-datepicker-toggle matIconSuffix [for]="fromPicker"></mat-datepicker-toggle>
              <mat-datepicker #fromPicker></mat-datepicker>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>To Date</mat-label>
              <input matInput [matDatepicker]="toPicker" formControlName="toDate" />
              <mat-datepicker-toggle matIconSuffix [for]="toPicker"></mat-datepicker-toggle>
              <mat-datepicker #toPicker></mat-datepicker>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>Status</mat-label>
              <mat-select formControlName="status">
                <mat-option [value]="null">All Statuses</mat-option>
                @for (s of enqStatuses; track s.enqstatid) {
                  <mat-option [value]="s.enqStatus">{{ s.enqStatus }}</mat-option>
                }
              </mat-select>
            </mat-form-field>

            <div class="filter-actions">
              <button mat-stroked-button color="primary" (click)="applyFilters()">
                <mat-icon>search</mat-icon> Search
              </button>
              <button mat-stroked-button (click)="resetFilters()">
                <mat-icon>clear</mat-icon> Reset
              </button>
            </div>
          </form>
        </mat-card-content>
      </mat-card>

      <!-- Table -->
      <mat-card class="table-card">
        <mat-card-content>
          @if (isLoading) { <app-skeleton-loader type="table" [rows]="5" [columns]="6"></app-skeleton-loader> }

          <div class="table-container" [hidden]="isLoading">
            <table mat-table [dataSource]="dataSource" matSort class="enquiry-table full-width">

              <!-- Enq No Column -->
              <ng-container matColumnDef="enqNo">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Enq. No.</th>
                <td mat-cell *matCellDef="let row">
                  <strong>{{ row.enqNo }}</strong>
                </td>
              </ng-container>

              <!-- Enq Date Column -->
              <ng-container matColumnDef="enqDate">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Date</th>
                <td mat-cell *matCellDef="let row">{{ row.enqDate | date: 'dd-MM-yyyy' }}</td>
              </ng-container>

              <!-- Customer Name Column -->
              <ng-container matColumnDef="customerName">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Customer</th>
                <td mat-cell *matCellDef="let row">{{ row.customerName }}</td>
              </ng-container>

              <!-- Enq Mode Column -->
              <ng-container matColumnDef="enqMode">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Mode</th>
                <td mat-cell *matCellDef="let row">{{ row.enqMode }}</td>
              </ng-container>

              <!-- Status Column -->
              <ng-container matColumnDef="status">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Status</th>
                <td mat-cell *matCellDef="let row">
                  <mat-chip [class]="'status-chip status-' + (row.status || '').toLowerCase().replace(' ', '-')">
                    {{ row.status }}
                  </mat-chip>
                </td>
              </ng-container>

              <!-- Actions Column -->
              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let row">
                  <button mat-icon-button color="primary" (click)="navigateToEdit(row.enqid)"
                    matTooltip="Edit Enquiry">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button color="warn" (click)="confirmDelete(row)"
                    matTooltip="Delete Enquiry">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns; sticky: true"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns;"
                class="enquiry-row"></tr>

              <!-- No Data Row -->
              <tr class="mat-row no-data-row" *matNoDataRow>
                <td class="mat-cell" [attr.colspan]="displayedColumns.length">
                  <div class="no-data">
                    <mat-icon>inbox</mat-icon>
                    <p>No enquiries found</p>
                  </div>
                </td>
              </tr>
            </table>
          </div>

          <mat-paginator
            [pageSizeOptions]="[10, 25, 50, 100, 250, 500]"
            [pageSize]="pageSize"
            [length]="totalRecords"
            [pageIndex]="currentPage - 1"
            showFirstLastButtons
            (page)="onPageChange($event)"
            aria-label="Select page of enquiries">
          </mat-paginator>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .enquiry-list-container {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .header-card mat-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .filter-card .filter-form {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: flex-start;
    }

    .filter-field {
      flex: 1 1 200px;
      min-width: 160px;
    }

    .filter-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      padding-top: 4px;
    }

    .table-card {
      position: relative;
    }

    .loading-overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      display: flex;
      justify-content: center;
      align-items: center;
      background: rgba(255,255,255,0.7);
      z-index: 10;
    }

    .table-container {
      overflow-x: auto;
    }

    .table-container.loading {
      opacity: 0.5;
      pointer-events: none;
    }

    .enquiry-table {
      width: 100%;
    }

    .full-width {
      width: 100%;
    }

    .enquiry-row:hover {
      background: #f5f5f5;
      cursor: pointer;
    }

    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 32px;
      color: #9e9e9e;
    }

    .no-data mat-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
    }

    .no-data-row td {
      text-align: center;
    }
  `],
})
export class EnquiryListComponent implements OnInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  displayedColumns: string[] = ['enqNo', 'enqDate', 'customerName', 'enqMode', 'status', 'actions'];
  dataSource = new MatTableDataSource<Enquiry>([]);
  enqStatuses: { enqstatid: number; enqStatus: string }[] = [];
  isLoading = false;
  filterForm: FormGroup;

  // Server-side pagination state
  currentPage = 1;
  pageSize = 25;
  totalRecords = 0;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private dialog: MatDialog,
  ) {
    this.filterForm = this.fb.group({
      customerId: [null],
      fromDate: [null],
      toDate: [null],
      status: [null],
    });
  }

  ngOnInit(): void {
    this.loadEnqStatuses();
    this.loadEnquiries();
  }

  loadEnqStatuses(): void {
    this.apiService.get<{ enqstatid: number; enqStatus: string }[]>('/masters/enq-statuses').subscribe({
      next: (data) => this.enqStatuses = data,
    });
  }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  loadEnquiries(): void {
    this.isLoading = true;
    const start = Date.now();
    const filters = this.buildFilterParams();
    this.apiService.get<PaginatedResponse<Enquiry>>('/enquiries', filters).subscribe({
      next: (res) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => {
          this.dataSource.data = res.items;
          this.totalRecords = res.total;
          this.isLoading = false;
        }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notificationService.error('Failed to load enquiries'); this.isLoading = false; }, remaining);
      },
    });
  }

  buildFilterParams(): Record<string, string> {
    const val = this.filterForm.value;
    const params: Record<string, string> = {
      page: String(this.currentPage),
      pageSize: String(this.pageSize),
    };
    if (val.customerId) params['customerId'] = val.customerId;
    if (val.fromDate) params['dateFrom'] = this.formatDate(val.fromDate);
    if (val.toDate) params['dateTo'] = this.formatDate(val.toDate);
    if (val.status) params['status'] = val.status;
    return params;
  }

  formatDate(date: Date): string {
    if (!date) return '';
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  onPageChange(event: any): void {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadEnquiries();
  }

  applyFilters(): void {
    this.currentPage = 1;
    this.loadEnquiries();
  }

  resetFilters(): void {
    this.filterForm.reset();
    this.currentPage = 1;
    this.loadEnquiries();
  }

  navigateToNew(): void {
    this.router.navigate(['/enquiries/new']);
  }

  navigateToEdit(id: number): void {
    this.router.navigate(['/enquiries', id, 'edit']);
  }

  confirmDelete(enquiry: Enquiry): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '400px',
      data: {
        title: 'Delete Enquiry',
        message: `Are you sure you want to delete enquiry ${enquiry.enqNo}? This action cannot be undone.`,
        confirmLabel: 'Delete',
        confirmColor: 'warn',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.deleteEnquiry(enquiry.enqid);
      }
    });
  }

  deleteEnquiry(id: number): void {
    this.isLoading = true;
    this.apiService.delete(`/enquiries/${id}`).subscribe({
      next: () => {
        this.notificationService.success('Enquiry deleted successfully');
        this.loadEnquiries();
      },
      error: () => {
        this.notificationService.error('Failed to delete enquiry');
        this.isLoading = false;
      },
    });
  }
}
