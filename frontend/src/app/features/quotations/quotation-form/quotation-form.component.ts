import { Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatTabsModule } from '@angular/material/tabs';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { HandoverDialogComponent } from '../../../shared/components/handover-dialog/handover-dialog.component';
import { ServerSearchSelectComponent } from '../../../shared/components/server-search-select/server-search-select.component';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuService } from '../../../core/services/menu.service';
import { QuotationDetailsComponent } from '../quotation-details/quotation-details.component';
import { QuotationTncComponent } from '../quotation-tnc/quotation-tnc.component';
import { QuotationVersionHistoryComponent } from '../quotation-version-history/quotation-version-history.component';
import { QuotationFollowUpComponent } from '../quotation-followup/quotation-followup.component';
import { AssetUploadComponent } from '../../assets/asset-upload/asset-upload.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { QuotationViabilityComponent } from '../quotation-viability/quotation-viability.component';
import { QuotationStepperComponent } from '../quotation-stepper/quotation-stepper.component';
import { QuotationAnnexureComponent } from '../quotation-annexure/quotation-annexure.component';

export interface Enquiry {
  enqid: number;
  enqNo: string;
  customerId: number;
  customerName?: string;
  customerContactId?: number;
  siteId?: number;
}

export interface Customer {
  customerId: number;
  customerName: string;
}

export interface Contact {
  customerContactId: number;
  contactPersonName: string;
}

export interface Site {
  siteId: number;
  siteAddressCode: string;
  addressLine?: string;
  dist?: string;
  state?: string;
}

export interface DeliveryTerm {
  deliveryTermId: number;
  deliveryTerm: string;
}

export interface DeliveryMode {
  deliveryModeId: number;
  deliveryMode: string;
}

export interface VersionEntry {
  versionNo: number;
  quotDate: string;
  status: string;
  approvedBy: string;
}

