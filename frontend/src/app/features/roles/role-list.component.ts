import { Component, OnInit, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { RoleDialogComponent } from './role-dialog.component';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../shared/components/skeleton-loader/skeleton-loader.component';

interface Role {
  roleId: number;
  roleName: string;
  IsSuperAdmin: boolean;
  isActive: boolean;
}

@Component({
  selector: 'app-role-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    SkeletonLoaderComponent,
  ],
  template: `
    <div class="page-header">
      <h2>Roles</h2>
      <button mat-raised-button color="primary" (click)="openDialog()">
        <mat-icon>add</mat-icon> Add Role
      </button>
    </div>

    <mat-card>
      <mat-card-content>
        <mat-form-field appearance="outline" style="width:300px;margin-bottom:1rem">
          <mat-label>Search</mat-label>
          <input matInput (keyup)="applyFilter($event)" placeholder="Search roles..." />
          <mat-icon matPrefix>search</mat-icon>
        </mat-form-field>

        @if (loading) {
          <app-skeleton-loader type="table" [rows]="4" [columns]="3"></app-skeleton-loader>
        }
        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="roleName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Role Name</th>
            <td mat-cell *matCellDef="let row">{{ row.roleName }}</td>
          </ng-container>

          <ng-container matColumnDef="IsSuperAdmin">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Super Admin</th>
            <td mat-cell *matCellDef="let row">
              <mat-checkbox [checked]="row.IsSuperAdmin" disabled></mat-checkbox>
            </td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button mat-icon-button color="primary" (click)="openDialog(row)">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button color="accent" [routerLink]="['/roles', row.roleId, 'permissions-v2']"
                matTooltip="Manage permissions">
                <mat-icon>security</mat-icon>
              </button>
              <button mat-icon-button color="warn" (click)="deleteRole(row)">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data" [attr.colspan]="displayedColumns.length">No records found.</td>
          </tr>
        </table>

        <mat-paginator [pageSizeOptions]="[10, 25, 50]" [pageSize]="10" showFirstLastButtons [hidden]="loading"></mat-paginator>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
    .page-header h2 { color: var(--snm-text-primary); font-weight: 600; margin: 0; }
    .full-width { width: 100%; }
    .no-data { padding: 24px; text-align: center; color: #888; }
  `],
})
export class RoleListComponent implements OnInit, AfterViewInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  dataSource = new MatTableDataSource<Role>([]);
  loading = true;
  displayedColumns = ['roleName', 'IsSuperAdmin', 'actions'];

  constructor(
    private api: ApiService,
    private dialog: MatDialog,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadRoles();
  }

  ngAfterViewInit(): void {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  loadRoles(): void {
    this.loading = true;
    const start = Date.now();
    this.api.get<Role[]>('/roles').subscribe({
      next: (data) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.dataSource.data = data; this.loading = false; }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load roles'); this.loading = false; }, remaining);
      },
    });
  }

  applyFilter(event: Event): void {
    this.dataSource.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
  }

  openDialog(role?: Role): void {
    const dialogRef = this.dialog.open(RoleDialogComponent, {
      width: '400px',
      data: role || null,
    });
    dialogRef.afterClosed().subscribe(result => {
      if (result) this.loadRoles();
    });
  }

  deleteRole(role: Role): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete Role', message: `Delete "${role.roleName}"?` },
    });
    dialogRef.afterClosed().subscribe(confirmed => {
      if (confirmed) {
        this.api.delete(`/roles/${role.roleId}`).subscribe({
          next: () => { this.notify.success('Role deleted'); this.loadRoles(); },
          error: () => this.notify.error('Failed to delete role'),
        });
      }
    });
  }
}
