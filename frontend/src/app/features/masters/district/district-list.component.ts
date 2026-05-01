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
import { MatSelectModule } from '@angular/material/select';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { DistrictDialogComponent } from './district-dialog.component';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

@Component({
  selector: 'app-district-list',
  standalone: true,
  imports: [
    CommonModule, MatTableModule, MatButtonModule, MatIconModule,
    MatDialogModule, MatCardModule, MatFormFieldModule, MatInputModule,
    MatPaginatorModule, MatSortModule, MatSelectModule, SkeletonLoaderComponent,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>Districts</mat-card-title>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="filter-field">
            <mat-label>Country</mat-label>
            <mat-select [(value)]="selectedCountry" (selectionChange)="onCountryChange()">
              <mat-option value="">All</mat-option>
              <mat-option *ngFor="let c of countries" [value]="c.countryname">{{ c.countryname }}</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" class="filter-field">
            <mat-label>State</mat-label>
            <mat-select [(value)]="selectedState" (selectionChange)="load()">
              <mat-option value="">All</mat-option>
              <mat-option *ngFor="let s of states" [value]="s.StateName">{{ s.StateName }}</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" class="search-field">
            <mat-label>Search</mat-label>
            <input matInput (keyup)="applyFilter($event)" placeholder="Search districts..." />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="openDialog()">
            <mat-icon>add</mat-icon> Add District
          </button>
        </div>
      </mat-card-header>
      <mat-card-content>
        @if (loading) { <app-skeleton-loader type="table" [rows]="5" [columns]="5"></app-skeleton-loader> }
        <table mat-table [dataSource]="dataSource" matSort class="full-width" [hidden]="loading">
          <ng-container matColumnDef="districtid">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>#</th>
            <td mat-cell *matCellDef="let row">{{ row.districtid }}</td>
          </ng-container>
          <ng-container matColumnDef="districName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>District Name</th>
            <td mat-cell *matCellDef="let row">{{ row.districName }}</td>
          </ng-container>
          <ng-container matColumnDef="StateName">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>State</th>
            <td mat-cell *matCellDef="let row">{{ row.StateName }}</td>
          </ng-container>
          <ng-container matColumnDef="Country">
            <th mat-header-cell *matHeaderCellDef mat-sort-header>Country</th>
            <td mat-cell *matCellDef="let row">{{ row.Country }}</td>
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
    .header-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .search-field { width: 250px; }
    .filter-field { width: 200px; }
    .full-width { width: 100%; }
    .no-data { padding: 24px; text-align: center; color: #888; }
  `],
})
export class DistrictListComponent implements OnInit, AfterViewInit {
  dataSource = new MatTableDataSource<any>([]);
  displayedColumns = ['districtid', 'districName', 'StateName', 'Country', 'actions'];
  loading = true;
  countries: any[] = [];
  states: any[] = [];
  selectedCountry = '';
  selectedState = '';

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor(private api: ApiService, private notify: NotificationService, private dialog: MatDialog) {}

  ngOnInit() {
    this.api.get('/masters/countries').subscribe({
      next: (res: any) => this.countries = res || [],
    });
    this.loadStates();
    this.load();
  }

  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  onCountryChange() {
    this.selectedState = '';
    this.loadStates();
    this.load();
  }

  loadStates() {
    const params: any = {};
    if (this.selectedCountry) params.country = this.selectedCountry;
    this.api.get('/masters/states', params).subscribe({
      next: (res: any) => this.states = res || [],
    });
  }

  load() {
    this.loading = true;
    const start = Date.now();
    const params: any = {};
    if (this.selectedCountry) params.country = this.selectedCountry;
    if (this.selectedState) params.state = this.selectedState;
    this.api.get('/masters/districts', params).subscribe({
      next: (res: any) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.dataSource.data = res || []; this.loading = false; }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load districts'); this.loading = false; }, remaining);
      },
    });
  }

  applyFilter(event: Event) {
    this.dataSource.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
  }

  openDialog(row?: any) {
    const ref = this.dialog.open(DistrictDialogComponent, {
      width: '480px',
      data: { row: row || null, countries: this.countries },
    });
    ref.afterClosed().subscribe((saved) => { if (saved) this.load(); });
  }

  deleteItem(row: any) {
    const ref = this.dialog.open(ConfirmDialogComponent, { data: { message: `Delete district "${row.districName}"?` } });
    ref.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api.delete(`/masters/districts/${row.districtid}`).subscribe({
          next: () => { this.notify.success('Deleted successfully'); this.load(); },
          error: () => this.notify.error('Delete failed'),
        });
      }
    });
  }
}