@Component({
  selector: 'app-quotation-form',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatTabsModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    MatChipsModule,
    MatTableModule,
    MatTooltipModule,
    MatDialogModule,
    RouterModule,
    QuotationDetailsComponent,
    QuotationTncComponent,
    QuotationVersionHistoryComponent,
    QuotationFollowUpComponent,
    ServerSearchSelectComponent,
    AssetUploadComponent,
    QuotationViabilityComponent,
    QuotationStepperComponent,
    QuotationAnnexureComponent,
  ],
  template: `
    <div class="quotation-form-container" [class.wide-mode]="lineItemsExpanded">
      <!-- Header -->
      <div class="page-header">
        <button mat-icon-button (click)="goBack()" matTooltip="Back">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <h2>{{ isEditMode ? 'Edit Quotation' : 'New Quotation' }}</h2>
        <span class="spacer"></span>

        <ng-container *ngIf="quotationId">
          <!-- Status badge -->
          <span class="status-badge"
            [ngClass]="'status-' + (quotationStatus || 'draft').toLowerCase()">
            {{ quotationStatus || 'Draft' }}
          </span>

          <!--
            Action buttons per stage:
            Draft    → [Approve]
            Approved → [Matured (PO)] [Reject] [Revise]
            Reject   → [Revert to Approved]
            Matured  → (PO fields editable only)
            Revised  → (fully locked)
          -->

          <!-- Draft → Approve -->
          <button mat-raised-button color="primary"
            *ngIf="canApprove && quotationStatus === 'Draft'"
            (click)="approveQuotation()" [disabled]="saving">
            <mat-icon>check_circle</mat-icon> Approve
          </button>

          <!-- Approved → Matured (PO received) -->
          <button mat-raised-button
            [style.background]="poReadyToMature ? '#1b5e20' : '#9e9e9e'"
            style="color:#fff"
            *ngIf="canApprove && quotationStatus === 'Approved'"
            (click)="onClickMature()" [disabled]="saving || !poReadyToMature"
            [matTooltip]="poReadyToMature
              ? 'Mark as Matured — Purchase Order received'
              : 'Fill Customer PO No and PO Date in the PO card below to enable'">
            <mat-icon>{{ poReadyToMature ? 'verified' : 'lock' }}</mat-icon> Matured (PO)
          </button>

          <!-- Approved → Reject -->
          <button mat-stroked-button color="warn"
            *ngIf="canApprove && quotationStatus === 'Approved'"
            (click)="rejectQuotation()" [disabled]="saving">
            <mat-icon>cancel</mat-icon> Reject
          </button>

          <!-- Approved → Revise (creates new version, locks this one) -->
          <button mat-stroked-button color="accent"
            *ngIf="canRevise && quotationStatus === 'Approved'"
            (click)="reviseQuotation()" [disabled]="saving"
            matTooltip="Create a new revision (this version will be locked)">
            <mat-icon>content_copy</mat-icon> Revise
          </button>

          <!-- Reject → Revert to Approved -->
          <button mat-stroked-button
            *ngIf="canApprove && quotationStatus === 'Reject'"
            (click)="revertReject()" [disabled]="saving"
            matTooltip="Revert back to Approved">
            <mat-icon>undo</mat-icon> Revert to Approved
          </button>

          <!-- Handover (available on Draft & Approved) -->
          <button mat-stroked-button
            *ngIf="canTransferOwnership && (quotationStatus === 'Draft' || quotationStatus === 'Approved')"
            (click)="openHandover()" [disabled]="saving"
            matTooltip="Transfer ownership to another user">
            <mat-icon>swap_horiz</mat-icon> Handover
          </button>
        </ng-container>
      </div>

      <!-- Status timeline — rendered for saved quotations only -->
      <app-quotation-stepper
        *ngIf="quotationId && !loading"
        [quotationStatus]="quotationStatus"
        [viabilityStatus]="viabilityStatus"
        [versionNo]="versionNo"
        [parentQuotId]="parentQuotId">
      </app-quotation-stepper>

      <div *ngIf="loading" class="spinner-container">
        <mat-spinner diameter="48"></mat-spinner>
      </div>

      <mat-card *ngIf="!loading">
        <mat-card-content>
          <mat-tab-group [(selectedIndex)]="activeTab" animationDuration="200ms">

            <!-- Tab 1: Quotation Header -->
            <mat-tab label="Quotation Info & PO Details">
              <form [formGroup]="quotForm" class="quotation-form" (ngSubmit)="saveQuotation()">
                <div class="form-grid">

                  <!-- Enquiry (server-side search, scales to 50k+ rows) -->
                  <!-- excludeStatuses: hides enquiries already converted or rejected -->
                  <div class="grid-cell">
                    <app-server-search-select
                      endpoint="/enquiries/search"
                      label="Enquiry"
                      placeholder="Search enquiry by no..."
                      formControlName="enqid"
                      [extraParams]="enquiryPickerParams"
                      (selectionChange)="onEnquiryChange($event?.id || null)">
                    </app-server-search-select>
                  </div>

                  <!-- Customer (server-side search, locked when enquiry is selected) -->
                  <div class="grid-cell">
                    <app-server-search-select
                      endpoint="/customers/search"
                      label="Customer *"
                      placeholder="Search customer..."
                      formControlName="customerId"
                      [required]="true"
                      [disabled]="customerLocked"
                      (selectionChange)="onCustomerChange($event?.id || null)">
                    </app-server-search-select>
                    <div class="field-error" *ngIf="quotForm.get('customerId')?.hasError('required') && quotForm.get('customerId')?.touched">
                      Customer is required.
                    </div>
                    <div class="field-hint" *ngIf="customerLocked">Inherited from enquiry</div>
                  </div>

                  <!-- Contact -->
                  <mat-form-field appearance="outline">
                    <mat-label>Contact Person</mat-label>
                    <mat-select formControlName="customerContactId"
                      (openedChange)="onDropdownOpen($event, 'contact')"
                      panelClass="searchable-panel">
                      <div class="select-search" (click)="$event.stopPropagation()">
                        <mat-icon class="search-ico">search</mat-icon>
                        <input placeholder="Search contacts..."
                          [value]="search.contact"
                          (input)="search.contact = $any($event.target).value"
                          (keydown)="$event.stopPropagation()">
                      </div>
                      @for (c of filteredContacts(); track c.customerContactId) {
                        <mat-option [value]="c.customerContactId">{{ c.contactPersonName }}</mat-option>
                      }
                    </mat-select>
                  </mat-form-field>

                  <!-- Site / Delivery Location -->
                  <mat-form-field appearance="outline">
                    <mat-label>Site / Delivery Location</mat-label>
                    <mat-select formControlName="siteId"
                      (openedChange)="onDropdownOpen($event, 'site')"
                      panelClass="searchable-panel">
                      <div class="select-search" (click)="$event.stopPropagation()">
                        <mat-icon class="search-ico">search</mat-icon>
                        <input placeholder="Search sites..."
                          [value]="search.site"
                          (input)="search.site = $any($event.target).value"
                          (keydown)="$event.stopPropagation()">
                      </div>
                      @for (s of filteredSites(); track s.siteId) {
                        <mat-option [value]="s.siteId">{{ getSiteLabel(s) }}</mat-option>
                      }
                    </mat-select>
                    <mat-hint *ngIf="!sites.length && quotForm.get('customerId')?.value">
                      No sites found for this customer
                    </mat-hint>
                  </mat-form-field>

                  <!-- User Code (only for select_code mode) -->
                  <mat-form-field appearance="outline" *ngIf="numGenMode === 'select_code'">
                    <mat-label>Generate No. Under</mat-label>
                    <mat-select formControlName="codeUserId">
                      @for (u of ownCodeUsers; track u.userId) {
                        <mat-option [value]="u.userId">{{ u.userName }} ({{ u.userCode }})</mat-option>
                      }
                    </mat-select>
                    <mat-hint>Select whose code to use in the number</mat-hint>
                  </mat-form-field>

                  <!-- Quot No (locked unless canEditNumber permission) -->
                  <mat-form-field appearance="outline">
                    <mat-label>Quotation No</mat-label>
                    <input matInput formControlName="quotNo"
                      [placeholder]="canEditNumber ? 'Auto-generated if blank' : 'Auto-generated'"
                      [readonly]="!canEditNumber" />
                    <mat-icon matSuffix *ngIf="!canEditNumber" matTooltip="Locked – no permission to edit">lock</mat-icon>
                  </mat-form-field>

                  <!-- Quot Date -->
                  <mat-form-field appearance="outline">
                    <mat-label>Quotation Date</mat-label>
                    <input matInput [matDatepicker]="quotDatePicker" formControlName="quotDate" />
                    <mat-datepicker-toggle matSuffix [for]="quotDatePicker"></mat-datepicker-toggle>
                    <mat-datepicker #quotDatePicker></mat-datepicker>
                    <mat-error *ngIf="quotForm.get('quotDate')?.hasError('required')">
                      Date is required.
                    </mat-error>
                  </mat-form-field>

                  <!-- Subject (full width) -->
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Subject</mat-label>
                    <input matInput formControlName="subject" />
                    <mat-error *ngIf="quotForm.get('subject')?.hasError('required')">
                      Subject is required.
                    </mat-error>
                  </mat-form-field>

                  <!-- Delivery Term — required so the freight lock rule
                       has a definite term to evaluate against. -->
                  <mat-form-field appearance="outline">
                    <mat-label>Delivery Term *</mat-label>
                    <mat-select formControlName="deliveryTermId">
                      @for (t of deliveryTerms; track t.deliveryTermId) {
                        <mat-option [value]="t.deliveryTermId">{{ t.deliveryTerm }}</mat-option>
                      }
                    </mat-select>
                    <mat-error *ngIf="quotForm.get('deliveryTermId')?.hasError('required')">
                      Delivery term is required.
                    </mat-error>
                  </mat-form-field>

                  <!-- Delivery Mode — required and limited to Truck / Trailer
                       when the term is FOR; "No Mode" is the explicit
                       no-selection sentinel for non-FOR terms. -->
                  <mat-form-field appearance="outline">
                    <mat-label>Delivery Mode{{ isForDeliveryTerm ? ' *' : '' }}</mat-label>
                    <mat-select formControlName="deliveryModeId">
                      <mat-option [value]="null">No Mode</mat-option>
                      @for (m of deliveryModes; track m.deliveryModeId) {
                        <mat-option [value]="m.deliveryModeId">{{ m.deliveryMode }}</mat-option>
                      }
                    </mat-select>
                    <mat-error *ngIf="quotForm.get('deliveryModeId')?.hasError('forModeRequired')">
                      Choose Truck or Trailer when delivery term is FOR.
                      <ng-container *ngIf="quotForm.get('deliveryModeId')?.errors?.['modeName']">
                        (got: "{{ quotForm.get('deliveryModeId')?.errors?.['modeName'] }}")
                      </ng-container>
                    </mat-error>
                  </mat-form-field>

                  <!-- Ref Quot No -->
                  <mat-form-field appearance="outline">
                    <mat-label>Ref. Quotation No</mat-label>
                    <input matInput formControlName="refQuotNo" />
                  </mat-form-field>

                  <!-- Remarks (full width) -->
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Remarks</mat-label>
                    <textarea matInput formControlName="remarks" rows="3"></textarea>
                  </mat-form-field>
                </div>

                <div class="form-actions">
                  <button mat-stroked-button type="button" (click)="goBack()">Cancel</button>
                  <button mat-raised-button color="primary" type="submit" [disabled]="quotForm.invalid || saving">
                    <mat-spinner *ngIf="saving" diameter="18" class="inline-spinner"></mat-spinner>
                    {{ saving ? 'Saving...' : 'Save Quotation' }}
                  </button>
                </div>
              </form>
            </mat-tab>

            <!-- Tab 2: Details (line items) -->
            <mat-tab label="Working & Viability Sheet" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-details
                  *ngIf="quotationId"
                  [quotId]="quotationId"
                  [enqId]="quotForm.get('enqid')?.value"
                  [readOnly]="isLocked || isMatured"
                  [isForDeliveryTerm]="isForDeliveryTerm"
                  [deliveryModeName]="deliveryModeName"
                  (expandedChange)="onLineItemsExpand($event)">
                </app-quotation-details>
              </div>
            </mat-tab>

            <!-- Tab 3: Annexure (locked until viability is approved) -->
            <mat-tab [disabled]="!quotationId || !annexureTabUnlocked">
              <ng-template mat-tab-label>
                <mat-icon *ngIf="!annexureTabUnlocked" class="tab-lock-icon" matTooltip="Locked until viability is approved">lock</mat-icon>
                <span>Annexure</span>
              </ng-template>
              <div class="tab-content">
                <app-quotation-annexure
                  *ngIf="quotationId && annexureTabUnlocked"
                  [quotId]="quotationId"
                  [canApprove]="canApprove"
                  [canApproveAnnexure]="canApproveAnnexure"
                  [readOnly]="isLocked"
                  (stageChanged)="onSubStageChanged()">
                </app-quotation-annexure>
              </div>
            </mat-tab>

            <!-- Tab 4: Terms & Conditions -->
            <mat-tab label="Terms & Conditions" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-tnc
                  *ngIf="quotationId"
                  [quotId]="quotationId"
                  [readOnly]="isLocked || isMatured">
                </app-quotation-tnc>
              </div>
            </mat-tab>

            <!-- Tab 4: Follow-Ups -->
            <mat-tab label="Follow-Ups" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-followup
                  *ngIf="quotationId"
                  [quotId]="quotationId">
                </app-quotation-followup>
              </div>
            </mat-tab>

            <!-- Tab 5: Version History -->
            <mat-tab label="Version History" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-version-history
                  *ngIf="quotationId"
                  [quotId]="quotationId">
                </app-quotation-version-history>
              </div>
            </mat-tab>

          </mat-tab-group>
        </mat-card-content>
      </mat-card>

      <!-- PO Details card: attached to the Quotation Info tab only. -->
      <mat-card *ngIf="showPoCard() && activeTab === 0" class="po-card">
        <mat-card-header>
          <mat-card-title>
            <mat-icon class="po-title-icon">receipt_long</mat-icon>
            Purchase Order Details
          </mat-card-title>
          <mat-card-subtitle>
            Provide PO No and PO Date to unlock the <strong>Matured</strong> action. Attachment is optional.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <form [formGroup]="quotForm" class="po-form">
            <mat-form-field appearance="outline">
              <mat-label>Customer PO No *</mat-label>
              <input matInput formControlName="CustomerPONo" />
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Customer PO Date *</mat-label>
              <input matInput [matDatepicker]="poPicker" formControlName="CustomerPODate" />
              <mat-datepicker-toggle matSuffix [for]="poPicker"></mat-datepicker-toggle>
              <mat-datepicker #poPicker></mat-datepicker>
            </mat-form-field>

            <div class="po-actions">
              <button mat-raised-button color="primary" type="button"
                (click)="savePoDetails()" [disabled]="saving || !poDirty || !poEditable">
                <mat-icon>save</mat-icon> Save PO Details
              </button>
              <span *ngIf="poDirty" class="po-unsaved">Unsaved changes</span>
              <span *ngIf="!poEditable && !isLocked" class="po-frozen">
                <mat-icon class="po-frozen-icon">lock</mat-icon> Locked — quotation has progressed past Matured
              </span>
            </div>
          </form>

          <app-asset-upload
            *ngIf="quotationId"
            [quotId]="quotationId"
            category="po_document"
            title="PO Attachments"
            namePlaceholder="e.g. PO Scan, Amendment"
            [allowedExtensions]="['pdf','jpg','jpeg','png']"
            [maxSizeMb]="20"
            [compressImages]="true"
            [multiple]="false"
            [disabled]="!poEditable"
            hintText="Allowed: PDF, JPG, PNG · max 20 MB · images auto-compressed">
          </app-asset-upload>
        </mat-card-content>
      </mat-card>

      <!-- Viability Sheet card: attached to the Line Items tab only.
           Becomes read-only once we move past viability approval.
           Explicit quotationId check first so Angular narrows the type for quotId binding. -->
      <app-quotation-viability
        *ngIf="quotationId && showViabilityCard() && activeTab === 1"
        [quotId]="quotationId"
        [canApprove]="canApprove"
        [readOnly]="viabilityReadOnly"
        (stageChanged)="onSubStageChanged()">
      </app-quotation-viability>
    </div>
  `,
  styles: [`
    .quotation-form-container {
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
      transition: max-width 0.3s ease, padding 0.3s ease;
    }

    .quotation-form-container.wide-mode {
      max-width: 100%;
      padding: 12px;
    }

    .page-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
    }

    .no-enq-hint {
      display: flex !important; align-items: center; gap: 4px;
      color: #e65100; font-size: 12px;
      .hint-icon { font-size: 15px; width: 15px; height: 15px; }
      a { color: #1565c0; font-weight: 500; text-decoration: underline; cursor: pointer; }
    }

    .page-header h2 {
      margin: 0;
      font-size: 22px;
    }

    .spacer {
      flex: 1;
    }

    .spinner-container {
      display: flex;
      justify-content: center;
      padding: 48px;
    }

    .quotation-form {
      padding: 24px 0;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .full-width {
      grid-column: 1 / -1;
    }

    .grid-cell { display: flex; flex-direction: column; }
    .field-error {
      color: var(--snm-error, #d32f2f);
      font-size: 12px;
      padding: 4px 0 0 2px;
    }
    .field-hint {
      color: var(--snm-text-muted, rgba(0,0,0,.55));
      font-size: 11px;
      padding: 4px 0 0 2px;
    }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-top: 24px;
    }

    .tab-content {
      padding: 16px 0;
    }

    .inline-spinner {
      display: inline-block;
      margin-right: 8px;
    }

    @media (max-width: 768px) {
      .form-grid {
        grid-template-columns: 1fr;
      }
    }

    /* PO Details card (appears after approval) */
    .po-card { margin-top: 20px; }
    .po-card mat-card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 18px;
    }
    .po-title-icon { color: var(--snm-accent-dark, #3a6bb5); }
    .po-form {
      display: grid;
      grid-template-columns: 1fr 1fr auto;
      gap: 12px;
      align-items: start;
      margin: 16px 0 8px;
    }
    .po-form mat-form-field { width: 100%; }
    .po-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-top: 4px;
    }
    .po-unsaved {
      font-size: 12px;
      color: #e65100;
      font-style: italic;
    }
    .po-frozen {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: var(--snm-text-muted);
      font-style: italic;
    }
    .po-frozen-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    @media (max-width: 768px) {
      .po-form { grid-template-columns: 1fr; }
    }

    /* Lock icon inside a disabled tab label */
    .tab-lock-icon {
      font-size: 15px;
      width: 15px;
      height: 15px;
      margin-right: 6px;
      color: var(--snm-text-faint);
      vertical-align: middle;
    }
  `],
})
export class QuotationFormComponent implements OnInit {
  quotForm!: FormGroup;
  isEditMode = false;
  quotationId: number | null = null;
  quotationStatus = 'Draft';
  activeTab = 0;
  loading = false;
  saving = false;
  lineItemsExpanded = false;

