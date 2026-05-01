import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuService } from '../../../core/services/menu.service';
import { EnquiryDetailsComponent } from '../enquiry-details/enquiry-details.component';
import { AssetUploadComponent } from '../../assets/asset-upload/asset-upload.component';
import { EnquiryFollowUpComponent } from '../enquiry-followup/enquiry-followup.component';
import { HandoverDialogComponent } from '../../../shared/components/handover-dialog/handover-dialog.component';
import { ServerSearchSelectComponent } from '../../../shared/components/server-search-select/server-search-select.component';

interface Contact {
  customerContactId: number;
  contactPersonName: string;
  personalEmail?: string;
  personalPhone?: string;
}

interface Site {
  siteId: number;
  siteAddressCode: string;
  addressLine?: string;
  dist?: string;
  state?: string;
}

@Component({
  selector: 'app-enquiry-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatDatepickerModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatDividerModule,
    MatTabsModule,
    MatProgressBarModule,
    MatDialogModule,
    MatTooltipModule,
    EnquiryDetailsComponent,
    AssetUploadComponent,
    EnquiryFollowUpComponent,
    ServerSearchSelectComponent,
  ],
  template: `
    <div class="enquiry-form-container">
      <!-- Page Header -->
      <mat-card class="header-card">
        <mat-card-header>
          <button mat-icon-button (click)="goBack()" matTooltip="Go Back">
            <mat-icon>arrow_back</mat-icon>
          </button>
          <div class="header-text">
            <mat-card-title>{{ isEditMode ? 'Edit Enquiry' : 'New Enquiry' }}</mat-card-title>
            <mat-card-subtitle *ngIf="isEditMode && enquiryNo">
              Enquiry No: {{ enquiryNo }}
            </mat-card-subtitle>
          </div>
          <span class="spacer" style="flex:1"></span>
          <span *ngIf="isEditMode && enquiryStatus" class="status-badge"
            [ngClass]="'status-' + (enquiryStatus || '').toLowerCase().replace(' ', '-')">
            {{ enquiryStatus }}
          </span>

          <!-- New → [Reject] [Handover] -->
          <button mat-stroked-button color="warn"
            *ngIf="isEditMode && enquiryStatus === 'New'"
            (click)="rejectEnquiry()"
            matTooltip="Reject this enquiry">
            <mat-icon>cancel</mat-icon> Reject
          </button>
          <button mat-stroked-button *ngIf="isEditMode && canTransferOwnership && enquiryStatus === 'New'"
            (click)="openHandover()"
            matTooltip="Transfer ownership to another user">
            <mat-icon>swap_horiz</mat-icon> Handover
          </button>

          <!-- Reject / Expired → [Renew] (requires canApprove permission) -->
          <button mat-raised-button color="primary"
            *ngIf="isEditMode && canRenew && (enquiryStatus === 'Reject' || enquiryStatus === 'Expired')"
            (click)="renewEnquiry()"
            matTooltip="Renew this enquiry — set back to New for editing">
            <mat-icon>refresh</mat-icon> Renew
          </button>
        </mat-card-header>
        <mat-progress-bar *ngIf="isSaving" mode="indeterminate"></mat-progress-bar>
      </mat-card>

      <!-- Form Card -->
      <mat-card class="form-card">
        <mat-card-content>
          <form [formGroup]="enquiryForm" (ngSubmit)="saveEnquiry()" class="enquiry-form">

            <div class="form-row">
              <!-- Customer (server-side search, scales to 50k+ rows) -->
              <div class="form-field-lg">
                <app-server-search-select
                  endpoint="/customers/search"
                  label="Customer *"
                  placeholder="Type customer name or code..."
                  formControlName="customerId"
                  [required]="true"
                  (selectionChange)="onCustomerChange($event?.id || null)">
                </app-server-search-select>
                <div class="field-error" *ngIf="enquiryForm.get('customerId')?.hasError('required') && enquiryForm.get('customerId')?.touched">
                  Customer is required
                </div>
              </div>

              <!-- User Code (only for select_code mode) -->
              <mat-form-field appearance="outline" class="form-field-md" *ngIf="numGenMode === 'select_code'">
                <mat-label>Generate No. Under</mat-label>
                <mat-select formControlName="codeUserId">
                  @for (u of ownCodeUsers; track u.userId) {
                    <mat-option [value]="u.userId">{{ u.userName }} ({{ u.userCode }})</mat-option>
                  }
                </mat-select>
                <mat-hint>Select whose code to use in the number</mat-hint>
              </mat-form-field>

              <!-- Enquiry No (locked unless canEditNumber permission) -->
              <mat-form-field appearance="outline" class="form-field-md">
                <mat-label>Enquiry No</mat-label>
                <input matInput formControlName="enqNo"
                  [placeholder]="canEditNumber ? 'Auto-generated if blank' : 'Auto-generated'"
                  [readonly]="!canEditNumber" />
                <mat-icon matSuffix *ngIf="!canEditNumber" matTooltip="Locked – no permission to edit">lock</mat-icon>
              </mat-form-field>

              <!-- Enquiry Date -->
              <mat-form-field appearance="outline" class="form-field-md">
                <mat-label>Enquiry Date *</mat-label>
                <input matInput [matDatepicker]="enqDatePicker" formControlName="enqDate" />
                <mat-datepicker-toggle matIconSuffix [for]="enqDatePicker"></mat-datepicker-toggle>
                <mat-datepicker #enqDatePicker></mat-datepicker>
                <mat-error *ngIf="enquiryForm.get('enqDate')?.hasError('required')">
                  Date is required
                </mat-error>
              </mat-form-field>
            </div>

            <div class="form-row">
              <!-- Contact -->
              <mat-form-field appearance="outline" class="form-field-md">
                <mat-label>Contact Person</mat-label>
                <mat-select formControlName="customerContactId" [disabled]="!contacts.length">
                  @for (c of contacts; track c.customerContactId) {
                    <mat-option [value]="c.customerContactId">{{ c.contactPersonName }}</mat-option>
                  }
                </mat-select>
                <mat-hint *ngIf="!contacts.length && enquiryForm.get('customerId')?.value">
                  No contacts found for this customer
                </mat-hint>
              </mat-form-field>

              <!-- Site -->
              <mat-form-field appearance="outline" class="form-field-md">
                <mat-label>Site / Delivery Location</mat-label>
                <mat-select formControlName="siteId" [disabled]="!sites.length">
                  @for (s of sites; track s.siteId) {
                    <mat-option [value]="s.siteId">{{ getSiteLabel(s) }}</mat-option>
                  }
                </mat-select>
                <mat-hint *ngIf="!sites.length && enquiryForm.get('customerId')?.value">
                  No sites found for this customer
                </mat-hint>
              </mat-form-field>

              <!-- Enquiry Mode -->
              <mat-form-field appearance="outline" class="form-field-sm">
                <mat-label>Enquiry Mode *</mat-label>
                <mat-select formControlName="enqMode">
                  <mat-option value="EMAIL">Email</mat-option>
                  <mat-option value="PHONE">Phone</mat-option>
                  <mat-option value="WALK_IN">Walk-in</mat-option>
                  <mat-option value="ONLINE">Online</mat-option>
                  <mat-option value="REFERRAL">Referral</mat-option>
                </mat-select>
                <mat-error *ngIf="enquiryForm.get('enqMode')?.hasError('required')">
                  Mode is required
                </mat-error>
              </mat-form-field>

              <!-- Validity Days -->
              <mat-form-field appearance="outline" class="form-field-sm">
                <mat-label>Validity (Days)</mat-label>
                <input matInput type="number" formControlName="validityDays" min="1" />
              </mat-form-field>
            </div>

            <div class="form-row">
              <!-- Description -->
              <mat-form-field appearance="outline" class="form-field-full">
                <mat-label>Description / Remarks</mat-label>
                <textarea matInput formControlName="description" rows="3"
                  placeholder="Enter enquiry details, special requirements, or remarks...">
                </textarea>
              </mat-form-field>
            </div>

            <!-- Loading spinner for customer-related data -->
            <div *ngIf="isLoadingCustomerData" class="customer-loading">
              <mat-spinner diameter="24"></mat-spinner>
              <span>Loading customer data...</span>
            </div>

            <!-- Form Actions -->
            <mat-divider class="form-divider"></mat-divider>
            <div class="form-actions">
              <button mat-stroked-button type="button" (click)="goBack()">
                <mat-icon>cancel</mat-icon> Cancel
              </button>
              <button mat-raised-button color="primary" type="submit"
                *ngIf="!isEnquiryLocked"
                [disabled]="enquiryForm.invalid || isSaving">
                <mat-spinner *ngIf="isSaving" diameter="20"></mat-spinner>
                <mat-icon *ngIf="!isSaving">save</mat-icon>
                {{ isSaving ? 'Saving...' : (isEditMode ? 'Update Enquiry' : 'Save Enquiry') }}
              </button>
            </div>
          </form>
        </mat-card-content>
      </mat-card>

      <!-- Details & Costing Tabs — shown only after save -->
      <mat-card *ngIf="savedEnquiryId" class="tabs-card"
        [class.locked-view]="isEnquiryLocked">
        <mat-card-content>
          <div *ngIf="isEnquiryLocked" class="locked-banner">
            <mat-icon>lock</mat-icon>
            This enquiry is <strong>{{ enquiryStatus }}</strong> — data is view-only.
          </div>
          <mat-tab-group animationDuration="200ms" dynamicHeight>
            <mat-tab label="Line Items">
              <div class="tab-content">
                <app-enquiry-details [enqId]="savedEnquiryId"></app-enquiry-details>
              </div>
            </mat-tab>
            <mat-tab label="Follow-Ups">
              <div class="tab-content">
                <app-enquiry-followup [enqId]="savedEnquiryId"></app-enquiry-followup>
              </div>
            </mat-tab>
            <mat-tab label="Attachments">
              <div class="tab-content">
                <app-asset-upload [enqid]="savedEnquiryId!"></app-asset-upload>
              </div>
            </mat-tab>
          </mat-tab-group>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .enquiry-form-container {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .header-card mat-card-header {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .locked-banner {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 16px; margin-bottom: 12px; border-radius: 6px;
      background: #fff8e1; color: #f57f17; font-size: 13px;
      border: 1px solid #ffecb3;
      mat-icon { font-size: 18px; width: 18px; height: 18px; }
    }

    /* Hide add/edit/delete buttons inside locked sub-resources */
    :host ::ng-deep .locked-view button[color="primary"],
    :host ::ng-deep .locked-view button[color="warn"],
    :host ::ng-deep .locked-view button[mat-raised-button],
    :host ::ng-deep .locked-view .upload-area,
    :host ::ng-deep .locked-view .followup-toolbar button,
    :host ::ng-deep .locked-view .sites-toolbar button,
    :host ::ng-deep .locked-view .action-btn {
      display: none !important;
    }

    .header-text {
      display: flex;
      flex-direction: column;
    }

    .form-card mat-card-content {
      padding-top: 16px;
    }

    .enquiry-form {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .form-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: flex-start;
    }

    .form-field-sm  { flex: 1 1 140px; min-width: 120px; }
    .form-field-md  { flex: 1 1 200px; min-width: 170px; }
    .form-field-lg  { flex: 2 1 280px; min-width: 220px; }
    .form-field-full { flex: 1 1 100%; }

    .field-error {
      color: var(--snm-error, #d32f2f);
      font-size: 12px;
      margin-top: -14px;
      margin-bottom: 6px;
      padding-left: 4px;
    }

    .customer-loading {
      display: flex;
      align-items: center;
      gap: 8px;
      color: #616161;
      font-size: 13px;
    }

    .form-divider {
      margin: 16px 0 12px;
    }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .form-actions button mat-spinner {
      display: inline-block;
      margin-right: 6px;
    }

    .tabs-card mat-card-content {
      padding: 0;
    }

    .tab-content {
      padding: 16px 0;
    }
  `],
})
export class EnquiryFormComponent implements OnInit {
  isEditMode = false;
  enquiryId: number | null = null;
  savedEnquiryId: number | null = null;
  enquiryNo: string | null = null;

