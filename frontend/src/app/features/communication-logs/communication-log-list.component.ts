import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ApiService, PaginatedResponse } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../shared/components/skeleton-loader/skeleton-loader.component';
import { CommunicationLogDialogComponent } from './communication-log-dialog.component';

export interface CommunicationLog {
  commlogID: number;
  commmode: string;
  contactto: string;
  contactinfo: string;
  enqid: number | null;
  quoteid: number | null;
  commsubject: string;
  commdescription: string;
  createdon: string;
}

@Component({
  selector: 'app-communication-log-list',
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
    MatCardModule,
    MatDialogModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <div class="comm-log-list-container">
      <mat-card class="header-card">
        <mat-card-header>
          <mat-card-title>Communication Logs</mat-card-title>
          <mat-card-subtitle>Manage communication history</mat-card-subtitle>
        </mat-card-header>
        <mat-card-actions align="end">
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon>
            New Communication Log
          </button>
        </mat-card-actions>
      </mat-card>

      <!-- Filters -->
      <mat-card class="filter-card">
        <mat-card-content>
          <form [formGroup]="filterForm" class="filter-form">
            <mat-form-field appearance="outline" class="filter-field">
              <mat-label>Communication Mode</mat-label>
              <mat-select formControlName="commmode">
                <mat-option [value]="null">All Modes</mat-option>
                @for (mode of commModes; track mode) {
                  <mat-option [value]="mode">{{ mode }}</mat-option>
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
            <table mat-table [dataSource]="dataSource" matSort class="full-width">

              <!-- ID Column -->
              <ng-container matColumnDef="commlogID">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>#</th>
                <td mat-cell *matCellDef="let row">{{ row.commlogID }}</td>
              </ng-container>

              <!-- Mode Column -->
              <ng-container matColumnDef="commmode">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Mode</th>
                <td mat-cell *matCellDef="let row">{{ row.commmode }}</td>
              </ng-container>

              <!-- Contact To Column -->
              <ng-container matColumnDef="contactto">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Contact To</th>
                <td mat-cell *matCellDef="let row">{{ row.contactto }}</td>
              </ng-container>

              <!-- Subject Column -->
              <ng-container matColumnDef="commsubject">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Subject</th>
                <td mat-cell *matCellDef="let row">{{ row.commsubject }}</td>
              </ng-container>

              <!-- Created On Column -->
              <ng-container matColumnDef="createdon">
                <th mat-header-cell *matHeaderCellDef mat-sort-header>Created On</th>
                <td mat-cell *matCellDef="let row">{{ row.createdon | date: 'dd/MM/yyyy HH:mm' }}</td>
              </ng-container>

              <!-- Actions Column -->
              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let row">
                  <button mat-icon-button color="primary" (click)="openDialog(row)" title="Edit">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button color="warn" (click)="confirmDelete(row)" title="Delete">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns; sticky: true"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>

              <!-- No Data Row -->
              <tr class="mat-row no-data-row" *matNoDataRow>
                <td class="mat-cell" [attr.colspan]="displayedColumns.length">
                  <div class="no-data">
                    <mat-icon>inbox</mat-icon>
                    <p>No communication logs found</p>
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
            aria-label="Select page of communication logs">
          </mat-paginator>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .comm-log-list-container {
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

    .table-container {
      overflow-x: auto;
    }

    .full-width {
      width: 100%;
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
export class CommunicationLogListComponent implements OnInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  displayedColumns: string[] = ['commlogID', 'commmode', 'contactto', 'commsubject', 'createdon', 'actions'];
  dataSource = new MatTableDataSource<CommunicationLog>([]);
  commModes: string[] = [];
  isLoading = false;
  filterForm: FormGroup;

  // Server-side pagination state
  currentPage = 1;
  pageSize = 25;
  totalRecords = 0;

  constructor(
    private fb: FormBuilder,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private dialog: MatDialog,
  ) {
    this.filterForm = this.fb.group({
      commmode: [null],
    });
  }

  ngOnInit(): void {
    this.loadCommModes();
    this.loadCommunicationLogs();
  }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  loadCommModes(): void {
    this.apiService.get<string[]>('/masters/communication-modes').subscribe({
      next: (data) => this.commModes = data || [],
      error: () => this.notificationService.error('Failed to load communication modes'),
    });
  }

  loadCommunicationLogs(): void {
    this.isLoading = true;
    const start = Date.now();
    const params = this.buildFilterParams();
    this.apiService.get<PaginatedResponse<CommunicationLog>>('/communication-logs', params).subscribe({
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
        setTimeout(() => {
          this.notificationService.error('Failed to load communication logs');
          this.isLoading = false;
        }, remaining);
      },
    });
  }

  buildFilterParams(): Record<string, string> {
    const val = this.filterForm.value;
    const params: Record<string, string> = {
      page: String(this.currentPage),
      pageSize: String(this.pageSize),
    };
    if (val.commmode) params['commmode'] = val.commmode;
    return params;
  }

  onPageChange(event: any): void {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadCommunicationLogs();
  }

  applyFilters(): void {
    this.currentPage = 1;
    this.loadCommunicationLogs();
  }

  resetFilters(): void {
    this.filterForm.reset();
    this.currentPage = 1;
    this.loadCommunicationLogs();
  }

  openDialog(row?: CommunicationLog): void {
    const ref = this.dialog.open(CommunicationLogDialogComponent, {
      width: '600px',
      data: { row: row || null, commModes: this.commModes },
    });
    ref.afterClosed().subscribe((saved) => {
      if (saved) this.loadCommunicationLogs();
    });
  }

  confirmDelete(row: CommunicationLog): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete Communication Log', message: 'Delete this communication log?' },
    });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.apiService.delete(`/communication-logs/${row.commlogID}`).subscribe({
          next: () => {
            this.notificationService.success('Communication log deleted successfully');
            this.loadCommunicationLogs();
          },
          error: () => this.notificationService.error('Failed to delete communication log'),
        });
      }
    });
  }
}