  contacts: Contact[] = [];
  sites: Site[] = [];
  deliveryTerms: DeliveryTerm[] = [];
  deliveryModes: DeliveryMode[] = [];
  numGenMode: string = 'own_code';
  ownCodeUsers: { userId: number; userName: string; userCode: string }[] = [];
  customerLocked = false;
  canEditNumber = false;
  canApprove = false;
  canRevise = false;
  canTransferOwnership = false;
  /** Granted only to the Commercial HOD role. Gates the annexure
   *  approve button AND lets the holder edit annexures even after
   *  they're approved. */
  canApproveAnnexure = false;
  currentOwnerUserId: number | null = null;
  isLocked = false;
  isMatured = false;

  // Viability + versioning surface state — consumed by <app-quotation-stepper>
  viabilityStatus: 'Draft' | 'Approved' | null = null;
  versionNo = 1;
  parentQuotId: number | null = null;

  /** True when the currently-selected delivery term reads as 'FOR' (token
   *  match, case-insensitive). Drives the freight-cell lock on the line
   *  items grid — same logic as the backend helper in quotations.py. */
  get isForDeliveryTerm(): boolean {
    const id = this.quotForm.get('deliveryTermId')?.value;
    if (!id) return false;
    const term = this.deliveryTerms.find(t => t.deliveryTermId === id);
    if (!term?.deliveryTerm) return false;
    return term.deliveryTerm.trim().toLowerCase().split(/\s+/).includes('for');
  }

