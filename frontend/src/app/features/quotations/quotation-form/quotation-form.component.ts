import { Component, DestroyRef, inject, OnInit, ViewChild } from '@angular/core';
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
import { StageShellComponent, StagePrimaryCta, StageStatus } from '../shared/stage-shell.component';
import { QuotationAnnexureComponent } from '../quotation-annexure/quotation-annexure.component';
import { QuotationPoDialogComponent } from '../quotation-po-dialog/quotation-po-dialog.component';
import { LifecycleUnlockDialogComponent } from '../lifecycle-unlock-dialog/lifecycle-unlock-dialog.component';
import { StaleBannerComponent } from '../stale-banner/stale-banner.component';
import { CycleSelectorComponent } from '../cycle-selector/cycle-selector.component';
import { CycleHistoryComponent } from '../cycle-history/cycle-history.component';
import { PoLoiPickerComponent } from '../po-loi-picker/po-loi-picker.component';
import {
  CycleService,
  CyclePurchaseOrder,
  FwsApprovalSnapshot,
  OrderCycle,
} from '../services/cycle.service';
import { HasPermissionDirective } from '../../../shared/directives/has-permission.directive';

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
    StageShellComponent,
    QuotationAnnexureComponent,
    StaleBannerComponent,
    CycleSelectorComponent,
    CycleHistoryComponent,
    PoLoiPickerComponent,
    HasPermissionDirective,
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

          <!-- Approved → Convert: Stage-1 forward gate. Opens the PO
               Capture dialog; on save, creates a Draft PO and flips
               the quotation to Converted. The legacy "Capture PO &
               Mature" single-step has been split into Convert here +
               Submit & Mature on the PO Summary card below. -->
          <button mat-raised-button
            style="background:#1b5e20; color:#fff"
            *ngIf="canConvert && quotationStatus === 'Approved'"
            (click)="openCapturePoDialog()" [disabled]="saving"
            matTooltip="Convert: capture the customer PO and move to Stage 2">
            <mat-icon>play_circle</mat-icon> Convert
          </button>

          <!-- Edit PO action moved into the PO stage card's action
               cluster (used to live here on the global toolbar). -->

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

          <!-- Reject → Reactivate (back to Approved). The legacy
               /revert-reject endpoint is kept as a backward-compat
               alias for one release; new clients hit /reactivate. -->
          <button mat-stroked-button
            *ngIf="canReactivate && quotationStatus === 'Reject'"
            (click)="reactivateQuotation()" [disabled]="saving"
            matTooltip="Reactivate this quotation back to Approved">
            <mat-icon>refresh</mat-icon> Reactivate
          </button>

          <!-- Privileged escape valve. Visible on any locked status
               (Converted / Revised) when the user holds the Quotation-
               level Unlock permission. Opens the unlock dialog with
               an audit-trail reason prompt. -->
          <button mat-stroked-button color="warn"
            *ngIf="!unlockEditHidden && canUnlockEditQuotation
                   && (quotationStatus === 'Converted' || quotationStatus === 'Revised')"
            (click)="openUnlockDialog('quotation', 'Quotation')"
            [disabled]="saving"
            matTooltip="Privileged: unlock this quotation for in-place edits (audited)">
            <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
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

      <!-- Lifecycle stepper — top horizontal strip across the page,
           clickable stations switch the active stage's tab group
           below. Carries the rich per-cycle rollup (formal/LOI counts,
           FWS C{n}-V{m} label, viability + annexure version) merged
           in from the former cycle-status-panel. Hidden for unsaved
           quotations (no id yet). -->
      <app-quotation-stepper
        *ngIf="quotationId && !loading"
        [quotationStatus]="quotationStatus"
        [poStatus]="poStatus"
        [viabilityStatus]="viabilityStatus"
        [annexureStatus]="annexureStatus"
        [currentStage]="currentStage"
        [versionNo]="versionNo"
        [parentQuotId]="parentQuotId"
        [cycleNo]="selectedCycleNo"
        [formalPoCount]="formalPoCount"
        [loiCount]="loiCount"
        [fwsLatestLabel]="fwsLatestLabel"
        [fwsVersionCount]="fwsApprovedCount"
        [viabilityVersionNo]="upstreamViabilityVersion"
        [viabilityVersionCount]="viabilityVersionCount"
        [annexureVersionNo]="annexureVersionNo"
        [annexureVersionCount]="annexureVersionCount"
        (stageSelected)="onStageSelected($event)">
      </app-quotation-stepper>

      <div *ngIf="loading" class="spinner-container">
        <mat-spinner diameter="48"></mat-spinner>
      </div>

      <!-- Lifecycle Workspace. The outer stepper drives the active
           stage and we render exactly one stage's tab group at a time
           below. Constant tabs (Version History and Follow-Ups) are
           repeated on every stage's group, sourced from the shared
           ng-templates further down in the markup. -->
      <mat-card *ngIf="!loading && currentStage === 'quotation'">
        <mat-card-content>
          <mat-tab-group [(selectedIndex)]="stageTab.quotation" animationDuration="200ms">

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

            <!-- Tab 2: Working Sheet (line items) -->
            <mat-tab label="Working Sheet" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-details
                  *ngIf="quotationId"
                  [quotId]="quotationId"
                  [enqId]="quotForm.get('enqid')?.value"
                  [readOnly]="workingSheetLocked"
                  [isForDeliveryTerm]="isForDeliveryTerm"
                  [deliveryModeName]="deliveryModeName"
                  (expandedChange)="onLineItemsExpand($event)">
                </app-quotation-details>
              </div>
            </mat-tab>

            <!-- Tab 3: Terms & Conditions -->
            <mat-tab label="Terms & Conditions" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-tnc
                  *ngIf="quotationId"
                  [quotId]="quotationId"
                  [readOnly]="isLocked || isMatured">
                </app-quotation-tnc>
              </div>
            </mat-tab>

            <!-- Constant tabs: Version History + Follow-Ups, shared
                 across every stage's tab group via ng-templates
                 defined further down in this file. -->
            <mat-tab label="Version History" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="versionHistoryTabContent"></ng-container>
              </div>
            </mat-tab>
            <mat-tab label="Follow-Ups" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="followUpsTabContent"></ng-container>
              </div>
            </mat-tab>

          </mat-tab-group>
        </mat-card-content>
      </mat-card>

      <!-- ===== Stage 2 — Purchase Order ===== -->
      <mat-card *ngIf="!loading && currentStage === 'po'">
        <mat-card-content>
          <!-- LOI / Cycle CR — Phase 1D. Cycle pill strip + Append
               PO/LOI controls. Hidden on legacy quotations that have
               no cycles yet (the strip itself stays empty). -->
          <ng-container *ngIf="quotationId">
            <app-cycle-selector #cycleStrip
              [quotId]="quotationId"
              [selectedCycleId]="selectedCycleId"
              [showStartButton]="quotationStatus === 'Converted' || quotationStatus === 'Approved'"
              (cycleSelected)="onCycleSelected($event)"
              (cyclesLoaded)="onCyclesLoaded($event)"
              (startNewCycle)="startNewCycle(cycleStrip)">
            </app-cycle-selector>
            <div class="cycle-actions" *ngIf="activeCycleSelected">
              <button mat-stroked-button color="primary"
                      (click)="openAppendCycleDialog(cycleStrip, false)"
                      *hasPermission="'Quotations:canSubmitPO'">
                <mat-icon>post_add</mat-icon> Append PO
              </button>
              <button mat-stroked-button
                      (click)="openAppendCycleDialog(cycleStrip, true)"
                      *hasPermission="'Quotations:canCaptureLOI'">
                <mat-icon>edit_note</mat-icon> Append LOI
              </button>
            </div>
          </ng-container>

          <mat-tab-group [(selectedIndex)]="stageTab.po" animationDuration="200ms">
            <mat-tab label="PO Header" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="poHeaderTabContent"></ng-container>
              </div>
            </mat-tab>
            <!-- Final Working Sheet — the PO-level BOM. Cloned from
                 QuotDetails on Convert; soft-flow keeps it editable
                 throughout the cycle. The Approve button snapshots the
                 current rows as a new version (D3 short-circuit when
                 unchanged) and is the singular gate into Viability. -->
            <mat-tab label="Final Working Sheet" [disabled]="!quotationId">
              <div class="tab-content">
                <!-- Stage-shell prototype: same shell will wrap Viability
                     and Annexure once this lands. Header carries status +
                     version + Switch Version; next-step strip pairs the
                     "what to do" hint with the primary Approve CTA. -->
                <app-stage-shell *ngIf="quotationId"
                  stageName="Final Working Sheet"
                  stageIcon="inventory_2"
                  [status]="fwsShellStatus"
                  [statusText]="fwsShellStatusText"
                  [versionLabel]="fwsLatestLabel"
                  [approvedAt]="fwsLatestApprovedAt"
                  [approvedByName]="fwsLatestApprovedByName"
                  [nextStepHint]="fwsShellNextStep"
                  [primaryCta]="fwsShellCta"
                  [showVersionControl]="!!purchaseOrder && fwsApprovedCount > 0 && activeCycleSelected"
                  [canSwitchVersion]="!fwsSwitching && !fwsApproving"
                  [versionItems]="fwsVersionItems"
                  [currentVersionId]="fwsCurrentSnapshotId"
                  (primaryClick)="approveFws()"
                  (versionPicked)="onFwsVersionPicked($event)">

                  <div *ngIf="purchaseOrder && activeCycleSelected" class="fws-toolbar">
                    <button mat-stroked-button color="primary"
                            (click)="regenerateFws()"
                            [disabled]="fwsApproving || fwsSwitching || fwsRegenerating"
                            matTooltip="Re-generate the cycle's Final Working Sheet from a past FWS version, quotation lines, or a parent cycle. Unlocks the editor.">
                      <mat-icon>refresh</mat-icon> Re-generate FWS
                    </button>
                    <span *ngIf="isFwsApprovedLock" class="fws-lock-hint">
                      <mat-icon class="fws-lock-icon">lock</mat-icon>
                      Editor locked after Approve — Re-generate to start a fresh draft
                    </span>
                  </div>
                  <app-quotation-details #fwsGrid
                    *ngIf="purchaseOrder"
                    mode="po"
                    [quotId]="quotationId"
                    [cycleId]="selectedCycleId"
                    [readOnly]="!canEditFinalWorkingSheet"
                    [isForDeliveryTerm]="isForDeliveryTerm"
                    [deliveryModeName]="deliveryModeName"
                    (expandedChange)="onLineItemsExpand($event)">
                  </app-quotation-details>

                  <div *ngIf="!purchaseOrder" class="stage-empty">
                    <mat-icon>build_circle</mat-icon>
                    <p>The Final Working Sheet appears here once a PO or LOI is appended to the cycle.</p>
                    <p class="hint">
                      Use <strong>Append PO</strong> or <strong>Append LOI</strong> above to capture
                      the order and auto-clone the quotation's lines as the editable Final Working Sheet.
                    </p>
                  </div>
                </app-stage-shell>
              </div>
            </mat-tab>
            <mat-tab label="Cycle History" [disabled]="!quotationId">
              <div class="tab-content">
                <app-cycle-history *ngIf="quotationId"
                                   [quotId]="quotationId"></app-cycle-history>
              </div>
            </mat-tab>
            <mat-tab label="Version History" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="versionHistoryTabContent"></ng-container>
              </div>
            </mat-tab>
            <mat-tab label="Follow-Ups" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="followUpsTabContent"></ng-container>
              </div>
            </mat-tab>
          </mat-tab-group>
        </mat-card-content>
      </mat-card>

      <!-- ===== Stage 3 — Viability ===== -->
      <mat-card *ngIf="!loading && currentStage === 'viability'">
        <mat-card-content>
          <mat-tab-group [(selectedIndex)]="stageTab.viability" animationDuration="200ms">
            <mat-tab label="Viability Sheet" [disabled]="!quotationId">
              <div class="tab-content">
                <app-quotation-viability
                  *ngIf="quotationId && showViabilityCard()"
                  [quotId]="quotationId"
                  [canApprove]="canApprove"
                  [readOnly]="viabilityReadOnly"
                  [upstreamPoVersion]="purchaseOrder?.versionNo ?? null"
                  [resourcing]="resourcing"
                  (reSource)="reSourceStage('viability')"
                  (stageChanged)="onSubStageChanged()">
                </app-quotation-viability>
                <div *ngIf="!showViabilityCard()" class="stage-empty">
                  <mat-icon>query_stats</mat-icon>
                  <p>Viability stage opens once the cycle's Final Working Sheet is approved.</p>
                  <p class="hint">
                    Go to the <strong>Purchase Order</strong> stage, open the
                    <strong>Final Working Sheet</strong> tab, and click
                    <strong>Approve FWS</strong> to unlock this stage.
                  </p>
                </div>
              </div>
            </mat-tab>
            <mat-tab label="Version History" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="versionHistoryTabContent"></ng-container>
              </div>
            </mat-tab>
            <mat-tab label="Follow-Ups" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="followUpsTabContent"></ng-container>
              </div>
            </mat-tab>
          </mat-tab-group>
        </mat-card-content>
      </mat-card>

      <!-- ===== Stage 4 — Annexure ===== -->
      <mat-card *ngIf="!loading && currentStage === 'annexure'">
        <mat-card-content>
          <mat-tab-group [(selectedIndex)]="stageTab.annexure" animationDuration="200ms">
            <mat-tab [disabled]="!quotationId">
              <ng-template mat-tab-label>
                <mat-icon *ngIf="!annexureTabUnlocked" class="tab-lock-icon"
                          matTooltip="Locked until viability is approved">lock</mat-icon>
                <span>Annexure</span>
              </ng-template>
              <div class="tab-content">
                <app-quotation-annexure
                  *ngIf="quotationId && annexureTabUnlocked"
                  [quotId]="quotationId"
                  [cycleId]="selectedCycleId"
                  [cycleNo]="selectedCycleNo"
                  [canApprove]="canApprove"
                  [canApproveAnnexure]="canApproveAnnexure"
                  [readOnly]="isLocked"
                  [upstreamQuotationVersion]="versionNo || 1"
                  [upstreamPoVersion]="purchaseOrder?.versionNo ?? null"
                  [upstreamViabilityVersion]="upstreamViabilityVersion"
                  [resourcing]="resourcing"
                  (reSource)="reSourceStage('annexure')"
                  (stageChanged)="onSubStageChanged()">
                </app-quotation-annexure>
                <div *ngIf="!annexureTabUnlocked" class="stage-empty">
                  <mat-icon>description</mat-icon>
                  <p>Annexure stage opens once the Viability Sheet is approved.</p>
                </div>
              </div>
            </mat-tab>
            <mat-tab label="Version History" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="versionHistoryTabContent"></ng-container>
              </div>
            </mat-tab>
            <mat-tab label="Follow-Ups" [disabled]="!quotationId">
              <div class="tab-content">
                <ng-container *ngTemplateOutlet="followUpsTabContent"></ng-container>
              </div>
            </mat-tab>
          </mat-tab-group>
        </mat-card-content>
      </mat-card>

      <!-- ===== Shared tab content templates (constant across stages) ===== -->
      <ng-template #versionHistoryTabContent>
        <app-quotation-version-history
          *ngIf="quotationId"
          [quotId]="quotationId">
        </app-quotation-version-history>
      </ng-template>

      <ng-template #followUpsTabContent>
        <app-quotation-followup
          *ngIf="quotationId"
          [quotId]="quotationId">
        </app-quotation-followup>
      </ng-template>

      <!-- ===== Stage 2 PO Header tab content ===== -->
      <ng-template #poHeaderTabContent>
        <!-- PO has been captured. Renders the same accent-strip Summary
             card you saw before, just hosted inside Stage 2's tab now. -->
        <mat-card *ngIf="activePo" class="stage-card">
          <div class="stage-card-head">
            <div class="stage-card-head-left">
              <mat-icon class="stage-card-head-icon">receipt_long</mat-icon>
              <div class="stage-card-head-text">
                <div class="stage-card-head-title">
                  Purchase Order
                  <app-po-loi-picker
                    *ngIf="quotationId && selectedCycleId"
                    [quotId]="quotationId"
                    [cycleId]="selectedCycleId"
                    [selectedPoId]="selectedPoId"
                    (poSelected)="onPoSelected($event)"
                    (rowsLoaded)="onPoLoiRowsLoaded($event)">
                  </app-po-loi-picker>
                </div>
                <div class="stage-card-head-meta">
                  <span class="po-no">{{ activePo.poNo }}</span>
                  <span class="po-dot">·</span>
                  <span>dated {{ activePo.poDate | date:'dd-MM-yyyy' }}</span>
                  <ng-container *ngIf="activePo.isLOI">
                    <span class="po-dot">·</span>
                    <span class="po-loi-tag">LOI</span>
                  </ng-container>
                </div>
              </div>
            </div>
            <div class="stage-card-head-actions">
              <span class="stage-status-chip"
                    [class.is-approved]="activePo.status === 'Submitted'"
                    [class.is-warn]="activePo.status === 'Rejected'">
                {{ activePo.status || 'Draft' }}
              </span>

              <!-- Edit PO header — only meaningful while the PO is
                   Draft (the backend rejects edits on Submitted/Rejected
                   rows). Lives here on the PO stage card now, not on
                   the global toolbar. -->
              <button mat-stroked-button
                *ngIf="canConvert && activePo.status === 'Draft'"
                (click)="openEditPoDialog()" [disabled]="saving"
                matTooltip="Edit the captured PO header (customer / contact / billing / consignee)">
                <mat-icon>edit_note</mat-icon> Edit PO
              </button>

              <!-- Soft-flow redesign (Slice C, 2026-05-20): the
                   "Submit & Mature" and "Reject PO" buttons are gone.
                   POs are append-only records now; the lifecycle is
                   advanced by clicking Approve on the Final Working
                   Sheet (one new versioned snapshot per click).
                   Withdrawing a PO is a soft-delete via the row's
                   trash affordance — backend supports
                   DELETE /cycles/{cId}/purchase-orders/{poId}. -->
              <button mat-stroked-button color="warn"
                *ngIf="canRejectPO && activePo.status !== 'Rejected'"
                (click)="withdrawPo()" [disabled]="saving"
                matTooltip="Withdraw this PO from the cycle (soft-delete). The cycle keeps running.">
                <mat-icon>delete_outline</mat-icon> Withdraw PO
              </button>

              <button mat-stroked-button color="warn"
                *ngIf="!unlockEditHidden && canUnlockEditPO && activePo.status === 'Submitted' && !viabilityApproved"
                (click)="openUnlockDialog('purchase-order', 'Purchase Order')"
                [disabled]="saving"
                matTooltip="Privileged: unlock this submitted PO for in-place edits (audited)">
                <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
              </button>

              <span *ngIf="viabilityApproved" class="stage-status-chip is-locked"
                    matTooltip="Locked because the Viability Sheet has been approved. Re-source from upstream to revisit.">
                <mat-icon>lock</mat-icon> Locked
              </span>
            </div>
          </div>

          <app-stale-banner
            [stale]="isPoStaleVsQuotation()"
            stageLabel="Purchase Order"
            title="PO is stale relative to the quotation"
            [message]="poStaleMessage()"
            [canResource]="canUnlockEditPO"
            [busy]="resourcing"
            (resource)="reSourceStage('purchase-order')">
          </app-stale-banner>

          <div class="po-grid">
            <div class="po-field">
              <label>Customer</label>
              <span>{{ activePo.customerName || '—' }}</span>
            </div>
            <div class="po-field">
              <label>Contact Person</label>
              <span>{{ activePo.contactPersonName || '—' }}</span>
            </div>
            <div class="po-field po-addr">
              <label>
                <mat-icon class="po-field-icon">request_quote</mat-icon>
                Billing Address
              </label>
              <span>{{
                activePo.billingAddressManual
                  || activePo.billingSiteAddress
                  || '—'
              }}</span>
            </div>
            <div class="po-field po-addr">
              <label>
                <mat-icon class="po-field-icon">local_shipping</mat-icon>
                Consignee Address
              </label>
              <span>{{
                activePo.consigneeAddressManual
                  || activePo.consigneeSiteAddress
                  || '—'
              }}</span>
            </div>
            <div class="po-field po-remarks" *ngIf="activePo.remarks">
              <label>Remarks</label>
              <span>{{ activePo.remarks }}</span>
            </div>
            <div class="po-field po-remarks" *ngIf="activePo.isLOI && activePo.loiText">
              <label>LOI Text</label>
              <span>{{ activePo.loiText }}</span>
            </div>
          </div>

          <mat-divider class="po-divider"></mat-divider>

          <!-- PO Attachments — scoped to the picked PO/LOI when one
               is selected. The quotPOId input triggers ngOnChanges in
               AssetUploadComponent which re-fetches the list, so
               switching the picker swaps the visible files
               accordingly. -->
          <app-asset-upload
            *ngIf="quotationId"
            [quotId]="quotationId"
            [quotPOId]="selectedPoId ?? undefined"
            category="po_document"
            [title]="selectedPoId
              ? 'Attachments · ' + (activePo.isLOI ? 'LOI ' : 'PO ') + activePo.poNo
              : 'PO Attachments'"
            namePlaceholder="e.g. PO Scan, Amendment"
            [allowedExtensions]="['pdf','jpg','jpeg','png']"
            [maxSizeMb]="20"
            [compressImages]="true"
            [multiple]="false"
            [disabled]="isPoAttachmentsLocked"
            hintText="Allowed: PDF, JPG, PNG · max 20 MB · images auto-compressed">
          </app-asset-upload>
        </mat-card>

        <!-- No PO captured yet — show empty-state + invite to Convert. -->
        <div *ngIf="!purchaseOrder" class="stage-empty">
          <mat-icon>receipt_long</mat-icon>
          <p>No purchase order captured yet.</p>
          <p class="hint">Use the <strong>Convert</strong> button on Stage 1 to capture the customer PO and open this stage.</p>
        </div>
      </ng-template>
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

    /* Stage-level empty / locked panel — used inside any stage's
       tab content when the underlying entity isn't ready (e.g. PO
       not yet captured, viability locked until PO is Submitted,
       annexure locked until viability is Approved). */
    .cycle-actions {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .cycle-actions button mat-icon { margin-right: 4px; }

    /* FWS Approve bar — sits above the line-items grid and pairs the
       "Last approved C{n}-V{m}" status badge with the singular Approve
       CTA. Replaces the legacy Submit & Mature lifecycle. */
    .fws-approve-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      margin-bottom: 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
    }
    .fws-approve-status {
      display: flex; align-items: center; gap: 8px;
      font-size: 13px;
      color: var(--snm-text-secondary);
      flex: 1 1 auto;
      min-width: 0;
    }
    .fws-status-icon { flex: 0 0 auto; }
    .fws-status-icon.ok { color: var(--snm-accent); }
    .fws-status-icon.warn { color: rgba(200, 150, 30, 0.95); }
    .fws-status-text strong { color: var(--snm-text-primary); margin: 0 4px; }
    .fws-status-meta {
      color: var(--snm-text-muted);
      font-size: 12px;
      margin-left: 4px;
    }
    .fws-approve-bar button mat-icon { margin-right: 4px; }
    .fws-actions { display: flex; gap: 8px; align-items: center; }
    .fws-toolbar {
      display: flex; gap: 8px; align-items: center;
      padding: 8px 0 4px;
      border-bottom: 1px dashed var(--snm-border-divider);
      margin-bottom: 8px;
    }
    .fws-toolbar button mat-icon { margin-right: 4px; }
    .fws-lock-hint {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px;
      color: var(--snm-text-muted);
      font-style: italic;
    }
    .fws-lock-icon {
      font-size: 16px; width: 16px; height: 16px;
      color: var(--snm-text-muted);
    }
    @media (max-width: 768px) {
      .fws-approve-bar {
        flex-direction: column;
        align-items: stretch;
      }
    }

    .stage-empty {
      text-align: center;
      padding: 56px 24px;
      color: var(--snm-text-muted);
    }
    .stage-empty mat-icon {
      font-size: 48px; width: 48px; height: 48px; opacity: 0.55;
      margin-bottom: 12px;
    }
    .stage-empty p { margin: 4px 0; font-size: 14px; }
    .stage-empty .hint {
      font-size: 12px;
      color: var(--snm-text-faint);
      max-width: 480px;
      margin: 6px auto 0;
      line-height: 1.5;
    }

    /* PO Summary card body. Shell chrome (head strip, status chip,
       lock chip) lives in the shared stage-card classes in
       styles.scss; only the body grid and address blocks are
       component-specific. */
    .po-no {
      font-weight: 600;
      color: var(--snm-accent-dark, #3a6bb5);
      letter-spacing: 0.3px;
    }
    .po-dot { margin: 0 6px; opacity: 0.5; }
    .po-loi-tag {
      padding: 1px 8px; border-radius: 8px;
      background: rgba(245,124,0,0.14); color: #f57c00;
      font-size: 11px; font-weight: 700;
      letter-spacing: 0.4px;
    }
    .po-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px 24px;
      padding: 18px 22px 6px;
    }
    .po-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .po-field label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      color: var(--snm-text-muted, rgba(0,0,0,0.55));
    }
    .po-field-icon {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--snm-accent, #5b85c2);
    }
    .po-field span {
      font-size: 14px;
      color: var(--snm-text-primary, #1a1a1a);
      line-height: 1.5;
      word-break: break-word;
    }
    .po-addr span {
      padding: 8px 12px;
      background: rgba(58, 107, 181, 0.04);
      border-left: 3px solid var(--snm-accent, #5b85c2);
      border-radius: 4px;
    }
    .po-remarks {
      grid-column: 1 / -1;
    }
    .po-divider {
      margin: 14px 0 0;
    }
    .po-summary-card app-asset-upload {
      display: block;
      padding: 18px 22px 18px;
    }
    @media (max-width: 768px) {
      .po-grid { grid-template-columns: 1fr; gap: 14px; padding: 16px; }
      .po-summary-card app-asset-upload { padding: 16px; }
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
  /** Currently-viewed lifecycle stage. Driven by the top stepper.
   *  Each stage owns its own ``mat-tab-group`` below; only the matching
   *  group is rendered. Constant tabs (Version History + Follow-Ups)
   *  are repeated at the right end of every group.
   *
   *  Default: 'quotation'. The stepper auto-selects the latest reached
   *  stage on first quotation load via ``computeDefaultStage()``. */
  currentStage: 'quotation' | 'po' | 'viability' | 'annexure' = 'quotation';
  /** Per-stage tab index. Each stage gets its own selectedIndex so
   *  switching back to a stage restores the user's last sub-view. */
  stageTab: { quotation: number; po: number; viability: number; annexure: number } = {
    quotation: 0, po: 0, viability: 0, annexure: 0,
  };
  /** Lifecycle status snapshot — drives the stepper's per-stage
   *  sub-text and reached state. Refreshed in ``loadQuotation``. */
  poStatus: 'Draft' | 'Submitted' | 'Rejected' | null = null;
  annexureStatus: 'Draft' | 'Approved' | null = null;
  /** Current viability head's versionNo (Phase 3 — Annexure compares
   *  this to its stamped ``sourcedFromViabilityVersion`` to surface a
   *  stale banner). Hydrated by ``refreshViabilityStatus``. */
  upstreamViabilityVersion: number | null = null;
  /** Used by ``loadQuotation`` to auto-pick the latest reached stage
   *  exactly once on first quotation load. Subsequent reloads (after
   *  Convert, Submit, etc.) preserve whatever stage the user is on. */
  private firstLoad = true;
  /** True while a Re-source request is in flight (Phase 3). The
   *  StaleBanner reads this for its inline spinner / disabled state. */
  resourcing = false;
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
  // Phase 1 lifecycle flags. Read from menuService on init.
  canConvert = false;
  canReactivate = false;
  canSubmitPO = false;
  canRejectPO = false;
  canUnlockEditQuotation = false;
  canUnlockEditPO = false;
  /** Feature flag — hides every Unlock & Edit button regardless of the
   *  caller's ``canUnlockEdit*`` permission. The underlying permission
   *  flags are still loaded (so Restore / Re-source affordances that
   *  share the same gate keep working); only the in-place unlock dialog
   *  is suppressed. Flip to ``false`` to re-enable the feature. */
  readonly unlockEditHidden = true;
  /** Granted only to the Commercial HOD role. Gates the annexure
   *  approve button AND lets the holder edit annexures even after
   *  they're approved. */
  canApproveAnnexure = false;
  currentOwnerUserId: number | null = null;
  isLocked = false;
  isMatured = false;

  /** Captured customer PO row (1:1 with the quotation). Null until the
   *  user runs the Capture-PO dialog; populated from the quotation
   *  ``purchase_order`` field on every reload. The form template's PO
   *  Summary card binds to this directly. The backend response carries
   *  pre-resolved labels (``customerName``, ``contactPersonName``,
   *  ``billingSiteAddress``, ``consigneeSiteAddress``) so this card
   *  doesn't need a follow-up site lookup — even when the address is
   *  an ad-hoc site that isn't in the regular picker list. */
  purchaseOrder: any | null = null;

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

  /** Annexure tab opens once viability is approved. Reads the
   *  per-stage status directly (Phase 4) — the legacy
   *  ViabilityApproved / AnnexureGenerated / AnnexureApproved
   *  strings on QuotSummary are gone. */
  get annexureTabUnlocked(): boolean {
    return this.viabilityStatus === 'Approved' || !!this.annexureStatus;
  }

  /** Working-sheet (line items) is locked once the quotation is
   *  Converted. After Convert the line items are immutable on the
   *  quotation side — any qty / cost-head changes happen on the
   *  PO Working Sheet (Stage 2). ``isLocked`` (Revised) keeps its
   *  pre-existing lock. */
  get workingSheetLocked(): boolean {
    if (this.isLocked) return true;
    return this.quotationStatus === 'Converted';
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
    private cycleService: CycleService,
  ) { }

  // ---- LOI / Cycle CR — Phase 1D state ----
  /** All cycles known on this quotation. Populated by the
   *  ``<app-cycle-selector>`` strip after its initial fetch. Empty
   *  array means this quotation pre-dates the cycle CR (legacy single-PO
   *  shape); the strip stays hidden in that case. */
  cycles: OrderCycle[] = [];

  /** The cycle whose POs/LOIs the Stage-2 panel is currently rendering.
   *  Defaults to the latest Active cycle on load; user can flip via
   *  the pill strip. */
  selectedCycleId: number | null = null;

  /** True when the active selected cycle is Active — controls whether
   *  the "Append PO / LOI" CTA is visible. */
  get activeCycleSelected(): boolean {
    const c = this.cycles.find(x => x.quotOrderCycleId === this.selectedCycleId);
    return !!c && c.status === 'Active';
  }

  /** Cycle number of the currently selected cycle (1-based). Used by
   *  the annexure component's Generate dialog for the C{n}-V{m}
   *  display label. Returns ``null`` when no cycle is selected. */
  get selectedCycleNo(): number | null {
    const c = this.cycles.find(x => x.quotOrderCycleId === this.selectedCycleId);
    return c?.cycleNo ?? null;
  }

  // ---- FWS approval state (soft-flow Slice F') ----
  /** How many FWS approval snapshots exist for the currently selected
   *  cycle. Drives the Viability gate (>= 1 unlocks the stage) and the
   *  Approve-FWS button's label flip ("Approve" → "Re-approve"). */
  fwsApprovedCount = 0;
  /** Latest snapshot's display label (e.g. "C1-V2") for the badge. */
  fwsLatestLabel: string | null = null;
  fwsLatestApprovedAt: string | null = null;
  fwsLatestApprovedByName: string | null = null;
  /** True while the POST /fws/approve request is in flight. */
  fwsApproving = false;
  /** True while a version-switch round-trip is in flight (load, or
   *  save-then-load). Disables both Approve and Switch buttons. */
  fwsSwitching = false;
  /** True while POST /fws/regenerate is in flight. */
  fwsRegenerating = false;
  /** Snapshot id the FWS editor was last loaded from. Used by the
   *  switch dialog to highlight the current row and disable
   *  switching-to-yourself. Initial value = the latest approved
   *  snapshot id (best-effort approximation; the live editor's
   *  content may diverge from this after subsequent edits). */
  fwsCurrentSnapshotId: number | null = null;
  /** Cached snapshot list used by the switch dialog. Populated by
   *  ``loadFwsApprovalState`` so the dialog opens instantly. */
  fwsSnapshotList: FwsApprovalSnapshot[] = [];
  /** Annexure head's versionNo — fed into the stepper's per-stage
   *  rollup so the Annexure stop can show ``C{n}-V{m}``. Hydrated by
   *  ``refreshAnnexureStatus``. */
  annexureVersionNo: number | null = null;
  /** How many approval snapshots exist for viability + annexure on
   *  this quotation. Drives the stepper's "· N versions" suffix on
   *  the per-stage detail line (mirrors the FWS rollup). Hydrated by
   *  ``refreshViabilityStatus`` / ``refreshAnnexureStatus``. */
  viabilityVersionCount = 0;
  annexureVersionCount = 0;

  /** Count of formal (non-LOI) POs in the currently selected cycle.
   *  Drives the stepper's PO/LOI rollup sub-text. Sourced from
   *  ``cyclePOs`` which the PO-LOI picker (or the parent-level cycle
   *  bundle pre-fetch) populates. */
  get formalPoCount(): number {
    return this.cyclePOs.filter(p => !p.isLOI).length;
  }
  /** Count of LOI rows in the currently selected cycle. */
  get loiCount(): number {
    return this.cyclePOs.filter(p => !!p.isLOI).length;
  }

  // ---- StageShell bindings for the FWS prototype ----
  /** Drives the FWS status pill in the shell header. */
  get fwsShellStatus(): StageStatus {
    if (!this.purchaseOrder) return 'locked';
    if (this.fwsApprovedCount > 0) return 'approved';
    return 'draft';
  }
  /** Human-readable status label. */
  get fwsShellStatusText(): string {
    if (!this.purchaseOrder) return 'Awaiting PO';
    if (this.fwsApprovedCount > 0) return 'Approved';
    return 'Draft';
  }
  /** One-line "what to do next" guidance under the FWS header. */
  get fwsShellNextStep(): string {
    if (!this.purchaseOrder) {
      return 'Append a PO or LOI to this cycle to start the Final Working Sheet';
    }
    if (this.fwsApprovedCount === 0) {
      return 'Review the line item costs, then Approve to unlock the Viability stage';
    }
    return 'Approve again to capture the latest edits as a new version, or move on to Viability';
  }
  /** Primary CTA descriptor for the FWS shell. ``null`` hides the
   *  button — happens when (a) no PO yet, (b) user lacks
   *  ``canApprove``, (c) cycle isn't Active, or (d) FWS is already
   *  Approved (Re-generate is the path back to editable). The
   *  "Re-approve" label is gone: once locked, the user clicks
   *  Re-generate to unlock + edit + Approve. */
  get fwsShellCta(): StagePrimaryCta | null {
    if (!this.purchaseOrder) return null;
    if (!this.canApprove || !this.activeCycleSelected) return null;
    const cycle = this.cycles.find(
      c => c.quotOrderCycleId === this.selectedCycleId,
    );
    if (cycle && cycle.fwsStatus === 'approved') return null;
    return {
      label: this.fwsApprovedCount > 0
        ? 'Approve FWS'
        : 'Approve FWS & Continue to Viability',
      icon: 'verified',
      disabled: false,
      busy: this.fwsApproving || this.fwsSwitching,
      color: 'primary',
    };
  }

  /** Map the cached FWS snapshot list into the inline picker's
   *  ``VersionInlineItem`` shape. */
  get fwsVersionItems(): { id: number; label: string; approvedAt: string | null; approvedByName: string | null }[] {
    return this.fwsSnapshotList.map(s => ({
      id: s.snapshotId,
      label: s.label,
      approvedAt: s.approvedAt,
      approvedByName: s.approvedByName,
    }));
  }

  // ---- Per-PO/LOI picker (Issue #1) ----
  /** Reference so we can ask the picker to refetch the cycle's
   *  bundle after an append (the picker self-loads on cycleId change
   *  but a same-cycle append doesn't fire ngOnChanges, so we trigger
   *  reload imperatively). Undefined when the picker is currently
   *  not mounted (no cycle selected / no PO captured yet). */
  @ViewChild(PoLoiPickerComponent) poLoiPicker?: PoLoiPickerComponent;
  /** Reference to the FWS line-items grid. Lets us imperatively
   *  refresh after a version-switch loads new rows into the table. */
  @ViewChild('fwsGrid') fwsGrid?: QuotationDetailsComponent;

  /** Currently selected PO/LOI from the picker dropdown. NULL means
   *  "fall back to the legacy single-PO ref" — keeps existing behaviour
   *  intact for quotations with one PO in their cycle. */
  selectedPoId: number | null = null;

  /** Cached list of POs/LOIs in the active cycle. Populated by the
   *  PoLoiPickerComponent's ``(rowsLoaded)`` callback. */
  cyclePOs: CyclePurchaseOrder[] = [];

  /** The PO/LOI row whose details the PO Header card is currently
   *  displaying. Falls back to the legacy ``purchaseOrder`` ref when
   *  the picker hasn't selected anything yet (e.g. cycle has only one
   *  PO and the form just opened). */
  get activePo(): any {
    if (this.selectedPoId) {
      const picked = this.cyclePOs.find(
        p => p.quotPOId === this.selectedPoId,
      );
      if (picked) return picked;
    }
    return this.purchaseOrder;
  }

  onPoSelected(po: CyclePurchaseOrder): void {
    this.selectedPoId = po.quotPOId;
    // The asset-upload component re-fetches its list whenever
    // ``quotPOId`` flips (via ngOnChanges), so no manual refresh
    // call is needed here.
  }

  /** Picker emits the full bundle list after every load. Auto-selection
   *  policy:
   *    1. Keep the current pick if it's still in the list.
   *    2. Otherwise, prefer the most-recently appended row (highest
   *       ``loiSequence``) — so right after the user clicks "Append
   *       LOI/PO", the form jumps to the row they just created.
   *    3. Fall back to the legacy ``purchaseOrder.quotPOId`` so
   *       single-PO quotations keep showing the row the access
   *       pipeline already loaded.
   *    4. Empty list → null. */
  onPoLoiRowsLoaded(rows: CyclePurchaseOrder[]): void {
    this.cyclePOs = rows;
    if (this.selectedPoId
        && rows.some(r => r.quotPOId === this.selectedPoId)) {
      return;
    }
    if (rows.length === 0) {
      this.selectedPoId = null;
      return;
    }
    const latest = [...rows].sort(
      (a, b) => (b.loiSequence ?? 0) - (a.loiSequence ?? 0),
    )[0];
    if (this.purchaseOrder
        && rows.some(r => r.quotPOId === this.purchaseOrder!.quotPOId)
        // Only fall back to legacy ref when the picker hasn't been
        // touched yet (first load on a single-PO cycle).
        && this.selectedPoId === null && this.cyclePOs.length === 1) {
      this.selectedPoId = this.purchaseOrder.quotPOId;
      return;
    }
    this.selectedPoId = latest.quotPOId;
  }

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
    // Phase 1 lifecycle flags. Convert/Reactivate/SubmitPO/RejectPO
    // fall back to canApprove for legacy roles that haven't been
    // granted the new flags yet — keeps existing HOD users unblocked
    // until the role-menu mapping is updated.
    this.canConvert = this.menuService.hasPermission('Quotations', 'canConvert')
      || this.menuService.hasPermission('Quotations', 'canApprove');
    this.canReactivate = this.menuService.hasPermission('Quotations', 'canReactivate')
      || this.menuService.hasPermission('Quotations', 'canApprove');
    this.canSubmitPO = this.menuService.hasPermission('Quotations', 'canSubmitPO')
      || this.menuService.hasPermission('Quotations', 'canEdit');
    this.canRejectPO = this.menuService.hasPermission('Quotations', 'canRejectPO')
      || this.menuService.hasPermission('Quotations', 'canApprove');
    // Unlock-and-Edit has NO legacy fallback — privileged users only.
    this.canUnlockEditQuotation = this.menuService.hasPermission('Quotations', 'canUnlockEditQuotation');
    this.canUnlockEditPO = this.menuService.hasPermission('Quotations', 'canUnlockEditPO');
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
        });
        // PO header lives on a separate entity now; cache the row so the
        // PO Summary card and the Edit-PO dialog can read from it. The
        // backend response carries pre-resolved labels for customer /
        // contact / billing / consignee, so the card binds directly
        // without any further client-side lookup.
        this.purchaseOrder = data.purchase_order || null;
        // Stepper sub-states. PO comes from the nested entity;
        // viability + annexure each fetch their own per-stage status
        // via dedicated endpoints (Phase 4 — no more deriving from
        // the now-collapsed QuotSummary.status).
        this.poStatus = (data.purchase_order?.status as any) || null;
        this.refreshAnnexureStatus();
        // Auto-pick the latest reached stage on first load so the user
        // lands on whichever stage they were last working on.
        if (this.firstLoad) {
          this.currentStage = this.computeDefaultStage();
          this.firstLoad = false;
        }
        // Pre-load cycles at the parent level so the Viability gate
        // (fwsApprovedCount > 0) is accurate even when the initial
        // stage is 'viability' or 'annexure' — in those routes the
        // cycle-selector child doesn't mount, so it never emits its
        // own cyclesLoaded event. onCyclesLoaded is idempotent; if the
        // child later mounts and re-emits, the selection is preserved.
        this.cycleService.list(this.quotationId!).subscribe({
          next: (res) => {
            this.onCyclesLoaded(res.cycles || []);
          },
          error: () => {/* cycles stay empty — viability gate falls back to locked */},
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
        // Matured / past-Matured = order body locked (PO + viability +
        // annexure live in their own dialogs/tabs and have their own
        // edit gates). The form has nothing left for the user to
        // edit at that point, so we just disable it wholesale.
        // Phase 4: locked-status set collapses to just Revised +
        // Converted. Past-Convert lifecycle position lives on the
        // per-stage entities now, not back on QuotSummary.status.
        // ``isMatured`` retained as a legacy alias for any external
        // CSS / template hooks that haven't been migrated yet.
        this.isLocked = data.status === 'Revised';
        this.isMatured = data.status === 'Converted';
        if (this.isLocked || data.status === 'Converted') {
          this.quotForm.disable();
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
          // Jump to the Working Sheet sub-tab inside Stage 1 so the
          // user lands on line-item entry right after the header save.
          this.currentStage = 'quotation';
          this.stageTab.quotation = 1;
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
    // Viability is only relevant from the Convert gate onwards. Skip
    // the network call for earlier statuses to avoid noise. Recognise
    // both the new ``Converted`` and any legacy "matured-or-later"
    // strings still in the data.
    const viabilityRelevant =
      this.poStatus === 'Submitted'
      || this.quotationStatus === 'Converted';
    if (!viabilityRelevant) {
      this.viabilityStatus = null;
      this.upstreamViabilityVersion = null;
      this.viabilityVersionCount = 0;
      return;
    }
    this.apiService.get<any>(`/quotations/${this.quotationId}/viability`).subscribe({
      next: (res) => {
        const v = res?.viability;
        this.viabilityStatus = v ? (v.status === 'Approved' ? 'Approved' : 'Draft') : null;
        this.upstreamViabilityVersion = v?.versionNo ?? null;
        // Fetch the approval-snapshot count so the stepper can show
        // "C{n}-V{m} · N versions" alongside FWS. The snapshot LIST is
        // quotation-scoped after Phase B v2; latest.versionNo IS the
        // count because the chain is monotonic.
        if (v?.viabilityId) {
          this.cycleService.listViabilitySnapshots(v.viabilityId).subscribe({
            next: (snaps) => {
              this.viabilityVersionCount = snaps?.items?.length || 0;
            },
            error: () => { this.viabilityVersionCount = 0; },
          });
        } else {
          this.viabilityVersionCount = 0;
        }
      },
      error: () => {
        this.viabilityStatus = null;
        this.upstreamViabilityVersion = null;
        this.viabilityVersionCount = 0;
      },
    });
  }

  /** Viability card opens when the PO is Submitted (Phase 1 model)
   *  OR the quotation is in any legacy "matured-or-later" status
   *  (rows still mid-migration). Stays visible through downstream
   *  stages so the user can reference it while working on annexure. */
  showViabilityCard(): boolean {
    if (!this.quotationId) return false;
    // Soft-flow: Viability unlocks the moment the cycle's FWS has at
    // least one approval snapshot. PO Submit/Mature is gone — the FWS
    // Approve button is now the singular gate into downstream stages.
    return this.fwsApprovedCount > 0;
  }

  /** Final Working Sheet is editable while the cycle is Active AND
   *  its ``fwsStatus`` is 'draft'. Approve flips fwsStatus to
   *  'approved' (locks the grid + line CRUD); Re-generate creates a
   *  fresh draft from a picked source and flips back to 'draft'.
   *  Mirrors the Draft→Approve→Re-generate lifecycle Viability and
   *  Annexure follow. */
  get canEditFinalWorkingSheet(): boolean {
    if (!this.activeCycleSelected) return false;
    const cycle = this.cycles.find(
      c => c.quotOrderCycleId === this.selectedCycleId,
    );
    return !cycle || cycle.fwsStatus !== 'approved';
  }

  /** True when the current cycle's FWS has been Approved and is
   *  therefore locked. Drives the small "Editor locked" hint next to
   *  the Re-generate button. */
  get isFwsApprovedLock(): boolean {
    const cycle = this.cycles.find(
      c => c.quotOrderCycleId === this.selectedCycleId,
    );
    return !!cycle && cycle.fwsStatus === 'approved';
  }

  /** PO Attachments stay open through every downstream stage so the
   *  KRO can drop in revised PO scans, amendments, and customer
   *  correspondence even after Submit & Mature / viability approval /
   *  annexure approval. Only locked when the cycle itself is no
   *  longer active (Complete / Abandoned) — at that point the row is
   *  archival and shouldn't accept new files. */
  get isPoAttachmentsLocked(): boolean {
    const cycle = this.cycles.find(c => c.quotOrderCycleId === this.selectedCycleId);
    if (cycle && cycle.status !== 'Active') return true;
    return false;
  }

  /** True once the viability sheet has been approved. Drives the
   *  downstream lock that hides Reject PO / Unlock-and-Edit PO /
   *  Unlock-and-Edit Viability — mutating either stage after the
   *  viability is signed off would silently invalidate the chain.
   *  Re-source from upstream is still available for users who hold
   *  the matching Unlock-and-Edit permission. */
  get viabilityApproved(): boolean {
    return this.viabilityStatus === 'Approved';
  }

  /** Viability stops being editable once an annexure exists for it
   *  (Phase 4 — read the per-stage status directly instead of the
   *  collapsed legacy strings). */
  get viabilityReadOnly(): boolean {
    // 2026-05-21 lifecycle rework: Approved viability is locked.
    // Re-generate is the explicit unlock path. Plus the universal
    // Revised-quotation hard freeze.
    return this.isLocked || this.viabilityStatus === 'Approved';
  }

  /** Open the PO-capture dialog (Approved → Matured). The dialog owns
   *  the PUT /mature call; on success we just refresh the form so the
   *  status badge, stepper, PO summary card, and toolbar all reflect
   *  the new state. */
  openCapturePoDialog(): void {
    if (!this.quotationId) return;
    const ref = this.dialog.open(QuotationPoDialogComponent, {
      data: {
        quotationId: this.quotationId,
        quotNo: this.quotForm.get('quotNo')?.value || null,
        mode: 'capture',
        defaults: {
          customerId: this.quotForm.get('customerId')?.value ?? null,
          customerContactId: this.quotForm.get('customerContactId')?.value ?? null,
          siteId: this.quotForm.get('siteId')?.value ?? null,
        },
      },
      width: '820px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.loadQuotation(this.quotationId!);
    });
  }

  /** Open the PO-edit dialog (Matured only). Server-side gate returns
   *  409 once viability has begun — surfaced as a toast inside the
   *  dialog. */
  openEditPoDialog(): void {
    if (!this.quotationId || !this.purchaseOrder) return;
    const po = this.purchaseOrder;
    const ref = this.dialog.open(QuotationPoDialogComponent, {
      data: {
        quotationId: this.quotationId,
        quotNo: this.quotForm.get('quotNo')?.value || null,
        mode: 'edit',
        defaults: {
          customerId: po.customerId,
          customerContactId: po.customerContactId,
          siteId: null,
          poNo: po.poNo,
          poDate: po.poDate,
          billingSiteId: po.billingSiteId,
          billingAddressManual: po.billingAddressManual,
          consigneeSiteId: po.consigneeSiteId,
          consigneeAddressManual: po.consigneeAddressManual,
          remarks: po.remarks,
        },
      },
      width: '820px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.loadQuotation(this.quotationId!);
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

  /** Soft-flow Slice C (2026-05-20): "Submit & Mature" and "Reject PO"
   *  were retired in favour of FWS Approve as the lifecycle advancer.
   *  ``withdrawPo`` is the replacement for both — it soft-deletes the
   *  PO row from the cycle without un-Converting the quotation. The
   *  cycle keeps running; the close precondition (≥1 active formal PO)
   *  blocks close until another PO is appended if needed. */
  withdrawPo(): void {
    if (!this.quotationId) return;
    if (!this.selectedCycleId || !this.activePo?.quotPOId) {
      this.notificationService.error(
        'Cannot withdraw: no cycle or PO is currently selected.',
      );
      return;
    }
    const cycleId = this.selectedCycleId;
    const poId = this.activePo.quotPOId;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Withdraw this PO?',
        message:
          'The PO row will be archived (soft-delete) and removed from ' +
          'the cycle\'s active list. The cycle keeps running — append ' +
          'another PO if you need to keep working in this cycle.',
        confirmText: 'Withdraw',
        confirmColor: 'warn',
        cancelText: 'Cancel',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.saving = true;
      this.apiService.delete(
        `/quotations/${this.quotationId}/cycles/${cycleId}/purchase-orders/${poId}`,
      ).subscribe({
        next: () => {
          this.saving = false;
          this.notificationService.success('PO withdrawn.');
          this.loadQuotation(this.quotationId!);
        },
        error: (e) => {
          this.saving = false;
          this.notificationService.error(e?.error?.detail || 'Failed to withdraw PO.');
        },
      });
    });
  }

  /** Stepper click handler — flips the active stage. Called when the
   *  user clicks a station on <app-quotation-stepper>. */
  onStageSelected(stage: 'quotation' | 'po' | 'viability' | 'annexure'): void {
    this.currentStage = stage;
  }

  // ---- LOI / Cycle CR — Phase 1D handlers ----

  /** Strip emits after every list refresh — auto-select the latest
   *  Active cycle (or the highest cycleNo if none Active) so the user
   *  doesn't have to click a pill on first arrival at Stage 2. */
  onCyclesLoaded(cycles: OrderCycle[]): void {
    this.cycles = cycles;
    if (cycles.length === 0) {
      this.selectedCycleId = null;
      return;
    }
    if (this.selectedCycleId
        && cycles.some(c => c.quotOrderCycleId === this.selectedCycleId)) {
      return;  // current pick still valid — don't churn the UI.
    }
    const active = cycles.find(c => c.status === 'Active');
    const fallback = cycles[cycles.length - 1];
    this.selectedCycleId = (active ?? fallback).quotOrderCycleId;
    this.loadFwsApprovalState();
  }

  onCycleSelected(cycle: OrderCycle): void {
    this.selectedCycleId = cycle.quotOrderCycleId;
    this.loadFwsApprovalState();
    // Phase 1D: pill click just flips selection. Phase 1E will wire
    // the per-cycle bundle fetch into the FWS/viability/annexure
    // panels so they show data scoped to the selected cycle.
  }

  /** Re-fetch the full cycle list from the backend. Call after any
   *  state-changing FWS action (Approve / Re-generate / Switch) so the
   *  parent's ``cycles`` cache picks up the new ``fwsStatus`` and
   *  the editor's lock-after-approve gate stays in sync. */
  private refreshCycles(): void {
    if (!this.quotationId) return;
    this.cycleService.list(this.quotationId).subscribe({
      next: (res) => {
        this.cycles = res?.cycles || [];
      },
      error: () => {/* keep stale cycles — better than wiping the strip */},
    });
  }

  /** Refresh the cached FWS approval state for the currently selected
   *  cycle. Drives the Viability gate, the "Last approved" badge on
   *  the FWS tab, the Approve / Re-approve button label flip, AND
   *  (since the cycle-status-panel was folded into the stepper) the
   *  per-stage rollup in the lifecycle stepper.
   *
   *  Also hydrates ``cyclePOs`` from the cycle bundle so the
   *  formal/LOI counts in the stepper are accurate even when the
   *  user lands directly on Viability or Annexure (in which case the
   *  PO-LOI picker child never mounts to emit ``rowsLoaded``). */
  private loadFwsApprovalState(): void {
    if (!this.quotationId || !this.selectedCycleId) {
      this.fwsApprovedCount = 0;
      this.fwsLatestLabel = null;
      this.fwsLatestApprovedAt = null;
      this.fwsLatestApprovedByName = null;
      this.fwsSnapshotList = [];
      this.fwsCurrentSnapshotId = null;
      this.cyclePOs = [];
      return;
    }
    this.cycleService
      .listFwsApprovalSnapshots(this.quotationId, this.selectedCycleId)
      .subscribe({
        next: (res) => {
          const items = res?.items || [];
          this.fwsSnapshotList = items;
          this.fwsApprovedCount = items.length;
          const latest = items[0];
          this.fwsLatestLabel = latest?.label ?? null;
          this.fwsLatestApprovedAt = latest?.approvedAt ?? null;
          this.fwsLatestApprovedByName = latest?.approvedByName ?? null;
          // Best-effort "currently shown" pointer. If we don't yet
          // know what the editor is on, assume the latest approved
          // snapshot — most fresh loads land there.
          if (this.fwsCurrentSnapshotId == null && latest) {
            this.fwsCurrentSnapshotId = latest.snapshotId;
          }
        },
        error: () => {
          this.fwsApprovedCount = 0;
          this.fwsLatestLabel = null;
          this.fwsLatestApprovedAt = null;
          this.fwsLatestApprovedByName = null;
          this.fwsSnapshotList = [];
          this.fwsCurrentSnapshotId = null;
        },
      });
    // Parallel: hydrate the cycle's PO/LOI rows so the stepper's PO
    // stop shows accurate "N formal · M LOI" counts. If the PO-LOI
    // picker is also mounted (i.e. user is on the PO stage), it will
    // re-emit rowsLoaded on its own; both writes converge on the
    // same array so this is harmless.
    this.cycleService.bundle(this.quotationId, this.selectedCycleId).subscribe({
      next: (b) => { this.cyclePOs = b?.purchaseOrders || []; },
      error: () => {/* keep whatever the picker already loaded */},
    });
  }

  /** Approve the cycle's Final Working Sheet — soft-flow's singular
   *  gate into Viability. POSTs to /cycles/{id}/fws/approve which
   *  snapshots the current line items as a new version (or fires the
   *  D3 short-circuit if content is unchanged since the last snapshot,
   *  in which case the audit event records "no changes"). */
  approveFws(): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    if (!this.canApprove || this.fwsApproving) return;
    const cycleNo = this.selectedCycleNo ?? '?';
    const isReapprove = this.fwsApprovedCount > 0;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: isReapprove
          ? `Re-approve FWS for Cycle ${cycleNo}?`
          : `Approve FWS for Cycle ${cycleNo}?`,
        message: isReapprove
          ? `Latest approved version: ${this.fwsLatestLabel}. ` +
            `Re-approving will snapshot the current line items as a new ` +
            `version (or record a no-change audit event if nothing has ` +
            `changed since the last snapshot).`
          : `This will snapshot the current Final Working Sheet line ` +
            `items as Cycle ${cycleNo} Version 1 and unlock the ` +
            `Viability stage. You can keep editing the FWS afterwards; ` +
            `each future Approve creates a new version.`,
        confirmText: isReapprove ? 'Re-approve' : 'Approve FWS',
        confirmColor: 'primary',
        cancelText: 'Cancel',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.fwsApproving = true;
      this.cycleService
        .approveFws(this.quotationId!, this.selectedCycleId!)
        .subscribe({
          next: (res) => {
            this.fwsApproving = false;
            // Track the just-approved snapshot as the "current loaded"
            // pointer — the editor's live state is, by definition,
            // identical to this snapshot at the moment of approve.
            this.fwsCurrentSnapshotId = res.snapshotId;
            if (res.created) {
              this.notificationService.success(
                `Final Working Sheet approved — ${res.label}.`,
              );
            } else {
              this.notificationService.info(
                `No changes since ${res.label} — re-approval recorded.`,
              );
            }
            this.loadFwsApprovalState();
            // Backend just flipped cycle.fwsStatus → 'approved'.
            // Refresh cycles so the FE's lock-after-approve gate
            // (canEditFinalWorkingSheet, isFwsApprovedLock) sees the
            // new state immediately.
            this.refreshCycles();
          },
          error: (e) => {
            this.fwsApproving = false;
            this.notificationService.error(
              e?.error?.detail || e?.error?.message ||
              'Failed to approve the Final Working Sheet.',
            );
          },
        });
    });
  }

  /** Open the FWS Re-generate dialog. On confirm POSTs to
   *  ``/cycles/{id}/fws/regenerate`` with the picked source, then
   *  refreshes the grid + snapshot state. Mirrors the Viability
   *  Re-generate flow so the three soft-flow stages stay
   *  consistent. */
  regenerateFws(): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    if (!this.activeCycleSelected) {
      this.notificationService.info(
        'Re-generate is only available while the cycle is Active.',
      );
      return;
    }
    const currentCycle = this.cycles.find(
      c => c.quotOrderCycleId === this.selectedCycleId,
    );
    const parentCycleId = currentCycle?.parentCycleId ?? null;
    const parentCycle = parentCycleId
      ? this.cycles.find(c => c.quotOrderCycleId === parentCycleId)
      : null;
    const parentCycleLabel = parentCycle
      ? `Cycle ${parentCycle.cycleNo} — Live FWS`
      : null;

    import('./generate-fws-dialog.component').then(m => {
      const ref = this.dialog.open(m.GenerateFwsDialogComponent, {
        data: {
          quotId: this.quotationId!,
          cycleId: this.selectedCycleId!,
          cycleNo: this.selectedCycleNo ?? 1,
          parentCycleId,
          parentCycleLabel,
        },
        width: '620px',
        maxHeight: '90vh',
      });
      ref.afterClosed().subscribe(result => {
        if (!result) return;
        this.performFwsRegenerate(result);
      });
    });
  }

  private performFwsRegenerate(
    result: {
      sourcedFromSnapshotId: number | null;
      fromQuotation: boolean;
      parentCycleId: number | null;
    },
  ): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    this.fwsRegenerating = true;
    const body: {
      sourcedFromSnapshotId?: number | null;
      fromQuotation?: boolean;
      parentCycleId?: number | null;
    } = {};
    if (result.sourcedFromSnapshotId != null) {
      body.sourcedFromSnapshotId = result.sourcedFromSnapshotId;
    } else if (result.fromQuotation) {
      body.fromQuotation = true;
    } else if (result.parentCycleId != null) {
      body.parentCycleId = result.parentCycleId;
    }
    this.cycleService
      .regenerateFws(this.quotationId, this.selectedCycleId, body)
      .subscribe({
        next: (res) => {
          this.fwsRegenerating = false;
          this.notificationService.success(
            `Final Working Sheet re-generated — ${res.inserted} row(s) inserted.`,
          );
          if (this.fwsGrid) {
            this.fwsGrid.loadDetails();
          } else {
            this.loadQuotation(this.quotationId!);
          }
          this.loadFwsApprovalState();
          // Backend flipped cycle.fwsStatus → 'draft' on regenerate.
          this.refreshCycles();
        },
        error: (e) => {
          this.fwsRegenerating = false;
          this.notificationService.error(
            e?.error?.detail || e?.error?.message ||
            'Failed to re-generate the Final Working Sheet.',
          );
        },
      });
  }

  /** Called when the user picks a row in the inline version picker.
   *  One-click switch — no confirm dialog. Auto-snapshots the current
   *  live state as the next approved version first (the stage's
   *  Approve endpoint handles the D3 short-circuit when content is
   *  unchanged), then loads the picked snapshot. No data is ever lost.
   *  No-ops if the picked id is already loaded. */
  onFwsVersionPicked(pickedId: number): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    if (pickedId === this.fwsCurrentSnapshotId) {
      this.notificationService.info(
        'That version is already loaded in the editor.',
      );
      return;
    }
    // The user with no approve permission can't auto-save — fall back
    // to a straight load (and warn them about edit loss). Everyone else
    // gets the safe save-then-load path.
    const action = this.canApprove ? 'saveAndSwitch' : 'discardAndSwitch';
    this.performFwsSwitch(pickedId, action);
  }

  /** Two-step orchestration for the FWS switch:
   *
   *  1. If ``action === 'saveAndSwitch'`` and the user can approve,
   *     fire approveFws first. If it actually creates a new snapshot,
   *     the user's edits are preserved as that version; if it D3-
   *     short-circuits, nothing is lost (content was already in the
   *     latest snapshot).
   *  2. Either way, POST /fws/approval-snapshots/{id}/restore to load
   *     the picked snapshot's data into the live editor.
   *  3. Refresh the grid + reload the approval state so the dropdown
   *     reflects any new version that was just created. */
  private performFwsSwitch(pickedId: number, action: 'saveAndSwitch' | 'discardAndSwitch'): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    this.fwsSwitching = true;
    const doLoad = () => {
      this.cycleService
        .loadFwsSnapshot(this.quotationId!, this.selectedCycleId!, pickedId)
        .subscribe({
          next: (res) => {
            this.fwsSwitching = false;
            this.fwsCurrentSnapshotId = pickedId;
            this.notificationService.success(
              `Loaded ${res.restoredFromLabel} into the editor.`,
            );
            // Restore flipped cycle.fwsStatus → 'draft' on the
            // backend; refresh so the lock state unwinds on the FE.
            this.refreshCycles();
            // Two-layer refresh so the grid always reflects the new
            // state: (1) imperative call into the grid's own loader
            // when the ViewChild is resolved, (2) a wholesale
            // loadQuotation fallback for the case where the grid is
            // currently unmounted (e.g. user navigated stage mid-
            // switch). Both end up at the cycle-aware list endpoint.
            if (this.fwsGrid) {
              this.fwsGrid.loadDetails();
            } else {
              this.loadQuotation(this.quotationId!);
            }
            this.loadFwsApprovalState();
          },
          error: (e) => {
            this.fwsSwitching = false;
            this.notificationService.error(
              e?.error?.detail || e?.error?.message ||
              'Failed to load the picked version.',
            );
          },
        });
    };
    if (action === 'saveAndSwitch') {
      // Try to snapshot the current live state first. If it D3 short-
      // circuits (nothing changed since the latest approval), no harm
      // done — we still proceed with the load.
      this.cycleService
        .approveFws(this.quotationId, this.selectedCycleId)
        .subscribe({
          next: () => doLoad(),
          error: (e) => {
            this.fwsSwitching = false;
            this.notificationService.error(
              e?.error?.detail || e?.error?.message ||
              'Failed to save current state before switching. Aborted — your edits are still in the editor.',
            );
          },
        });
    } else {
      doLoad();
    }
  }

  /** Confirm + call ``POST /quotations/{qid}/cycles`` to spawn cycle
   *  N+1. For cycles ≥ 2 we first fetch the inheritance preview so
   *  the confirm dialog can tell the user exactly what (and how much)
   *  will carry forward — avoids surprises post-start. The strip
   *  auto-refreshes on success via ``cycleStrip.reload()``. */
  startNewCycle(cycleStrip: CycleSelectorComponent): void {
    if (!this.quotationId) return;
    const nextNo = (this.cycles.length || 0) + 1;
    const latestParent = this.cycles.length
      ? this.cycles[this.cycles.length - 1]
      : null;

    const open = (message: string) => {
      const ref = this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: `Start Cycle ${nextNo}?`,
          message,
          confirmText: 'Start Cycle',
          confirmColor: 'primary',
          cancelText: 'Cancel',
        },
      });
      ref.afterClosed().subscribe(ok => {
        if (!ok) return;
        this.cycleService.start(this.quotationId!, {}).subscribe({
          next: (c) => {
            this.notificationService.success(`Cycle ${c.cycleNo} started.`);
            this.selectedCycleId = c.quotOrderCycleId;
            this.loadFwsApprovalState();
            cycleStrip.reload();
          },
          error: (e) => this.notificationService.error(
            e?.error?.message || e?.error?.detail || 'Failed to start cycle.',
          ),
        });
      });
    };

    if (!latestParent) {
      open(
        'This is the first call-off on this quotation. The new cycle ' +
        'will start empty — append a PO or LOI to begin.',
      );
      return;
    }

    this.cycleService.inheritancePreview(
      this.quotationId, latestParent.quotOrderCycleId,
    ).subscribe({
      next: (preview) => {
        const sourceLabel =
          preview.sourceType === 'viability'
            ? `Cycle ${preview.parentCycleNo}'s last approved viability`
            : preview.sourceType === 'working_sheet'
              ? `Cycle ${preview.parentCycleNo}'s working sheet`
              : null;
        const message = sourceLabel
          ? `The new cycle's Final Working Sheet will inherit ` +
            `${preview.lineCount} line${preview.lineCount === 1 ? '' : 's'} ` +
            `from ${sourceLabel}. Rates carry forward; you can edit or add ` +
            `lines after appending the first PO/LOI.`
          : `Cycle ${preview.parentCycleNo} has no inheritable rows — ` +
            `the new cycle will start empty.`;
        open(message);
      },
      // If the preview fails (network glitch / permission) we still
      // let the user proceed with a generic message — starting the
      // cycle itself doesn't depend on the preview succeeding.
      error: () => open(
        `A new call-off cycle opens and inherits rates from Cycle ` +
        `${latestParent.cycleNo} if a working sheet exists. You can ` +
        `append POs and LOIs from this strip after starting.`,
      ),
    });
  }

  /** Open the PO dialog in append-cycle mode for the currently-selected
   *  active cycle. ``isLOI`` defaults from the toggle inside the dialog
   *  but parent can preselect via the data param. */
  openAppendCycleDialog(cycleStrip: CycleSelectorComponent, asLOI: boolean): void {
    if (!this.quotationId || !this.selectedCycleId) return;
    const cycle = this.cycles.find(c => c.quotOrderCycleId === this.selectedCycleId);
    if (!cycle) return;
    const ref = this.dialog.open(QuotationPoDialogComponent, {
      data: {
        quotationId: this.quotationId,
        quotNo: this.quotForm.get('quotNo')?.value || null,
        mode: 'append-cycle',
        cycleId: cycle.quotOrderCycleId,
        cycleNo: cycle.cycleNo,
        isLOI: asLOI,
        defaults: {
          customerId: this.quotForm.get('customerId')?.value ?? null,
          customerContactId: this.quotForm.get('customerContactId')?.value ?? null,
          siteId: this.quotForm.get('siteId')?.value ?? null,
        },
      },
      width: '820px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) {
        cycleStrip.reload();
        // Clear the picker selection so onPoLoiRowsLoaded auto-picks
        // the newest row (which the picker's reload below brings in).
        // Without this we'd stay on the previous selection and the
        // user would have to manually flip the dropdown after every
        // append.
        this.selectedPoId = null;
        // Refresh the form so the legacy PO summary card + version
        // pills reflect the just-appended row. Cycle-aware FWS/
        // viability/annexure binding lands in Phase 1E.
        this.loadQuotation(this.quotationId!);
        // The picker is inside *ngIf="activePo" so it may not be
        // mounted yet on the first append (when there's no PO at
        // all). setTimeout defers until after Angular's next change-
        // detection tick, giving the *ngIf a chance to swap in.
        setTimeout(() => this.poLoiPicker?.reload());
      }
    });
  }

  // ----- Phase 3 staleness checks + Re-source dispatcher -----

  /** PO is stale when its stamped quotation version is older than the
   *  quotation's current versionNo (i.e. someone Revised the quotation
   *  after the PO was Converted). */
  isPoStaleVsQuotation(): boolean {
    if (!this.purchaseOrder) return false;
    const stamp = this.purchaseOrder.sourcedFromQuotationVersion;
    const head = this.versionNo || 1;
    return stamp != null && stamp < head;
  }

  poStaleMessage(): string {
    const stamp = this.purchaseOrder?.sourcedFromQuotationVersion ?? '?';
    const head = this.versionNo || 1;
    return (
      `Sourced from quotation v${stamp}; current quotation head is v${head}. ` +
      `Click Re-source to re-clone the Final Working Sheet from the latest quotation.`
    );
  }

  /** Single dispatcher for the Re-source button on every stage. Posts
   *  to ``/quotations/{id}/{stage}/re-source`` and reloads the form
   *  on success. */
  reSourceStage(stage: 'purchase-order' | 'viability' | 'annexure'): void {
    if (!this.quotationId) return;
    this.resourcing = true;
    this.apiService.post<any>(
      `/quotations/${this.quotationId}/${stage}/re-source`, {},
    ).subscribe({
      next: () => {
        this.resourcing = false;
        this.notificationService.success('Re-sourced from latest upstream.');
        this.loadQuotation(this.quotationId!);
      },
      error: (err) => {
        this.resourcing = false;
        this.notificationService.error(err?.error?.detail || 'Re-source failed.');
      },
    });
  }

  /** Coarse derivation of annexure status from the (legacy) flat
   *  ``QuotSummary.status``. Once the form pulls the dedicated
   *  ``/quotations/{id}/annexure`` endpoint into its load chain we'll
   *  read the per-stage status directly via /quotations/{id}/annexure. */
  private refreshAnnexureStatus(): void {
    if (!this.quotationId) return;
    this.apiService.get<any>(`/quotations/${this.quotationId}/annexure`).subscribe({
      next: (ann) => {
        if (!ann || !ann.annexureId) {
          this.annexureStatus = null;
          this.annexureVersionNo = null;
          this.annexureVersionCount = 0;
          return;
        }
        this.annexureStatus = ann.status === 'Approved' ? 'Approved' : 'Draft';
        this.annexureVersionNo = ann.versionNo ?? null;
        // Approval-snapshot count for the stepper's "· N versions"
        // suffix. Same pattern as viability above.
        this.cycleService.listAnnexureSnapshots(ann.annexureId).subscribe({
          next: (snaps) => {
            this.annexureVersionCount = snaps?.items?.length || 0;
          },
          error: () => { this.annexureVersionCount = 0; },
        });
      },
      error: () => {
        this.annexureStatus = null;
        this.annexureVersionNo = null;
        this.annexureVersionCount = 0;
      },
    });
  }

  /** Pick the latest-reached stage on first load. Lets a user who
   *  comes back to a Converted quotation land on Stage 2 immediately
   *  rather than having to click the stepper. */
  private computeDefaultStage(): 'quotation' | 'po' | 'viability' | 'annexure' {
    if (this.annexureStatus) return 'annexure';
    if (this.viabilityStatus) return 'viability';
    if (this.poStatus || this.purchaseOrder) return 'po';
    return 'quotation';
  }

  /** Phase 1 Reactivate. Replaces the legacy /revert-reject endpoint
   *  with /reactivate (clearer name, gated by CanReactivate). The
   *  backend keeps revert-reject as a backward-compat alias for one
   *  release; new clients hit reactivate. */
  reactivateQuotation(): void {
    if (!this.quotationId) return;
    this.apiService.put(`/quotations/${this.quotationId}/reactivate`, {}).subscribe({
      next: () => {
        this.notificationService.success('Quotation reactivated to Approved.');
        this.loadQuotation(this.quotationId!);
      },
      error: (e) => this.notificationService.error(e?.error?.detail || 'Failed to reactivate.'),
    });
  }

  /** Privileged Unlock-and-Edit escape valve. Opens the reason
   *  prompt; on success the audit row is written server-side and
   *  the form refreshes (ngOnInit-style flag re-eval lets the
   *  template show edit affordances again). */
  openUnlockDialog(
    stage: 'quotation' | 'purchase-order' | 'viability' | 'annexure',
    stageLabel: string,
  ): void {
    if (!this.quotationId) return;
    const ref = this.dialog.open(LifecycleUnlockDialogComponent, {
      data: {
        quotationId: this.quotationId,
        stage,
        stageLabel,
        quotNo: this.quotForm.get('quotNo')?.value || null,
      },
      width: '560px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.loadQuotation(this.quotationId!);
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
