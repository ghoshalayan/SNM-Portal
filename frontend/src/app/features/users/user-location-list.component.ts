import { Component, OnInit, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService, PaginatedResponse } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { UserLocationDialogComponent } from './user-location-dialog.component';
import { SkeletonLoaderComponent } from '../../shared/components/skeleton-loader/skeleton-loader.component';

interface User {
  userId: number;
  userName: string;
  userCode: string;
  userEmail: string;
  userPhone: string;
  userLogin: string;
}

@Component({
  selector: 'app-user-location-list',
  standalone: true,
  imports: [
    CommonModule, MatTableModule, MatPaginatorModule, MatSortModule,
    MatButtonModule, MatIconModule, MatDialogModule, MatCardModule,
    MatFormFieldModule, MatInputModule, MatTooltipModule, SkeletonLoaderComponent,
  ],
  template: `
    <div class="page-header">
      <h2>User Location Mapping</h2>
    </div>
    <mat-card>
      <mat-card-content>
        <mat-form-field appearance="outline" style="width:300px;margin-bottom:1rem">
          <mat-label>Search</mat-label>
          <input matInput (keyup)="applyFilter($event)" placeholder="Search users..." />
          <mat-icon matPrefix>search</mat-icon>
        </mat-form-field>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="5"></app-skeleton-loader> }
        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="userCode"><th mat-header-cell *matHeaderCellDef mat-sort-header>Code</th><td mat-cell *matCellDef="let r">{{r.userCode}}</td></ng-container>
          <ng-container matColumnDef="userName"><th mat-header-cell *matHeaderCellDef mat-sort-header>Name</th><td mat-cell *matCellDef="let r">{{r.userName}}</td></ng-container>
          <ng-container matColumnDef="userEmail"><th mat-header-cell *matHeaderCellDef mat-sort-header>Email</th><td mat-cell *matCellDef="let r">{{r.userEmail}}</td></ng-container>
          <ng-container matColumnDef="userPhone"><th mat-header-cell *matHeaderCellDef>Phone</th><td mat-cell *matCellDef="let r">{{r.userPhone}}</td></ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Location Mapping</th>
            <td mat-cell *matCellDef="let r">
              <button mat-icon-button (click)="openLocationDialog(r)" matTooltip="Manage Locations" style="color:var(--snm-accent)">
                <mat-icon>location_on</mat-icon>
              </button>
            </td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let r; columns: displayedColumns;"></tr>
          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data" [attr.colspan]="displayedColumns.length">No records found.</td>
          </tr>
        </table>
        <mat-paginator [pageSizeOptions]="[10, 25, 50]" [pageSize]="pageSize" [length]="totalRecords" [pageIndex]="currentPage - 1" showFirstLastButtons (page)="onPageChange($event)" [hidden]="loading"></mat-paginator>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
    .full-width { width: 100%; }
    .no-data { padding: 24px; text-align: center; color: #888; }
  `],
})
export class UserLocationListComponent implements OnInit, AfterViewInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  dataSource = new MatTableDataSource<User>([]);
  displayedColumns = ['userCode', 'userName', 'userEmail', 'userPhone', 'actions'];
  loading = true;
  searchTerm = '';

  currentPage = 1;
  pageSize = 10;
  totalRecords = 0;

  constructor(private api: ApiService, private dialog: MatDialog, private notify: NotificationService) {}

  ngOnInit(): void { this.loadUsers(); }

  ngAfterViewInit(): void {
    this.dataSource.sort = this.sort;
  }

  loadUsers(): void {
    this.loading = true;
    const start = Date.now();
    const params: Record<string, string> = {
      page: String(this.currentPage),
      pageSize: String(this.pageSize),
    };
    if (this.searchTerm?.trim()) {
      params['search'] = this.searchTerm.trim();
    }
    this.api.get<PaginatedResponse<User>>('/users', params).subscribe({
      next: res => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => {
          this.dataSource.data = res.items;
          this.totalRecords = res.total;
          this.loading = false;
        }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load users'); this.loading = false; }, remaining);
      },
    });
  }

  onPageChange(event: any): void {
    this.currentPage = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadUsers();
  }

  applyFilter(event: Event): void {
    this.searchTerm = (event.target as HTMLInputElement).value.trim().toLowerCase();
    this.currentPage = 1;
    this.loadUsers();
  }

  openLocationDialog(user: User): void {
    this.dialog.open(UserLocationDialogComponent, {
      width: '960px',
      maxWidth: '95vw',
      data: { userId: user.userId, userName: user.userName },
    });
  }
}
