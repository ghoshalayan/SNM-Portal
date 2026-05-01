import { Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatTabsModule } from '@angular/material/tabs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { CustomerContactsComponent } from '../customer-contacts/customer-contacts.component';
import { CustomerSitesComponent } from '../customer-sites/customer-sites.component';

export interface CustomerClassification {
  classificationId: number;
  classificationName: string;
}

export interface CustomerDetail {
  customerId?: number;
  customerCode: string;
  customerName: string;
  GSTN: string;
  PAN: string;
  classificationId: number | null;
}

@Component({
  selector: 'app-customer-form',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatTabsModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatCardModule,
    MatDividerModule,
    CustomerContactsComponent,
    CustomerSitesComponent,
  ],
  template: `
    <div class="customer-form-container">
      <mat-card>
        <mat-card-header>
          <mat-card-title>
            <button mat-icon-button (click)="goBack()" class="back-btn" matTooltip="Back to list">
              <mat-icon>arrow_back</mat-icon>
            </button>
            {{ isEditMode ? 'Edit Customer' : 'New Customer' }}
          </mat-card-title>
        </mat-card-header>

        <mat-card-content>
          <div class="loading-overlay" *ngIf="isLoadingCustomer">
            <mat-spinner diameter="48"></mat-spinner>
            <p>Loading customer data...</p>
          </div>

          <mat-tab-group
            *ngIf="!isLoadingCustomer"
            animationDuration="200ms"
            class="customer-tabs"
          >

            <!-- TAB 1: Basic Info -->
            <mat-tab label="Basic Info">
              <div class="tab-content">
                <form [formGroup]="basicForm" class="basic-form">
                  <div class="form-row">
                    <mat-form-field appearance="outline" class="half-width">
                      <mat-label>Classification</mat-label>
                      <mat-select formControlName="classificationId">
                        <mat-option [value]="null">-- Select --</mat-option>
                        <mat-option *ngFor="let cls of classifications" [value]="cls.classificationId">
                          {{ cls.classificationName }}
                        </mat-option>
                      </mat-select>
                    </mat-form-field>

                    <mat-form-field appearance="outline" class="half-width">
                      <mat-label>Customer Code</mat-label>
                      <input matInput formControlName="customerCode" placeholder="Auto: TEMPxxxxx" />
                      <mat-hint>Leave blank to auto-generate (TEMP00001…). Editable later.</mat-hint>
                    </mat-form-field>
                  </div>

                  <div class="form-row">
                    <mat-form-field appearance="outline" class="full-width">
                      <mat-label>Customer Name *</mat-label>
                      <input matInput formControlName="customerName" />
                      <mat-error *ngIf="basicForm.get('customerName')?.hasError('required')">
                        Customer name is required
                      </mat-error>
                    </mat-form-field>
                  </div>

                  <div class="form-row">
                    <mat-form-field appearance="outline" class="half-width">
                      <mat-label>GSTN</mat-label>
                      <input matInput formControlName="GSTN" maxlength="15" />
                      <mat-hint>15-character GST number</mat-hint>
                    </mat-form-field>

                    <mat-form-field appearance="outline" class="half-width">
                      <mat-label>PAN</mat-label>
                      <input matInput formControlName="PAN" maxlength="10" />
                      <mat-hint>10-character PAN</mat-hint>
                    </mat-form-field>
                  </div>

                  <div class="tab-actions">
                    <button mat-stroked-button type="button" (click)="goBack()">
                      Cancel
                    </button>
                    <button
                      mat-raised-button
                      color="primary"
                      type="button"
                      (click)="saveBasicInfo()"
                      [disabled]="basicForm.invalid || isSavingBasic"
                    >
                      <mat-spinner *ngIf="isSavingBasic" diameter="18" class="btn-spinner"></mat-spinner>
                      <span *ngIf="!isSavingBasic">
                        <mat-icon>save</mat-icon>
                        {{ isEditMode ? 'Update' : 'Save & Continue' }}
                      </span>
                    </button>
                  </div>
                </form>
              </div>
            </mat-tab>

            <!-- TAB 2: Contacts -->
            <mat-tab [label]="'Contacts' + (isEditMode ? '' : ' (save basic info first)')" [disabled]="!savedCustomerId">
              <div class="tab-content">
                <app-customer-contacts [customerId]="savedCustomerId"></app-customer-contacts>
              </div>
            </mat-tab>

            <!-- TAB 3: Sites -->
            <mat-tab [label]="'Sites' + (isEditMode ? '' : ' (save basic info first)')" [disabled]="!savedCustomerId">
              <div class="tab-content">
                <app-customer-sites [customerId]="savedCustomerId" [customerCode]="basicForm.get('customerCode')?.value || ''"></app-customer-sites>
              </div>
            </mat-tab>

          </mat-tab-group>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .customer-form-container {
      padding: 24px;
      max-width: 900px;
      margin: 0 auto;
    }

    mat-card-header {
      margin-bottom: 8px;
    }

    mat-card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 20px;
      font-weight: 500;
    }

    .back-btn {
      margin-left: -8px;
    }

    .loading-overlay {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 48px;
      gap: 16px;
      color: rgba(0, 0, 0, 0.54);
    }

    .customer-tabs {
      margin-top: 8px;
    }

    .tab-content {
      padding: 24px 0;
    }

    .basic-form {
      max-width: 720px;
    }

    .form-row {
      display: flex;
      gap: 16px;
      margin-bottom: 8px;
    }

    .half-width {
      flex: 1;
    }

    .full-width {
      flex: 1;
    }

    .tab-actions {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
      margin-top: 24px;
      padding-top: 16px;
      border-top: 1px solid rgba(0, 0, 0, 0.12);
    }

    .btn-spinner {
      display: inline-block;
      margin-right: 8px;
    }
  `],
})
export class CustomerFormComponent implements OnInit {
  isEditMode = false;
  routeId: string | null = null;
  savedCustomerId: number | null = null;