  /** Selected delivery mode's display name (e.g. 'Trailer' / 'Truck') —
   *  feeds the per-column lock decision in quotation-details. Returns
   *  empty string when nothing is selected. */
  get deliveryModeName(): string {
    const id = this.quotForm.get('deliveryModeId')?.value;
    if (!id) return '';
    const mode = this.deliveryModes.find(m => m.deliveryModeId === id);
    return mode?.deliveryMode || '';
  }

  /** Annexure tab opens once viability is approved (or further down the chain). */
  get annexureTabUnlocked(): boolean {
    return this.viabilityStatus === 'Approved'
      || this.quotationStatus === 'ViabilityApproved'
      || this.quotationStatus === 'AnnexureGenerated'
      || this.quotationStatus === 'AnnexureApproved';
  }

  // Local search for contact dropdown (loaded once per customer, small set)
  search = { contact: '', site: '' };

  // Enquiries already converted or rejected should not appear as source
  // options when creating a quotation. Already-linked enqids still resolve
  // via the id-lookup path on the backend.
  readonly enquiryPickerParams: Record<string, string> = {
    excludeStatuses: 'Quotation Prepared,Reject',
  };

  /** DestroyRef lets us scope RxJS subscriptions to the component's lifetime.
   *  Any observable piped through `takeUntilDestroyed(this.destroyRef)` is
   *  auto-unsubscribed when the component is torn down — plugging leaks in
   *  long-lived sessions. */
  private destroyRef = inject(DestroyRef);

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private menuService: MenuService,
    private dialog: MatDialog,
  ) { }

  ngOnInit(): void {
    this.canEditNumber = this.menuService.hasPermission('Quotations', 'canEditNumber');
    // canApprove/canRevise: grant if the dedicated flag OR basic canEdit is set
    // (backward compat for roles that don't have the RBAC v2 extended flags yet)
    this.canApprove = this.menuService.hasPermission('Quotations', 'canApprove')
      || this.menuService.hasPermission('Quotations', 'canEdit');
    this.canRevise = this.menuService.hasPermission('Quotations', 'canRevise')
      || this.menuService.hasPermission('Quotations', 'canEdit');
    this.canTransferOwnership = this.menuService.hasPermission('Quotations', 'canTransferOwnership');
    this.canApproveAnnexure = this.menuService.hasPermission('Quotations', 'canApproveAnnexure');
    this.buildForm();
    this.loadDropdowns();

    const id = this.route.snapshot.paramMap.get('id');
    if (id && id !== 'new') {
      this.isEditMode = true;
      this.quotationId = Number(id);
      this.loadQuotation(this.quotationId);
    }
  }

  buildForm(): void {
    this.quotForm = this.fb.group({
      enqid: [null],
      customerId: [null, Validators.required],
      customerContactId: [null],
      siteId: [null],
      quotNo: [''],
      quotDate: [new Date(), Validators.required],
      subject: ['', Validators.required],
      deliveryTermId: [null, Validators.required],
      deliveryModeId: [null, this.forModeValidator()],
      refQuotNo: [''],
      remarks: [''],
      CustomerPONo: [''],
      CustomerPODate: [null],
      codeUserId: [null],
    });

    // Whenever the delivery term changes, re-run the mode validator —
    // FOR requires a Truck/Trailer mode while other terms allow "No Mode".
    this.quotForm.get('deliveryTermId')!.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.quotForm.get('deliveryModeId')?.updateValueAndValidity());
  }

  /** Cross-field validator: when delivery term is FOR, the mode must be a
   *  real Truck / Trailer entry — null and "No Mode" both fail. The match
   *  is regex-based so common spellings ("Trailer", "Trailor", "By
   *  Trailer", "Trail", "Truck", "Trk") all resolve correctly. */
  private static readonly TRAILER_RE = /trail|trial/i;
  private static readonly TRUCK_RE = /truck|trk|lorr/i;
  private forModeValidator() {
    return (control: any) => {
      // Form may not be wired yet on first instantiation; bail safely.
      const form = control?.parent;
      if (!form) return null;
      const termId = form.get('deliveryTermId')?.value;
      if (!termId) return null;
      const term = this.deliveryTerms.find(t => t.deliveryTermId === termId);
      const isFor = !!term?.deliveryTerm
        && term.deliveryTerm.trim().toLowerCase().split(/\s+/).includes('for');
      if (!isFor) return null;
      const modeId = control.value;
      if (!modeId) return { forModeRequired: true, modeName: null };
      const mode = this.deliveryModes.find(m => m.deliveryModeId === modeId);
      const raw = (mode?.deliveryMode || '').trim();
      const name = raw.toLowerCase();
      if (!name) return { forModeRequired: true, modeName: '<unknown>' };
      if (
        !QuotationFormComponent.TRUCK_RE.test(name)
        && !QuotationFormComponent.TRAILER_RE.test(name)
      ) {
        return { forModeRequired: true, modeName: raw };
      }
      return null;
    };
  }

  loadDropdowns(): void {
    const userData = JSON.parse(localStorage.getItem('snm_user_data') || '{}');
    this.numGenMode = userData.numGenMode || 'own_code';
    if (this.numGenMode === 'select_code') {
      this.apiService.get<any[]>('/users/own-code-users')
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (users) => (this.ownCodeUsers = users),
        });
    }
    // Enquiries + Customers are loaded on-demand via <app-server-search-select> — no preload.
    this.apiService.get<DeliveryTerm[]>('/masters/delivery-terms')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.deliveryTerms = data;
          this.quotForm.get('deliveryModeId')?.updateValueAndValidity();
        },
        error: () => this.notificationService.error('Failed to load delivery terms.'),
      });

    this.apiService.get<DeliveryMode[]>('/masters/delivery-modes')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.deliveryModes = data;
          this.quotForm.get('deliveryModeId')?.updateValueAndValidity();
        },
        error: () => this.notificationService.error('Failed to load delivery modes.'),
      });
  }

  onDropdownOpen(opened: boolean, key: 'contact' | 'site'): void {
    if (opened) this.search[key] = '';
  }

  filteredContacts(): Contact[] {
    const term = this.search.contact.toLowerCase();
    return term ? this.contacts.filter(c => c.contactPersonName.toLowerCase().includes(term)) : this.contacts;
  }

  filteredSites(): Site[] {
    const term = this.search.site.toLowerCase();
    return term ? this.sites.filter(s => (s.siteAddressCode || s.addressLine || '').toLowerCase().includes(term)) : this.sites;
  }

  loadQuotation(id: number): void {
    this.loading = true;
    this.apiService.get<any>(`/quotations/${id}`).subscribe({
      next: (data) => {
        this.quotationStatus = data.status || 'Draft';
        this.currentOwnerUserId = data.ownerUserId ?? null;
        this.versionNo = data.versionNo || 1;
        this.parentQuotId = data.parentQuotId ?? null;
        // Keep viability status in sync so the stepper reflects the true stage.
        this.refreshViabilityStatus();
        this.quotForm.patchValue({
          ...data,
          quotDate: data.quotDate ? new Date(data.quotDate) : null,
          CustomerPODate: data.CustomerPODate ? new Date(data.CustomerPODate) : null,
        });
        // Lock customer if linked to an enquiry. The ServerSearchSelect auto-resolves
        // the enqid → label via its /search?ids=X lookup — no manual preload needed.
        if (data.enqid) {
          this.customerLocked = true;
        }
        if (data.customerId) {
          this.loadContactsAndSites(data.customerId);
        }
        // Revised = fully locked.
        // Matured = only PO fields editable.
        // Anything past Matured (Viability/Annexure stages) = fully locked too —
        // the order details and PO are frozen, viability/annexure live in their
        // own components/tabs.
        this.isLocked = data.status === 'Revised';
        this.isMatured = data.status === 'Matured';
        const pastMatured = [
          'ViabilityGenerated', 'ViabilityApproved',
          'AnnexureGenerated', 'AnnexureApproved',
        ].includes(data.status);
        if (this.isLocked || pastMatured) {
          this.quotForm.disable();
        } else if (this.isMatured) {
          // Disable everything, then re-enable PO fields only
          this.quotForm.disable();
          this.quotForm.get('CustomerPONo')?.enable();
          this.quotForm.get('CustomerPODate')?.enable();
        }
        this.loading = false;
      },
      error: () => {
        this.notificationService.error('Failed to load quotation.');
        this.loading = false;
      },
    });
  }

  onEnquiryChange(enqid: number | null): void {
    if (!enqid) {
      this.customerLocked = false;
      return;
    }
    // Fetch full enquiry to get contactId, siteId
    this.apiService.get<any>(`/enquiries/${enqid}`).subscribe({
      next: (enquiry) => {
        // If the form is in a locked state (Matured/past-Matured), the
        // individual controls are disabled — patchValue will still write
        // values, but attached UI components (e.g. server-search-select)
        // won't refresh while disabled. Temporarily enable the three
        // controls we're patching, then re-disable them so the surrounding
        // lock state is preserved.
        const keys = ['customerId', 'customerContactId', 'siteId'] as const;
        const wasDisabled: Record<string, boolean> = {};
        for (const k of keys) {
          const ctrl = this.quotForm.get(k);
          if (!ctrl) continue;
          wasDisabled[k] = ctrl.disabled;
          if (ctrl.disabled) ctrl.enable({ emitEvent: false });
        }
        this.quotForm.patchValue({
          customerId: enquiry.customerId,
          customerContactId: enquiry.customerContactId || null,
          siteId: enquiry.siteId || null,
        });
        for (const k of keys) {
          if (wasDisabled[k]) {
            this.quotForm.get(k)?.disable({ emitEvent: false });
          }
        }
        this.customerLocked = true;
        this.loadContactsAndSites(enquiry.customerId);
      },
      error: () => {
        this.notificationService.error('Failed to load enquiry details');
      },
    });
  }

  onCustomerChange(customerId: number | null): void {
    if (!customerId) return;
    this.loadContactsAndSites(customerId);
  }

  loadContactsAndSites(customerId: number): void {
    this.apiService.get<Contact[]>(`/customers/${customerId}/contacts`).subscribe({
      next: (data) => (this.contacts = data),
      error: () => this.notificationService.error('Failed to load contacts.'),
    });

    this.apiService.get<Site[]>(`/customers/${customerId}/sites`).subscribe({
      next: (data) => (this.sites = data),
      error: () => this.notificationService.error('Failed to load sites.'),
    });
  }

  saveQuotation(): void {
    // Raw-value read so disabled controls are still included in the payload.
    // When the form is in Matured/past-Matured state, identity fields like
    // customerId are disabled — they'd silently drop from `.value` and the
    // server would reject the save or lose the association.
    if (this.quotForm.invalid && this.quotForm.enabled) return;
    this.saving = true;
    const val = this.quotForm.getRawValue();
    const payload = {
      ...val,
      quotDate: val.quotDate ? this.formatDate(val.quotDate) : null,
      CustomerPODate: val.CustomerPODate ? this.formatDate(val.CustomerPODate) : null,
    };

    const request$ = this.isEditMode && this.quotationId
      ? this.apiService.put(`/quotations/${this.quotationId}`, payload)
      : this.apiService.post('/quotations', payload);

    request$.subscribe({
      next: (res: any) => {
        this.saving = false;
        const savedId = res?.quotId ?? this.quotationId;
        this.notificationService.success('Quotation saved successfully.');
        if (!this.isEditMode && savedId) {
          this.router.navigate(['/quotations', savedId, 'edit']);
        } else {
          this.quotationId = savedId;
          this.isEditMode = true;
          this.activeTab = 1;
        }
      },
      error: () => {
        this.saving = false;
        this.notificationService.error('Failed to save quotation.');
      },
    });
  }

  private formatDate(date: Date | string): string {
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  openHandover(): void {
    if (!this.quotationId) return;
    const quotNo = this.quotForm.get('quotNo')?.value;
    const ref = this.dialog.open(HandoverDialogComponent, {
      data: {
        entityType: 'quotation',
        entityId: this.quotationId,
        entityNo: quotNo,
        currentOwnerUserId: this.currentOwnerUserId ?? undefined,
      },
      width: '540px',
    });
    ref.afterClosed().subscribe(result => {
      if (result) {
        // Reload to reflect new owner and possibly Draft status
        this.loadQuotation(this.quotationId!);
      }
    });
  }

  reviseQuotation(): void {
    if (!this.quotationId) return;
    this.apiService.post(`/quotations/${this.quotationId}/revise`, {}).subscribe({
      next: (res: any) => {
        this.notificationService.success('Quotation revised. New version created.');
        if (res?.quotId) {
          this.router.navigate(['/quotations', res.quotId, 'edit']);
        }
      },
      error: (e: any) => this.notificationService.error(e?.error?.detail || 'Failed to revise quotation.'),
    });
  }

  approveQuotation(): void {
    if (!this.quotationId) return;

    // Confirm before approving — once approved, edits go through Revise.
    // The backend ALSO rejects approve when line items / TnC are missing
    // (its detail message will surface in the error toast if so).
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Approve quotation?',
        message:
          'Once approved, edits to this version will require a Revision. ' +
          'Make sure line items and Terms & Conditions are complete before approving.',
        confirmText: 'Yes, approve',
        cancelText: 'Cancel',
        confirmColor: 'primary',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok || !this.quotationId) return;
      this.apiService.put(`/quotations/${this.quotationId}/approve`, {}).subscribe({
        next: () => {
          this.notificationService.success('Quotation approved.');
          this.loadQuotation(this.quotationId!);
        },
        error: (e) => this.notificationService.error(e?.error?.detail || 'Failed to approve.'),
      });
    });
  }

  /**
   * Called by child cards (viability / annexure) after any state-changing
   * action (generate/approve). Re-pulls the quotation so the header status
   * badge, stepper, tab locks, and PO/Viability card gating all reflect the
   * new stage instantly — no manual refresh needed.
   */
  onSubStageChanged(): void {
    if (this.quotationId) this.loadQuotation(this.quotationId);
  }

  /**
   * Pull the viability sheet state so the stepper can show the real stage.
   * Only meaningful once the quotation is Matured; for earlier states we
   * clear the badge. The GET endpoint is cheap (returns null viability on
   * a non-matured quotation) so we don't guard aggressively.
   */
  private refreshViabilityStatus(): void {
    if (!this.quotationId) return;
    if (this.quotationStatus !== 'Matured') {
      this.viabilityStatus = null;
      return;
    }
    this.apiService.get<any>(`/quotations/${this.quotationId}/viability`).subscribe({
      next: (res) => {
        const v = res?.viability;
        this.viabilityStatus = v ? (v.status === 'Approved' ? 'Approved' : 'Draft') : null;
      },
      error: () => { this.viabilityStatus = null; },
    });
  }

  /** PO card is relevant from the moment the quotation is Approved and stays
   * visible through every downstream stage so the user can reference the
   * order details while working on Viability or Annexure. */
  showPoCard(): boolean {
    return !!this.quotationId && [
      'Approved', 'Matured',
      'ViabilityGenerated', 'ViabilityApproved',
      'AnnexureGenerated', 'AnnexureApproved',
    ].includes(this.quotationStatus);
  }

  /** Viability card only becomes available once the quotation is Matured.
   * Stays visible through the downstream stages (ViabilityGenerated/Approved,
   * AnnexureGenerated/Approved) so the user can reference it while working
   * on annexure. Becomes read-only once we move past viability approval. */
  showViabilityCard(): boolean {
    return !!this.quotationId && [
      'Matured',
      'ViabilityGenerated', 'ViabilityApproved',
      'AnnexureGenerated', 'AnnexureApproved',
    ].includes(this.quotationStatus);
  }

  /** PO fields are only editable in Approved / Matured. Past Matured we
   * freeze them — viability / annexure stages shouldn't mutate the order. */
  get poEditable(): boolean {
    return !this.isLocked
      && (this.quotationStatus === 'Approved' || this.quotationStatus === 'Matured');
  }

  /** Viability stops being editable once we've moved into the annexure stages. */
  get viabilityReadOnly(): boolean {
    return this.isLocked
      || this.quotationStatus === 'AnnexureGenerated'
      || this.quotationStatus === 'AnnexureApproved';
  }

  /** Mature action requires both PO No and PO Date to be filled and saved. */
  get poReadyToMature(): boolean {
    const no = (this.quotForm.get('CustomerPONo')?.value || '').toString().trim();
    const date = this.quotForm.get('CustomerPODate')?.value;
    const dirty = this.poDirty;
    return !!no && !!date && !dirty;
  }

  /** True when either PO field has unsaved edits — used to drive the Save button and the save-before-mature prompt. */
  get poDirty(): boolean {
    return !!this.quotForm.get('CustomerPONo')?.dirty
      || !!this.quotForm.get('CustomerPODate')?.dirty;
  }

  /** Persists PO No + PO Date via the existing update path. Stays on current tab. */
  savePoDetails(): void {
    if (!this.quotationId) return;
    const poNo = this.quotForm.get('CustomerPONo');
    const poDate = this.quotForm.get('CustomerPODate');
    if (!poNo?.value || !poDate?.value) {
      this.notificationService.error('Customer PO No and PO Date are required.');
      return;
    }
    this.saving = true;
    const payload = {
      CustomerPONo: poNo.value,
      CustomerPODate: this.formatDate(poDate.value),
    };
    this.apiService.put(`/quotations/${this.quotationId}`, payload).subscribe({
      next: () => {
        this.saving = false;
        poNo.markAsPristine();
        poDate.markAsPristine();
        this.notificationService.success('PO details saved.');
      },
      error: (e: any) => {
        this.saving = false;
        this.notificationService.error(e?.error?.detail || 'Failed to save PO details.');
      },
    });
  }

  /** Entry point for the Mature button. Prompts to save first if PO fields are dirty. */
  onClickMature(): void {
    if (!this.quotationId) return;
    if (this.poDirty) {
      const ref = this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: 'Unsaved PO Details',
          message: 'You have unsaved changes to the PO fields. Save them before marking this quotation as Matured?',
          confirmText: 'Save & Mature',
          cancelText: 'Cancel',
          confirmColor: 'primary',
        },
      });
      ref.afterClosed().subscribe(ok => {
        if (!ok) return;
        this.savePoDetailsThenMature();
      });
    } else {
      this.matureQuotation();
    }
  }

  private savePoDetailsThenMature(): void {
    if (!this.quotationId) return;
    const poNo = this.quotForm.get('CustomerPONo');
    const poDate = this.quotForm.get('CustomerPODate');
    this.saving = true;
    const payload = {
      CustomerPONo: poNo?.value,
      CustomerPODate: poDate?.value ? this.formatDate(poDate.value) : null,
    };
    this.apiService.put(`/quotations/${this.quotationId}`, payload).subscribe({
      next: () => {
        poNo?.markAsPristine();
        poDate?.markAsPristine();
        this.matureQuotation();
      },
      error: (e: any) => {
        this.saving = false;
        this.notificationService.error(e?.error?.detail || 'Failed to save PO details.');
      },
    });
  }

  matureQuotation(): void {
    if (!this.quotationId) return;
    this.saving = true;
    this.apiService.put(`/quotations/${this.quotationId}/mature`, {}).subscribe({
      next: () => {
        this.saving = false;
        this.notificationService.success('Quotation matured (PO received).');
        this.loadQuotation(this.quotationId!);
      },
      error: (e) => {
        this.saving = false;
        this.notificationService.error(e?.error?.detail || 'Failed to mature.');
      },
    });
  }

  rejectQuotation(): void {
    if (!this.quotationId) return;
    this.apiService.put(`/quotations/${this.quotationId}/reject`, {}).subscribe({
      next: () => {
        this.notificationService.success('Quotation rejected.');
        this.loadQuotation(this.quotationId!);
      },
      error: (e) => this.notificationService.error(e?.error?.detail || 'Failed to reject.'),
    });
  }

  revertReject(): void {
    if (!this.quotationId) return;
    this.apiService.put(`/quotations/${this.quotationId}/revert-reject`, {}).subscribe({
      next: () => {
        this.notificationService.success('Quotation reverted to Approved.');
        this.loadQuotation(this.quotationId!);
      },
      error: (e) => this.notificationService.error(e?.error?.detail || 'Failed to revert.'),
    });
  }

  onLineItemsExpand(expanded: boolean): void {
    this.lineItemsExpanded = expanded;
  }

  getSiteLabel(s: Site): string {
    const parts = [s.siteAddressCode];
    const addr = [s.addressLine, s.dist, s.state].filter(Boolean).join(', ');
    if (addr) parts.push(addr);
    return parts.join(' - ');
  }

  goBack(): void {
    this.router.navigate(['/quotations']);
  }
}