  isSaving = false;
  isLoadingCustomerData = false;

  enquiryForm: FormGroup;
  contacts: Contact[] = [];
  sites: Site[] = [];
  numGenMode: string = 'own_code';
  ownCodeUsers: { userId: number; userName: string; userCode: string }[] = [];
  canEditNumber = false;
  canTransferOwnership = false;
  canRenew = false;
  currentOwnerUserId: number | null = null;
  enquiryStatus: string | null = null;
  isEnquiryLocked = false;

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private menuService: MenuService,
    private dialog: MatDialog,
  ) {
    this.enquiryForm = this.fb.group({
      customerId: [null, Validators.required],
      enqNo: [''],
      enqDate: [new Date(), Validators.required],
      customerContactId: [null],
      siteId: [null],
      enqMode: ['EMAIL', Validators.required],
      validityDays: [30],
      description: [''],
      codeUserId: [null],
    });
  }

  ngOnInit(): void {
    this.canEditNumber = this.menuService.hasPermission('Enquiries', 'canEditNumber');
    this.canTransferOwnership = this.menuService.hasPermission('Enquiries', 'canTransferOwnership');
    this.canRenew = this.menuService.hasPermission('Enquiries', 'canApprove')
                 || this.menuService.hasPermission('Enquiries', 'canEdit');
    this.loadNumGenMode();
    // Customer list no longer pre-loaded — server-search component loads on demand

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam && idParam !== 'new') {
      this.isEditMode = true;
      this.enquiryId = +idParam;
      this.savedEnquiryId = this.enquiryId;
      this.loadEnquiry(this.enquiryId);
    }
  }

  loadNumGenMode(): void {
    const userData = JSON.parse(localStorage.getItem('snm_user_data') || '{}');
    this.numGenMode = userData.numGenMode || 'own_code';
    if (this.numGenMode === 'select_code') {
      this.apiService.get<any[]>('/users/own-code-users').subscribe({
        next: (users) => (this.ownCodeUsers = users),
      });
    }
  }

  loadEnquiry(id: number): void {
    this.apiService.get<any>(`/enquiries/${id}`).subscribe({
      next: (data) => {
        this.enquiryNo = data.enqNo;
        this.currentOwnerUserId = data.ownerUserId ?? null;
        this.enquiryStatus = data.status || 'New';
        this.enquiryForm.patchValue({
          customerId: data.customerId,
          enqNo: data.enqNo,
          enqDate: data.enqDate ? new Date(data.enqDate) : null,
          customerContactId: data.customerContactId,
          siteId: data.siteId,
          enqMode: data.enqMode,
          validityDays: data.validityDays,
          description: data.description,
        });
        if (data.customerId) {
          this.loadContactsAndSites(data.customerId);
        }
        // Lock form if not in "New" status
        this.isEnquiryLocked = !!(this.enquiryStatus && this.enquiryStatus !== 'New');
        if (this.isEnquiryLocked) {
          this.enquiryForm.disable();
        } else {
          this.enquiryForm.enable();
        }
      },
      error: () => this.notificationService.error('Failed to load enquiry details'),
    });
  }

  onCustomerChange(customerId: number | null): void {
    this.enquiryForm.patchValue({ customerContactId: null, siteId: null });
    this.contacts = [];
    this.sites = [];
    if (customerId) {
      this.loadContactsAndSites(customerId);
    }
  }

  loadContactsAndSites(customerId: number): void {
    this.isLoadingCustomerData = true;
    const contacts$ = this.apiService.get<Contact[]>(`/customers/${customerId}/contacts`);
    const sites$ = this.apiService.get<Site[]>(`/customers/${customerId}/sites`);

    let completed = 0;
    const done = () => {
      completed++;
      if (completed === 2) this.isLoadingCustomerData = false;
    };

    contacts$.subscribe({
      next: (data) => { this.contacts = data; done(); },
      error: () => { this.notificationService.error('Failed to load contacts'); done(); },
    });

    sites$.subscribe({
      next: (data) => { this.sites = data; done(); },
      error: () => { this.notificationService.error('Failed to load sites'); done(); },
    });
  }

  saveEnquiry(): void {
    if (this.enquiryForm.invalid) {
      this.enquiryForm.markAllAsTouched();
      return;
    }

    this.isSaving = true;
    const payload = this.buildPayload();

    const request$ = this.isEditMode
      ? this.apiService.put<any>(`/enquiries/${this.enquiryId}`, payload)
      : this.apiService.post<any>('/enquiries', payload);

    request$.subscribe({
      next: (response) => {
        this.isSaving = false;
        const savedId = response?.enqid ?? response?.id ?? this.enquiryId;
        this.savedEnquiryId = savedId;
        this.enquiryNo = response?.enqNo ?? this.enquiryForm.get('enqNo')?.value;

        if (!this.isEditMode) {
          this.isEditMode = true;
          this.enquiryId = savedId;
          this.router.navigate(['/enquiries', savedId, 'edit'], { replaceUrl: true });
        }

        this.notificationService.success(
          this.isEditMode ? 'Enquiry updated successfully' : 'Enquiry created successfully'
        );
      },
      error: () => {
        this.isSaving = false;
        this.notificationService.error('Failed to save enquiry');
      },
    });
  }

  buildPayload(): any {
    const val = this.enquiryForm.value;
    return {
      ...val,
      enqDate: val.enqDate ? this.formatDate(val.enqDate) : null,
    };
  }

  formatDate(date: Date): string {
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  getSiteLabel(s: Site): string {
    const parts = [s.siteAddressCode];
    const addr = [s.addressLine, s.dist, s.state].filter(Boolean).join(', ');
    if (addr) parts.push(addr);
    return parts.join(' - ');
  }

  goBack(): void {
    this.router.navigate(['/enquiries']);
  }

  renewEnquiry(): void {
    if (!this.enquiryId) return;
    this.apiService.put(`/enquiries/${this.enquiryId}/renew`, {}).subscribe({
      next: () => {
        this.notificationService.success('Enquiry renewed — now editable.');
        this.loadEnquiry(this.enquiryId!);
      },
      error: (e: any) => this.notificationService.error(e?.error?.detail || 'Failed to renew.'),
    });
  }

  rejectEnquiry(): void {
    if (!this.enquiryId) return;
    this.apiService.put(`/enquiries/${this.enquiryId}/reject`, {}).subscribe({
      next: () => {
        this.notificationService.success('Enquiry rejected.');
        this.loadEnquiry(this.enquiryId!);
      },
      error: (e: any) => this.notificationService.error(e?.error?.detail || 'Failed to reject.'),
    });
  }

  openHandover(): void {
    if (!this.enquiryId) return;
    const ref = this.dialog.open(HandoverDialogComponent, {
      data: {
        entityType: 'enquiry',
        entityId: this.enquiryId,
        entityNo: this.enquiryNo ?? undefined,
        currentOwnerUserId: this.currentOwnerUserId ?? undefined,
      },
      width: '540px',
    });
    ref.afterClosed().subscribe(result => {
      if (result) {
        this.loadEnquiry(this.enquiryId!);
      }
    });
  }
}
