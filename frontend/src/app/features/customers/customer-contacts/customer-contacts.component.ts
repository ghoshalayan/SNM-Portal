import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
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
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { Inject } from '@angular/core';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { SearchFilterPipe } from '../../../shared/pipes/search-filter.pipe';

export interface CustomerContact {
  id?: number;
  customerId?: number;
  contactTypeId: number | null;
  contactTypeName?: string;
  contactPersonName: string;
  designation: string;
  personalPhone: string;
  personalEmail: string;
  officePhone: string;
  officeEmail: string;
  address: string;
  country: string;
  state: string;
  dist: string;
  birthday: string | null;
  anniversary: string | null;
}

interface ContactType {
  contactTypeId: number;
  contactType: string;
}

@Component({
  selector: 'app-contact-dialog',
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
    MatDatepickerModule,
    MatNativeDateModule,
    SearchFilterPipe,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.contact?.id ? 'Edit Contact' : 'Add Contact' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="contact-form">
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Contact Type *</mat-label>
            <mat-select formControlName="contactTypeId">
              <mat-option *ngFor="let ct of contactTypes" [value]="ct.contactTypeId">
                {{ ct.contactType }}
              </mat-option>
            </mat-select>
            <mat-error *ngIf="form.get('contactTypeId')?.hasError('required')">Required</mat-error>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Contact Person Name *</mat-label>
            <input matInput formControlName="contactPersonName" />
            <mat-error *ngIf="form.get('contactPersonName')?.hasError('required')">Required</mat-error>
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Designation</mat-label>
            <input matInput formControlName="designation" />
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Personal Phone</mat-label>
            <input matInput formControlName="personalPhone" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Personal Email</mat-label>
            <input matInput formControlName="personalEmail" type="email" />
            <mat-error *ngIf="form.get('personalEmail')?.hasError('email')">Invalid email</mat-error>
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Office Phone</mat-label>
            <input matInput formControlName="officePhone" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Office Email</mat-label>
            <input matInput formControlName="officeEmail" type="email" />
            <mat-error *ngIf="form.get('officeEmail')?.hasError('email')">Invalid email</mat-error>
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
            <mat-label>Address</mat-label>
            <input matInput formControlName="address" />
          </mat-form-field>
        </div>

        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Birthday</mat-label>
            <input matInput [matDatepicker]="bdPicker" formControlName="birthday" />
            <mat-datepicker-toggle matIconSuffix [for]="bdPicker"></mat-datepicker-toggle>
            <mat-datepicker #bdPicker></mat-datepicker>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Anniversary</mat-label>
            <input matInput [matDatepicker]="annPicker" formControlName="anniversary" />
            <mat-datepicker-toggle matIconSuffix [for]="annPicker"></mat-datepicker-toggle>
            <mat-datepicker #annPicker></mat-datepicker>
          </mat-form-field>
        </div>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid">
        {{ data.contact?.id ? 'Update' : 'Add' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .contact-form {
      min-width: 760px;
      padding: 8px 0;
    }
    .form-row {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }
    .form-row > mat-form-field { min-width: 220px; }
    .half-width {
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
  `],
})
export class ContactDialogComponent implements OnInit {
  form: FormGroup;
  countries: any[] = [];
  states: any[] = [];
  districts: any[] = [];
  allAccess = false;
  private myLocations: any = null;
  contactTypes: ContactType[] = [];
  countrySearch = '';
  stateSearch = '';
  distSearch = '';

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private dialogRef: MatDialogRef<ContactDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { contact: CustomerContact | null }
  ) {
    const c = data.contact;
    this.form = this.fb.group({
      contactTypeId: [c?.contactTypeId ?? null, Validators.required],
      contactPersonName: [c?.contactPersonName ?? '', Validators.required],
      designation: [c?.designation ?? ''],
      address: [c?.address ?? ''],
      personalPhone: [c?.personalPhone ?? ''],
      personalEmail: [c?.personalEmail ?? '', Validators.email],
      officePhone: [c?.officePhone ?? ''],
      officeEmail: [c?.officeEmail ?? '', Validators.email],
      country: [c?.country ?? ''],
      state: [c?.state ?? ''],
      dist: [c?.dist ?? ''],
      birthday: [c?.birthday ? new Date(c.birthday) : null],
      anniversary: [c?.anniversary ? new Date(c.anniversary) : null],
    });
  }

  ngOnInit(): void {
    this.loadContactTypes();
    this.loadMyLocations();
  }

  loadContactTypes(): void {
    this.api.get<ContactType[]>('/masters/contact-types').subscribe({
      next: (data) => (this.contactTypes = data),
    });
  }

  loadMyLocations(): void {
    this.api.get<any>('/users/my-locations').subscribe({
      next: (loc) => {
        this.myLocations = loc;
        this.allAccess = loc.allAccess;
        this.countries = loc.countries || [];

        const c = this.data.contact;
        if (c?.country) {
          // Country stored on record
          this.onCountryChange(c.country, false);
        } else if (c?.state) {
          // Reverse-lookup country from state
          const found = this.countries.find((ct: any) =>
            ct.states?.some((s: any) => s.StateName === c.state)
          );
          if (found) {
            this.form.get('country')?.setValue(found.countryName);
            this.onCountryChange(found.countryName, false);
          }
        } else if (this.countries.length === 1) {
          // Auto-select if only one country
          this.form.get('country')?.setValue(this.countries[0].countryName);
          this.onCountryChange(this.countries[0].countryName, false);
        }
        if (c?.state) this.onStateChange(c.state, false);
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
      const val = { ...this.form.value };
      // Format dates as YYYY-MM-DD for the backend
      if (val.birthday instanceof Date) {
        const b = val.birthday;
        val.birthday = `${b.getFullYear()}-${String(b.getMonth()+1).padStart(2,'0')}-${String(b.getDate()).padStart(2,'0')}`;
      }
      if (val.anniversary instanceof Date) {
        const a = val.anniversary;
        val.anniversary = `${a.getFullYear()}-${String(a.getMonth()+1).padStart(2,'0')}-${String(a.getDate()).padStart(2,'0')}`;
      }
      this.dialogRef.close(val);
    }
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}

@Component({
  selector: 'app-customer-contacts',
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
    <div class="contacts-container">
      <div class="contacts-toolbar">
        <span class="contacts-title">Contacts</span>
        <button
          mat-raised-button
          color="primary"
          (click)="openDialog(null)"
          [disabled]="!customerId"
        >
          <mat-icon>person_add</mat-icon>
          Add Contact
        </button>
      </div>

      <div class="loading-wrap" *ngIf="isLoading">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div class="table-wrapper" *ngIf="!isLoading">
        <table mat-table [dataSource]="dataSource" class="contacts-table">

          <ng-container matColumnDef="contactType">
            <th mat-header-cell *matHeaderCellDef>Type</th>
            <td mat-cell *matCellDef="let row">{{ row.contactTypeName || '—' }}</td>
          </ng-container>

          <ng-container matColumnDef="contactPersonName">
            <th mat-header-cell *matHeaderCellDef>Name</th>
            <td mat-cell *matCellDef="let row">{{ row.contactPersonName }}</td>
          </ng-container>

          <ng-container matColumnDef="designation">
            <th mat-header-cell *matHeaderCellDef>Designation</th>
            <td mat-cell *matCellDef="let row">{{ row.designation }}</td>
          </ng-container>

          <ng-container matColumnDef="personalPhone">
            <th mat-header-cell *matHeaderCellDef>Personal Phone</th>
            <td mat-cell *matCellDef="let row">{{ row.personalPhone }}</td>
          </ng-container>

          <ng-container matColumnDef="officePhone">
            <th mat-header-cell *matHeaderCellDef>Office Phone</th>
            <td mat-cell *matCellDef="let row">{{ row.officePhone }}</td>
          </ng-container>

          <ng-container matColumnDef="state">
            <th mat-header-cell *matHeaderCellDef>State</th>
            <td mat-cell *matCellDef="let row">{{ row.state }}</td>
          </ng-container>

          <ng-container matColumnDef="birthday">
            <th mat-header-cell *matHeaderCellDef>Birthday</th>
            <td mat-cell *matCellDef="let row">{{ row.birthday ? (row.birthday | date:'dd-MM') : '—' }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button
                mat-icon-button
                color="primary"
                matTooltip="Edit Contact"
                (click)="openDialog(row)"
              >
                <mat-icon>edit</mat-icon>
              </button>
              <button
                mat-icon-button
                color="warn"
                matTooltip="Delete Contact"
                (click)="deleteContact(row)"
              >
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>

          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data-cell" [attr.colspan]="displayedColumns.length">
              No contacts found. Click "Add Contact" to add one.
            </td>
          </tr>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .contacts-container {
      padding: 16px 0;
    }

    .contacts-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .contacts-title {
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

    .contacts-table {
      width: 100%;
    }

    .no-data-cell {
      text-align: center;
      padding: 24px;
      color: rgba(0, 0, 0, 0.54);
    }
  `],
})
export class CustomerContactsComponent implements OnInit, OnChanges {
  @Input() customerId!: number | null;

  displayedColumns: string[] = [
    'contactType',
    'contactPersonName',
    'designation',
    'personalPhone',
    'officePhone',
    'state',
    'birthday',
    'actions',
  ];

  dataSource = new MatTableDataSource<CustomerContact>([]);
  isLoading = false;

  constructor(
    private api: ApiService,
    private notification: NotificationService,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    if (this.customerId) {
      this.loadContacts();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['customerId'] && this.customerId) {
      this.loadContacts();
    }
  }

  loadContacts(): void {
    if (!this.customerId) return;
    this.isLoading = true;
    this.api.get<any[]>(`/customers/${this.customerId}/contacts`).subscribe({
      next: (data) => {
        this.dataSource.data = data.map(c => ({
          ...c,
          id: c.customerContactId ?? c.id,
          contactTypeName: c.contact_type?.contactType || c.contactTypeName || '',
        }));
        this.isLoading = false;
      },
      error: () => {
        this.notification.error('Failed to load contacts');
        this.isLoading = false;
      },
    });
  }

  openDialog(contact: CustomerContact | null): void {
    const dialogRef = this.dialog.open(ContactDialogComponent, {
      data: { contact },
      width: '880px',
      maxWidth: '95vw',
      disableClose: true,
    });

    dialogRef.afterClosed().subscribe((result: Partial<CustomerContact> | null) => {
      if (!result) return;

      if (contact?.id) {
        this.api
          .put<CustomerContact>(`/customers/${this.customerId}/contacts/${contact.id}`, result)
          .subscribe({
            next: () => {
              this.notification.success('Contact updated successfully');
              this.loadContacts();
            },
            error: () => this.notification.error('Failed to update contact'),
          });
      } else {
        this.api
          .post<CustomerContact>(`/customers/${this.customerId}/contacts`, result)
          .subscribe({
            next: () => {
              this.notification.success('Contact added successfully');
              this.loadContacts();
            },
            error: () => this.notification.error('Failed to add contact'),
          });
      }
    });
  }

  deleteContact(contact: CustomerContact): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete Contact',
        message: `Are you sure you want to delete contact "${contact.contactPersonName}"?`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api
          .delete(`/customers/${this.customerId}/contacts/${contact.id}`)
          .subscribe({
            next: () => {
              this.notification.success('Contact deleted successfully');
              this.loadContacts();
            },
            error: () => this.notification.error('Failed to delete contact'),
          });
      }
    });
  }
}
