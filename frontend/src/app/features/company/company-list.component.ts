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
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { CompanyDialogComponent } from './company-dialog.component';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { SkeletonLoaderComponent } from '../../shared/components/skeleton-loader/skeleton-loader.component';

interface Company {
  companyId: number;
  companyName: string;
  companyCode: string;
  city: string;
  state: string;
  phone: string;
  email: string;
  isActive: boolean;
}

@Component({
  selector: 'app-company-list',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    SkeletonLoaderComponent,
  ],
  templateUrl: './company-list.component.html',
  styleUrl: './company-list.component.scss',
})
export class CompanyListComponent implements OnInit, AfterViewInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  dataSource = new MatTableDataSource<Company>([]);
  loading = true;
  displayedColumns = ['companyCode', 'companyName', 'city', 'state', 'phone', 'email', 'actions'];

  constructor(
    private api: ApiService,
    private dialog: MatDialog,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadCompanies();
  }

  ngAfterViewInit(): void {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  loadCompanies(): void {
    this.loading = true;
    const start = Date.now();
    this.api.get<Company[]>('/companies').subscribe({
      next: (data) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.dataSource.data = data; this.loading = false; }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => { this.notify.error('Failed to load companies'); this.loading = false; }, remaining);
      },
    });
  }

  openDialog(company?: Company): void {
    const dialogRef = this.dialog.open(CompanyDialogComponent, {
      width: '700px',
      data: company || null,
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) this.loadCompanies();
    });
  }

  deleteCompany(company: Company): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete Company', message: `Are you sure you want to delete "${company.companyName}"?` },
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (confirmed) {
        this.api.delete(`/companies/${company.companyId}`).subscribe({
          next: () => {
            this.notify.success('Company deleted');
            this.loadCompanies();
          },
          error: () => this.notify.error('Failed to delete company'),
        });
      }
    });
  }

  applyFilter(event: Event): void {
    const value = (event.target as HTMLInputElement).value.trim().toLowerCase();
    this.dataSource.filter = value;
  }
}
