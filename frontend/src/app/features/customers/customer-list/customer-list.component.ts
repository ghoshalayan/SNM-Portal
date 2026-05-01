import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { debounceTime, distinctUntilChanged, Subject } from 'rxjs';
import { ApiService, PaginatedResponse } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

export interface Customer {
  customerId: number;
  customerCode: string;
  customerName: string;
  GSTN: string;
  PAN: string;
  classificationId: number;
  classificationName?: string;
}

export interface CustomerClassification {
  classificationId: number;
  classificationName: string;
}

@Component({
  selector: 'app-customer-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatDialogModule,
    MatCardModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <div class="customer-list-container">
      <mat-card>
        <mat-card-header>
          <mat-card-title>Customers</mat-card-title>
          <div class="header-actions">
            <button mat-raised-button color="primary" (click)="navigateToNew()">
              <mat-icon>add</mat-icon>
              Add Customer
            </button>
          </div>
        </mat-card-header>

        <mat-card-content>
          <div class="filters-row">
            <mat-form-field appearance="outline" class="search-field">
              <mat-label>Search</mat-label>
              <input
                matInput
                [(ngModel)]="searchTerm"
                (ngModelChange)="onSearchChange($event)"
                placeholder="Search by code, name, GSTN..."
              />
              <mat-icon matSuffix>search</mat-icon>
            </mat-form-field>

            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>Classification</mat-label>
              <mat-select
                [(ngModel)]="selectedClassificationId"
                (ngModelChange)="onClassificationChange()"
              >
                <mat-option [value]="null">All Classifications</mat-option>
                <mat-option
                  *ngFor="let cls of classifications"
                  [value]="cls.classificationId"
                >
                  {{ cls.classificationName }}
                </mat-option>
              </mat-select>
            </mat-form-field>

            <button mat-stroked-button (click)="clearFilters()" class="clear-btn">
              <mat-icon>clear</mat-icon>
              Clear
            </button>
          </div>

          @if (isLoading) { <app-skeleton-loader type="table" [rows]="5" [columns]="5"></app-skeleton-loader> }

          <div class="table-wrapper" [hidden]="isLoading">
            <table mat-table [dataSource]="dataSource" matSort class="customer-table">

              <ng-container matColumnDef="customerCode">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Code</th>
                <td mat-cell *matCellDef="let row">{{ row.customerCode }}</td>
              </ng-container>

              <ng-container matColumnDef="customerName">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Customer Name</th>
                <td mat-cell *matCellDef="let row">{{ row.customerName }}</td>
              </ng-container>

              <ng-container matColumnDef="GSTN">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>GSTN</th>
                <td mat-cell *matCellDef="let row">{{ row.GSTN }}</td>
              </ng-container>

              <ng-container matColumnDef="classificationName">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Classification</th>
                <td mat-cell *matCellDef="let row">{{ row.classificationName }}</td>
              </ng-container>

              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let row">
                  <button
                    mat-icon-button
                    color="primary"
                    matTooltip="Edit Customer"
                    (click)="navigateToEdit(row)"
                  >
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button
                    mat-icon-button
                    color="warn"
                    matTooltip="Delete Customer"
                    (click)="deleteCustomer(row)"
                  >
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>

              <tr class="mat-row" *matNoDataRow>
                <td class="mat-cell no-data-cell" [attr.colspan]="displayedColumns.length">
                  <span *ngIf="!isLoading">No customers found.</span>
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
    .customer-list-container {
      padding: 24px;
    }

    mat-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .header-actions {
      margin-left: auto;
    }

    .filters-row {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }

    .search-field {
      flex: 1;
      min-width: 220px;
    }

    .filter-field {
      min-width: 200px;
    }

    .clear-btn {
      height: 56px;
    }

    .loading-overlay {
      display: flex;
      justify-content: center;
      padding: 32px 0;
    }

    .table-wrapper {
      overflow-x: auto;
    }

    .table-wrapper.loading {
      opacity: 0.5;
      pointer-events: none;
    }

    .customer-table {
      width: 100%;
    }

    .no-data-cell {
      text-align: center;
      padding: 32px;
      color: rgba(0, 0, 0, 0.54);
    }

    mat-card-title {
      font-size: 20px;
      font-weight: 500;
    }
  `],
})
export class CustomerListComponent implements OnInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  displayedColumns: string[] = [
    'customerCode',
    'customerName',
    'GSTN',
    'classificationName',
    'actions',
  ];

  dataSource = new MatTableDataSource<Customer>([]);
  classifications: CustomerClassification[] = [];
  searchTerm = '';
  selectedClassificationId: number | null = null;
  isLoading = false;

  // Server-side pagination state
  currentPage = 1;
  pageSize = 25;
  totalRecords = 0;

  private searchSubject = new Subject<string>();

  constructor(
    private api: ApiService,
    private notification: NotificationService,
    private dialog: MatDialog,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadClassifications();
    this.loadCustomers();

    this.searchSubject
      .pipe(debounceTime(400), distinctUntilChanged())
      .subscribe(() => { this.currentPage = 1; this.loadCustomers(); });
  }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  loadClassifications(): void {
    this.api.get<CustomerClassification[]>('/masters/customer-classifications').subscribe({
      next: (data) => (this.classifications = data),
      error: () => this.notification.error('Failed to load classifications'),
    });
  }

  loadCustomers(): void {
    this.isLoading = true;
    const start = Date.now();
    const params: Record<string, string> = {
      page: String(this.currentPage),
      pageSize: String(this.pageSize),
      sortBy: 'customerId',
      sortDir: 'desc',
    };
    if (this.searchTerm?.trim()) {
      params['search'] = this.searchTerm.trim();
    }
    if (this.selectedClassificationId != null) {
      params['classificationId'] = String(this.selectedClassificationId);
    }

    this.api.get<PaginatedResponse<Customer>>('/customers', params).subscribe({
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
        setTimeout(() => { this.notification.error('Failed to load customers'); this.isLoading = false; }, remaining);
      },
    });
  }

  onPageChange(event: any): void {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadCustomers();
  }

  onSearchChange(value: string): void {
    this.searchSubject.next(value);
  }

  onClassificationChange(): void {
    this.currentPage = 1;
    this.loadCustomers();
  }

  clearFilters(): void {
    this.searchTerm = '';
    this.selectedClassificationId = null;
    this.currentPage = 1;
    this.loadCustomers();
  }

  navigateToNew(): void {
    this.router.navigate(['/customers/new']);
  }

  navigateToEdit(customer: Customer): void {
    this.router.navigate(['/customers', customer.customerId, 'edit']);
  }

  deleteCustomer(customer: Customer): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete Customer',
        message: `Are you sure you want to delete "${customer.customerName}"? This action cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/customers/${customer.customerId}`).subscribe({
          next: () => {
            this.notification.success('Customer deleted successfully');
            this.loadCustomers();
          },
          error: () => this.notification.error('Failed to delete customer'),
        });
      }
    });
  }
}