  basicForm!: FormGroup;
  classifications: CustomerClassification[] = [];

  isLoadingCustomer = false;
  isSavingBasic = false;

  private destroyRef = inject(DestroyRef);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private fb: FormBuilder,
    private api: ApiService,
    private notification: NotificationService
  ) {}

  ngOnInit(): void {
    this.buildForm();
    this.loadClassifications();

    this.routeId = this.route.snapshot.paramMap.get('id');
    this.isEditMode = !!this.routeId && this.routeId !== 'new';

    if (this.isEditMode && this.routeId) {
      this.savedCustomerId = Number(this.routeId);
      this.loadCustomer(this.savedCustomerId);
    }
  }

  buildForm(): void {
    this.basicForm = this.fb.group({
      classificationId: [null],
      // Optional; backend auto-generates `TEMP00001`-style code if blank
      customerCode: [''],
      customerName: ['', Validators.required],
      GSTN: [''],
      PAN: [''],
    });
  }

  loadClassifications(): void {
    this.api.get<CustomerClassification[]>('/masters/customer-classifications')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => (this.classifications = data),
        error: () => this.notification.error('Failed to load classifications'),
      });
  }

  loadCustomer(id: number): void {
    this.isLoadingCustomer = true;
    this.api.get<CustomerDetail>(`/customers/${id}`).subscribe({
      next: (customer) => {
        this.basicForm.patchValue({
          classificationId: customer.classificationId,
          customerCode: customer.customerCode,
          customerName: customer.customerName,
          GSTN: customer.GSTN,
          PAN: customer.PAN,
        });
        this.isLoadingCustomer = false;
      },
      error: () => {
        this.notification.error('Failed to load customer data');
        this.isLoadingCustomer = false;
      },
    });
  }

  saveBasicInfo(): void {
    if (this.basicForm.invalid) return;
    this.isSavingBasic = true;
    const payload = this.basicForm.value;

    if (this.isEditMode && this.savedCustomerId) {
      this.api.put<CustomerDetail>(`/customers/${this.savedCustomerId}`, payload).subscribe({
        next: () => {
          this.notification.success('Customer updated successfully');
          this.isSavingBasic = false;
        },
        error: () => {
          this.notification.error('Failed to update customer');
          this.isSavingBasic = false;
        },
      });
    } else {
      this.api.post<CustomerDetail>('/customers', payload).subscribe({
        next: (created) => {
          this.notification.success('Customer created successfully');
          this.isSavingBasic = false;
          if (created.customerId) {
            this.savedCustomerId = created.customerId;
            this.isEditMode = true;
            this.router.navigate(['/customers', created.customerId, 'edit'], { replaceUrl: true });
          }
        },
        error: () => {
          this.notification.error('Failed to create customer');
          this.isSavingBasic = false;
        },
      });
    }
  }

  goBack(): void {
    this.router.navigate(['/customers']);
  }
}
