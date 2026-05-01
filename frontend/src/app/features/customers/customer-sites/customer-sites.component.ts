import { Component, Input, OnInit, OnChanges, SimpleChanges, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { SearchFilterPipe } from '../../../shared/pipes/search-filter.pipe';

export interface CustomerSite {
  siteId?: number;
  customerId?: number;
  siteAddressCode: string;
  addressLine: string;
  country: string;
  state: string;
  dist: string;
  pin: string;
  contactPerson1: string;
  contactPhone1: string;
  contactEmail1: string;
  isHeadOffice?: boolean;
}

@Component({
  selector: 'app-site-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    MatDividerModule,
    MatSlideToggleModule,
    SearchFilterPipe,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.site?.siteId ? 'Edit Site' : 'Add Site' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="site-form">
        <div class="form-row">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Site Address Code *</mat-label>
            <input matInput formControlName="siteAddressCode" [readonly]="!data.site?.siteId" />
            <mat-hint *ngIf="!data.site?.siteId">Auto-generated from customer code</mat-hint>
            <mat-error *ngIf="form.get('siteAddressCode')?.hasError('required')">Required</mat-error>
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Address Line *</mat-label>
            <textarea matInput formControlName="addressLine" rows="2"></textarea>
            <mat-error *ngIf="form.get('addressLine')?.hasError('required')">Required</mat-error>
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Country</mat-label>
            <mat-select formControlName="country"
              (selectionChange)="onCountryChange($event.value)"
              (openedChange)="countrySearch = ''">
              <div class="select-search" (click)="$event.stopPropagation()">
                <input placeholder="Search country..." [(ngModel)]="countrySearch" [ngModelOptions]="{standalone: true}" (keydown)="$event.stopPropagation()">
              </div>
              @for (c of countries | searchFilter:countrySearch:'countryName'; track c.countryid) {
                <mat-option [value]="c.countryName">{{ c.countryName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>State</mat-label>
            <mat-select formControlName="state"
              (selectionChange)="onStateChange($event.value)"
              (openedChange)="stateSearch = ''">
              <div class="select-search" (click)="$event.stopPropagation()">
                <input placeholder="Search state..." [(ngModel)]="stateSearch" [ngModelOptions]="{standalone: true}" (keydown)="$event.stopPropagation()">
              </div>
              @for (s of states | searchFilter:stateSearch:'StateName'; track s.stateid) {
                <mat-option [value]="s.StateName">{{ s.StateName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>District</mat-label>
            <mat-select formControlName="dist"
              (openedChange)="distSearch = ''">
              <div class="select-search" (click)="$event.stopPropagation()">
                <input placeholder="Search district..." [(ngModel)]="distSearch" [ngModelOptions]="{standalone: true}" (keydown)="$event.stopPropagation()">
              </div>
              @for (d of districts | searchFilter:distSearch:'districName'; track d.districName) {
                <mat-option [value]="d.districName">{{ d.districName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>PIN</mat-label>
            <input matInput formControlName="pin" maxlength="6" />
          </mat-form-field>
        </div>

        <div class="form-row" style="margin-bottom: 8px;">
          <mat-slide-toggle formControlName="isHeadOffice" color="primary">
            Head Office
          </mat-slide-toggle>
        </div>

        <mat-divider class="section-divider"></mat-divider>
        <p class="section-label">Primary Contact</p>

        <div class="form-row">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Contact Person</mat-label>
            <input matInput formControlName="contactPerson1" />
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Contact Phone</mat-label>
            <input matInput formControlName="contactPhone1" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Contact Email</mat-label>
            <input matInput formControlName="contactEmail1" type="email" />
            <mat-error *ngIf="form.get('contactEmail1')?.hasError('email')">Invalid email</mat-error>
          </mat-form-field>
        </div>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid">
        {{ data.site?.siteId ? 'Update' : 'Add' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .site-form {
      min-width: 520px;
      padding: 8px 0;
    }
    .form-row {
      display: flex;
      gap: 16px;
      margin-bottom: 4px;
    }
    .half-width {
      flex: 1;
    }
    .full-width {
      flex: 1;
    }
    .select-search {
      padding: 8px 16px 4px;
      position: sticky;
      top: 0;
      background: var(--mat-sys-surface, #fff);
      z-index: 1;
    }
    .select-search input {
      width: 100%;
      padding: 6px 8px;
      border: 1px solid #ccc;
      border-radius: 4px;
      font-size: 14px;
      outline: none;
    }
    .section-divider {
      margin: 12px 0 8px;
    }
    .section-label {
      font-size: 13px;
      font-weight: 500;
      color: rgba(0,0,0,0.6);
      margin: 0 0 8px;
    }
  `],
})
export class SiteDialogComponent implements OnInit {
  form: FormGroup;
  countries: any[] = [];
  states: any[] = [];
  districts: any[] = [];
  allAccess = false;
  private myLocations: any = null;
  countrySearch = '';
  stateSearch = '';
  distSearch = '';

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private dialogRef: MatDialogRef<SiteDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: {
      site: CustomerSite | null;
      customerCode: string;
      nextSiteIndex: number;
    }
  ) {
    const isEdit = !!data.site?.siteId;
    const autoCode = isEdit
      ? (data.site!.siteAddressCode ?? '')
      : this.generateSiteCode(data.customerCode, data.nextSiteIndex);

    this.form = this.fb.group({
      siteAddressCode: [autoCode, Validators.required],
      addressLine: [data.site?.addressLine ?? '', Validators.required],
      country: [data.site?.country ?? ''],
      state: [data.site?.state ?? ''],
      dist: [data.site?.dist ?? ''],
      pin: [data.site?.pin ?? ''],
      contactPerson1: [data.site?.contactPerson1 ?? ''],
      contactPhone1: [data.site?.contactPhone1 ?? ''],
      contactEmail1: [data.site?.contactEmail1 ?? '', Validators.email],
      isHeadOffice: [data.site?.isHeadOffice ?? false],
    });
  }

  private generateSiteCode(customerCode: string, index: number): string {
    if (!customerCode) return '';
    if (index === 0) return customerCode;
    return `${customerCode}/${index}`;
  }

  ngOnInit(): void {
    this.loadMyLocations();
  }

  loadMyLocations(): void {
    this.api.get<any>('/users/my-locations').subscribe({
      next: (loc) => {
        this.myLocations = loc;
        this.allAccess = loc.allAccess;
        this.countries = loc.countries || [];

        const s = this.data.site;
        if (s?.country) {
          this.onCountryChange(s.country, false);
        } else if (s?.state) {
          // Reverse-lookup country from state
          const found = this.countries.find((ct: any) =>
            ct.states?.some((st: any) => st.StateName === s.state)
          );
          if (found) {
            this.form.get('country')?.setValue(found.countryName);
            this.onCountryChange(found.countryName, false);
          }
        } else if (this.countries.length === 1) {
          this.form.get('country')?.setValue(this.countries[0].countryName);
          this.onCountryChange(this.countries[0].countryName, false);
        }
        if (s?.state) this.onStateChange(s.state, false);
      },
    });
  }

  onCountryChange(countryName: string, resetChildren = true): void {
    if (resetChildren) {
      this.form.get('state')?.setValue('');
      this.form.get('dist')?.setValue('');
      this.districts = [];
    }
    const country = this.countries.find((c: any) => c.countryName === countryName);
    this.states = country?.states || [];
  }

  onStateChange(stateName: string, resetDist = true): void {
    if (resetDist) this.form.get('dist')?.setValue('');
    if (!stateName) { this.districts = []; return; }

    const stateEntry = this.states.find((s: any) => s.StateName === stateName);
    if (this.allAccess || stateEntry?.allDistricts) {
      this.api.get<any[]>('/masters/districts', { state: stateName }).subscribe({
        next: (data) => (this.districts = data),
      });
    } else {
      this.districts = (stateEntry?.districts || []).map((d: any) => ({ districName: d.districName }));
    }
  }

  save(): void {
    if (this.form.valid) {
      this.dialogRef.close(this.form.value);
    }
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}

@Component({
  selector: 'app-customer-sites',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatDialogModule,
  ],
  template: `
    <div class="sites-container">
      <div class="sites-toolbar">
        <span class="sites-title">Sites</span>
        <button
          mat-raised-button
          color="primary"
          (click)="openDialog(null)"
          [disabled]="!customerId"
        >
          <mat-icon>add_location</mat-icon>
          Add Site
        </button>
      </div>

      <div class="loading-wrap" *ngIf="isLoading">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div class="table-wrapper" *ngIf="!isLoading">
        <table mat-table [dataSource]="dataSource" class="sites-table">

          <ng-container matColumnDef="siteAddressCode">
            <th mat-header-cell *matHeaderCellDef>Code</th>
            <td mat-cell *matCellDef="let row">
              {{ row.siteAddressCode }}
              <span *ngIf="row.isHeadOffice" class="ho-badge">HO</span>
            </td>
          </ng-container>

          <ng-container matColumnDef="addressLine">
            <th mat-header-cell *matHeaderCellDef>Address</th>
            <td mat-cell *matCellDef="let row">{{ row.addressLine }}</td>
          </ng-container>

          <ng-container matColumnDef="state">
            <th mat-header-cell *matHeaderCellDef>State</th>
            <td mat-cell *matCellDef="let row">{{ row.state }}</td>
          </ng-container>

          <ng-container matColumnDef="dist">
            <th mat-header-cell *matHeaderCellDef>District</th>
            <td mat-cell *matCellDef="let row">{{ row.dist }}</td>
          </ng-container>

          <ng-container matColumnDef="pin">
            <th mat-header-cell *matHeaderCellDef>PIN</th>
            <td mat-cell *matCellDef="let row">{{ row.pin }}</td>
          </ng-container>

          <ng-container matColumnDef="contactPerson1">
            <th mat-header-cell *matHeaderCellDef>Contact Person</th>
            <td mat-cell *matCellDef="let row">{{ row.contactPerson1 }}</td>
          </ng-container>

          <ng-container matColumnDef="contactPhone1">
            <th mat-header-cell *matHeaderCellDef>Phone</th>
            <td mat-cell *matCellDef="let row">{{ row.contactPhone1 }}</td>
          </ng-container>

          <ng-container matColumnDef="contactEmail1">
            <th mat-header-cell *matHeaderCellDef>Email</th>
            <td mat-cell *matCellDef="let row">{{ row.contactEmail1 }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button
                mat-icon-button
                color="primary"
                matTooltip="Edit Site"
                (click)="openDialog(row)"
              >
                <mat-icon>edit</mat-icon>
              </button>
              <button
                mat-icon-button
                color="warn"
                matTooltip="Delete Site"
                (click)="deleteSite(row)"
              >
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>

          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data-cell" [attr.colspan]="displayedColumns.length">
              No sites found. Click "Add Site" to add one.
            </td>
          </tr>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .sites-container {
      padding: 16px 0;
    }

    .sites-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .sites-title {
      font-size: 16px;
      font-weight: 500;
      color: rgba(0, 0, 0, 0.87);
    }

    .loading-wrap {
      display: flex;
      justify-content: center;
      padding: 32px 0;
    }

    .table-wrapper {
      overflow-x: auto;
    }

    .sites-table {
      width: 100%;
    }

    .no-data-cell {
      text-align: center;
      padding: 24px;
      color: rgba(0, 0, 0, 0.54);
    }

    .ho-badge {
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 3px;
      background: #e3f2fd;
      color: #1565c0;
      margin-left: 6px;
      vertical-align: middle;
    }
  `],
})
export class CustomerSitesComponent implements OnInit, OnChanges {
  @Input() customerId!: number | null;
  @Input() customerCode: string = '';

  displayedColumns: string[] = [
    'siteAddressCode',
    'addressLine',
    'state',
    'dist',
    'pin',
    'contactPerson1',
    'contactPhone1',
    'contactEmail1',
    'actions',
  ];

  dataSource = new MatTableDataSource<CustomerSite>([]);
  isLoading = false;

  constructor(
    private api: ApiService,
    private notification: NotificationService,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    if (this.customerId) {
      this.loadSites();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['customerId'] && this.customerId) {
      this.loadSites();
    }
  }

  loadSites(): void {
    if (!this.customerId) return;
    this.isLoading = true;
    this.api.get<CustomerSite[]>(`/customers/${this.customerId}/sites`).subscribe({
      next: (data) => {
        this.dataSource.data = data;
        this.isLoading = false;
      },
      error: () => {
        this.notification.error('Failed to load sites');
        this.isLoading = false;
      },
    });
  }

  private getNextSiteIndex(): number {
    const sites = this.dataSource.data;
    if (sites.length === 0) return 0;
    // Find the highest suffix number from existing codes
    let maxIndex = 0;
    for (const s of sites) {
      const code = s.siteAddressCode || '';
      const slashPos = code.lastIndexOf('/');
      if (slashPos >= 0) {
        const suffix = parseInt(code.substring(slashPos + 1), 10);
        if (!isNaN(suffix) && suffix > maxIndex) maxIndex = suffix;
      }
    }
    return maxIndex + 1;
  }

  openDialog(site: CustomerSite | null): void {
    const dialogRef = this.dialog.open(SiteDialogComponent, {
      data: {
        site,
        customerCode: this.customerCode,
        nextSiteIndex: site ? 0 : this.getNextSiteIndex(),
      },
      width: '600px',
      disableClose: true,
    });

    dialogRef.afterClosed().subscribe((result: Partial<CustomerSite> | null) => {
      if (!result) return;

      if (site?.siteId) {
        this.api
          .put<CustomerSite>(`/customers/${this.customerId}/sites/${site.siteId}`, result)
          .subscribe({
            next: () => {
              this.notification.success('Site updated successfully');
              this.loadSites();
            },
            error: () => this.notification.error('Failed to update site'),
          });
      } else {
        this.api
          .post<CustomerSite>(`/customers/${this.customerId}/sites`, result)
          .subscribe({
            next: () => {
              this.notification.success('Site added successfully');
              this.loadSites();
            },
            error: () => this.notification.error('Failed to add site'),
          });
      }
    });
  }

  deleteSite(site: CustomerSite): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete Site',
        message: `Are you sure you want to delete site "${site.siteAddressCode}"?`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api
          .delete(`/customers/${this.customerId}/sites/${site.siteId}`)
          .subscribe({
            next: () => {
              this.notification.success('Site deleted successfully');
              this.loadSites();
            },
            error: () => this.notification.error('Failed to delete site'),
          });
      }
    });
  }
}
