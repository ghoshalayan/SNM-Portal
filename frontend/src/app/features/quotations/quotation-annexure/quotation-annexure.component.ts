import { CommonModule, Location } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuService } from '../../../core/services/menu.service';
import { LifecycleUnlockDialogComponent } from '../lifecycle-unlock-dialog/lifecycle-unlock-dialog.component';
import { StaleBannerComponent } from '../stale-banner/stale-banner.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import {
  AnnexureApprovalSnapshot,
  CycleService,
} from '../services/cycle.service';
import {
  VersionInlinePickerComponent,
  VersionInlineItem,
} from '../shared/version-inline-picker.component';

export interface DiaBreakupEntry {
  dia: string | null;
  qty: number | null;
  amount: number | null;
}

export interface Annexure {
  annexureId: number;
  quotId: number;
  viabilityId?: number | null;
  status: 'Draft' | 'Approved';
  parentAnnexureId?: number | null;
  versionNo?: number;

  clientName?: string;
  customerPONo?: string;
  customerPODate?: string;
  totalBillableAmount?: number;
  totalQuantityMT?: number;

  invoicing?: string;
  transportationMode?: string;
  tcType?: string;
  paymentTerms?: string;
  loadabilityQty?: number;
  transportChargesPerMT?: number;
  transportChargesFOR?: string;
  specificLength?: string;
  tolerance?: string;
  deliverySchedule?: string;
  transportRealizationPerMT?: number;
  panNo?: string;
  gstNo?: string;
  contactPerson?: string;
  contactPersonNumber?: string;
  billingAddress?: string;
  consigneeAddress?: string;
  qualityFe?: string;
  qualityStandard?: string;
  qualityStandardLength?: string;
  companyName?: string;
  billsTo?: string;
  totalOutstanding?: number;
  overdueOutstanding?: number;
  diawiseBreakup?: DiaBreakupEntry[];
  unloadingScope?: string;
  unloadingRate?: number;
  remarks?: string;

  preparedByName?: string;
  checkedByName?: string;
  approvedByName?: string;
  approvedon?: string;

  /** Addressee printed on the annexure ("To:" line). Editable on the
   *  form; backfilled with the legacy hardcoded value for older rows. */
  addressedTo?: string;
}

@Component({
  selector: 'app-quotation-annexure',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterModule,
    MatCardModule, MatButtonModule, MatIconModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatDatepickerModule, MatNativeDateModule,
    MatProgressSpinnerModule, MatTooltipModule, MatDialogModule,
    StaleBannerComponent,
    VersionInlinePickerComponent,
  ],
  template: `
    <mat-card class="stage-card ann-card">
      <div class="stage-card-head">
        <div class="stage-card-head-left">
          <mat-icon class="stage-card-head-icon">description</mat-icon>
          <div class="stage-card-head-text">
            <div class="stage-card-head-title">
              Annexure-A
              @if (annexure) {
                <span class="stage-status-chip" [class.is-approved]="annexure.status === 'Approved'">
                  {{ annexure.status }}
                </span>
                @if (snapshots.length > 0) {
                  <app-version-inline-picker
                    [items]="versionItems"
                    [currentId]="currentSnapshotId"
                    [busy]="saving || switching"
                    [headLabel]="'Annexure versions'"
                    (picked)="onVersionPicked($event)">
                  </app-version-inline-picker>
                }
              }
            </div>
            <div class="stage-card-head-meta">
              Structured document attached to the matured PO · auto-filled from quotation + viability
            </div>
          </div>
        </div>
        <div class="stage-card-head-actions">
          @if (annexure) {
            <button mat-stroked-button (click)="openPrint()">
              <mat-icon>print</mat-icon> Print
            </button>
            <!-- Re-generate is visible even when locked since it is
                 the explicit unlock path. The parent-supplied readOnly
                 input (Revised-quotation hard freeze) still suppresses it. -->
            @if (!readOnly) {
              <button mat-stroked-button (click)="resource()"
                      [disabled]="saving || switching"
                      matTooltip="Re-generate the annexure from a different Viability version or PO/LOI. Unlocks the editor and creates a fresh Draft.">
                <mat-icon>refresh</mat-icon> Re-generate
              </button>
            }
            @if (!isLocked) {
              <button mat-raised-button color="primary" (click)="save()" [disabled]="saving">
                <mat-icon>save</mat-icon> Save
              </button>
            }
            @if (annexure.status === 'Draft' && canApproveAnnexure) {
              <button mat-raised-button color="accent" (click)="approve()" [disabled]="saving || switching">
                <mat-icon>verified</mat-icon> Approve
              </button>
            }
            @if (annexure.status === 'Approved' && canUnlockEditAnnexure && !unlockEditHidden) {
              <button mat-stroked-button color="warn" (click)="openUnlockDialog()" [disabled]="saving"
                matTooltip="Privileged: unlock this approved annexure for in-place edits (audited)">
                <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
              </button>
            }
          }
        </div>
      </div>

      <mat-card-content>
        <!-- Soft-flow approval banner (SF5). Replaces the old "locked"
             affordance with informed-consent UX — edits post-approval
             are allowed and recorded as "(after approval)" entries in
             the activity log; the canonical signed-off version lives
             in QuotAnnexureApprovalSnapshot. -->
        @if (annexure && annexure.status === 'Approved') {
          <div class="soft-flow-banner">
            <mat-icon class="banner-icon">verified</mat-icon>
            <div class="banner-text">
              <strong>This annexure was approved.</strong>
              You can still edit it — changes are recorded as
              post-approval edits. The version signed off at approval
              is preserved in the approval-snapshot history.
            </div>
          </div>
        }
        <app-stale-banner
          *ngIf="annexure"
          [stale]="isAnnexureStale()"
          stageLabel="Annexure"
          title="Annexure is stale relative to upstream"
          [message]="annexureStaleMessage()"
          [canResource]="canUnlockEditAnnexure"
          [busy]="resourcing"
          [hideAction]="true">
        </app-stale-banner>
        @if (loading) {
          <div class="ann-spinner"><mat-spinner diameter="40"></mat-spinner></div>
        } @else if (!annexure) {
          <div class="ann-empty">
            <mat-icon>description</mat-icon>
            <p>No annexure generated yet.</p>
            <p class="hint">It will be pre-filled from the quotation + approved viability sheet.</p>
            <button mat-raised-button color="primary" (click)="generate()" [disabled]="saving || readOnly">
              <mat-icon>add</mat-icon> Generate Annexure
            </button>
          </div>
        } @else {
          <form class="ann-form" (ngSubmit)="save()" #f="ngForm">

            <!-- Header block -->
            <section class="ann-section">
              <h3>Header Block</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>Client Name (A/C)</mat-label>
                  <input matInput [(ngModel)]="annexure.clientName" name="clientName" readonly />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Customer PO No</mat-label>
                  <input matInput [(ngModel)]="annexure.customerPONo" name="customerPONo" readonly />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>PO Date</mat-label>
                  <input matInput [value]="annexure.customerPODate | date:'dd-MM-yyyy'" readonly />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Total Billable Amount (₹)</mat-label>
                  <input matInput type="number" [(ngModel)]="annexure.totalBillableAmount" name="totalBillableAmount" readonly />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Total Quantity (MT)</mat-label>
                  <input matInput type="number" [(ngModel)]="annexure.totalQuantityMT" name="totalQuantityMT" readonly />
                </mat-form-field>
              </div>
            </section>

            <!-- 1-11: Invoicing, transportation & charges -->
            <section class="ann-section">
              <h3>Invoicing & Transportation</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>1. Invoicing</mat-label>
                  <input matInput [(ngModel)]="annexure.invoicing" name="invoicing" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>2. Transportation</mat-label>
                  <mat-select [(ngModel)]="annexure.transportationMode" name="transportationMode" [disabled]="isLocked">
                    <mat-option value="Trailer">Trailer</mat-option>
                    <mat-option value="Truck">Truck</mat-option>
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>3. TC Type</mat-label>
                  <mat-select [(ngModel)]="annexure.tcType" name="tcType" [disabled]="isLocked">
                    <mat-option value="Low Alloy TC">Low Alloy TC</mat-option>
                    <mat-option value="Normal TC">Normal TC</mat-option>
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>4. Payment Terms</mat-label>
                  <textarea matInput rows="2" [(ngModel)]="annexure.paymentTerms" name="paymentTerms" [disabled]="isLocked"></textarea>
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>5. Loadability (MT / vehicle)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.loadabilityQty" name="loadabilityQty" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>6. Transport Charges (₹/MT)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.transportChargesPerMT" name="transportChargesPerMT" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>7. Transportation Charges FOR (Site)</mat-label>
                  <input matInput [(ngModel)]="annexure.transportChargesFOR" name="transportChargesFOR" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>8. Specific Length</mat-label>
                  <input matInput [(ngModel)]="annexure.specificLength" name="specificLength" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>9. Tolerance</mat-label>
                  <input matInput [(ngModel)]="annexure.tolerance" name="tolerance" [disabled]="isLocked"
                    placeholder="No excess delivery / 5%" />
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>10. Delivery Schedule</mat-label>
                  <textarea matInput rows="2" [(ngModel)]="annexure.deliverySchedule" name="deliverySchedule" [disabled]="isLocked"></textarea>
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>11. Transport Realization (₹/MT)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.transportRealizationPerMT" name="transportRealizationPerMT" [disabled]="isLocked" />
                </mat-form-field>
              </div>
            </section>

            <!-- 12-17: PAN/GST, contact, addresses -->
            <section class="ann-section">
              <h3>Party Details</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>12. PAN No</mat-label>
                  <input matInput [(ngModel)]="annexure.panNo" name="panNo" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>13. GST No</mat-label>
                  <input matInput [(ngModel)]="annexure.gstNo" name="gstNo" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>14. Contact Person</mat-label>
                  <input matInput [(ngModel)]="annexure.contactPerson" name="contactPerson" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>15. Contact Number</mat-label>
                  <input matInput [(ngModel)]="annexure.contactPersonNumber" name="contactPersonNumber" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>16. Billing Address</mat-label>
                  <textarea matInput rows="2" [(ngModel)]="annexure.billingAddress" name="billingAddress" [disabled]="isLocked"></textarea>
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>17. Consignee Address</mat-label>
                  <textarea matInput rows="2" [(ngModel)]="annexure.consigneeAddress" name="consigneeAddress" [disabled]="isLocked"></textarea>
                </mat-form-field>
              </div>
            </section>

            <!-- 18-20: Quality & dispatch -->
            <section class="ann-section">
              <h3>Quality & Dispatch</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>18a. Grade</mat-label>
                  <input matInput [(ngModel)]="annexure.qualityFe" name="qualityFe" [disabled]="isLocked"
                    placeholder="Fe-500D / Fe-550D" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>18b. Standard</mat-label>
                  <input matInput [(ngModel)]="annexure.qualityStandard" name="qualityStandard" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>18c. Standard Length</mat-label>
                  <input matInput [(ngModel)]="annexure.qualityStandardLength" name="qualityStandardLength" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>19. Company</mat-label>
                  <input matInput [(ngModel)]="annexure.companyName" name="companyName" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>20. Bills to Sent</mat-label>
                  <mat-select [(ngModel)]="annexure.billsTo" name="billsTo" [disabled]="isLocked">
                    <mat-option value="HO">1 Set to H.O. (Original)</mat-option>
                    <mat-option value="SITE">1 Set to Site</mat-option>
                  </mat-select>
                </mat-form-field>
              </div>
            </section>

            <!-- 21-22: Outstandings + 24: Unloading -->
            <section class="ann-section">
              <h3>Financials</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>21. Total Outstanding (₹)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.totalOutstanding" name="totalOutstanding" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>22. Over Due Outstanding (₹)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.overdueOutstanding" name="overdueOutstanding" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>24a. Unloading Scope</mat-label>
                  <mat-select [(ngModel)]="annexure.unloadingScope" name="unloadingScope" [disabled]="isLocked">
                    <mat-option value="CUSTOMER">Customer's scope</mat-option>
                    <mat-option value="SRMB">SRMB scope</mat-option>
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>24b. Unloading Rate (₹/MT)</mat-label>
                  <input matInput type="number" step="0.01"
                    [(ngModel)]="annexure.unloadingRate" name="unloadingRate" [disabled]="isLocked || annexure.unloadingScope !== 'SRMB'" />
                </mat-form-field>
              </div>
            </section>

            <!-- 23: Diawise breakup (auto, sourced from a viability version) -->
            <section class="ann-section">
              <div class="ann-breakup-head">
                <h3>23. Diawise Breakup of Order</h3>
                @if (viabilityVersions.length > 1 && !isLocked) {
                  <div class="ann-breakup-source">
                    <mat-form-field appearance="outline" class="ann-source-pick">
                      <mat-label>Source viability version</mat-label>
                      <mat-select [(value)]="selectedViabilityId" [disabled]="refilling">
                        @for (v of viabilityVersions; track v.entityId) {
                          <mat-option [value]="v.entityId">
                            v{{ v.versionNo }} · {{ v.status || 'Draft' }}
                            @if (v.isHead) { · head }
                          </mat-option>
                        }
                      </mat-select>
                    </mat-form-field>
                    <button mat-stroked-button type="button" color="primary"
                            (click)="refillFromSelectedViability()"
                            [disabled]="refilling || !selectedViabilityId
                                        || selectedViabilityId === annexure.viabilityId"
                            matTooltip="Recompute the breakup, totals and freight/MT from the selected viability version.">
                      <mat-icon>refresh</mat-icon>
                      Refill from this viability
                    </button>
                  </div>
                }
              </div>
              <p class="ann-breakup-source-hint" *ngIf="annexure.viabilityId && currentViabilityLabel()">
                <mat-icon>info</mat-icon>
                Currently sourced from {{ currentViabilityLabel() }}
              </p>
              @if (annexure.diawiseBreakup?.length) {
                <table class="ann-dia-table">
                  <thead>
                    <tr><th>Dia</th><th>Qty (MT)</th><th>Amount (₹)</th></tr>
                  </thead>
                  <tbody>
                    @for (d of annexure.diawiseBreakup; track d.dia) {
                      <tr>
                        <td>{{ d.dia }}</td>
                        <td class="num">{{ d.qty | number:'1.2-2' }}</td>
                        <td class="num">{{ d.amount | number:'1.2-2' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              } @else {
                <p class="ann-empty-hint">No dia breakdown available.</p>
              }
            </section>

            <!-- 25: Remarks — wrapped in .ann-grid so the .ann-wide
                 class (grid-column 1/-1) actually spans the full form
                 width. Without the grid context the form field falls
                 back to its narrow intrinsic width. -->
            <section class="ann-section">
              <h3>25. Remarks</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>Remarks</mat-label>
                  <textarea matInput rows="3" [(ngModel)]="annexure.remarks" name="remarks" [disabled]="isLocked"></textarea>
                </mat-form-field>
              </div>
            </section>

            <!-- Letterhead controls the "From" and "To" lines
                 printed above the body table. The Prepared-By name
                 doubles as the From signature. -->
            <section class="ann-section">
              <h3>Letterhead</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>From (KRO Name)</mat-label>
                  <input matInput [(ngModel)]="annexure.preparedByName"
                         name="fromName" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline" class="ann-wide">
                  <mat-label>To (Addressee)</mat-label>
                  <input matInput [(ngModel)]="annexure.addressedTo"
                         name="addressedTo" [disabled]="isLocked"
                         placeholder="Mr. A. Chaudhuri / Mrs. S. Basu Sengupta" />
                </mat-form-field>
              </div>
            </section>

            <!-- Signatures — Prepared mirrors the From line above
                 (single source of truth); Checked & Approved are
                 separate signers captured at sign-off time. -->
            <section class="ann-section">
              <h3>Signatures</h3>
              <div class="ann-grid">
                <mat-form-field appearance="outline">
                  <mat-label>Prepared by (KRO)</mat-label>
                  <input matInput [(ngModel)]="annexure.preparedByName" name="preparedByName" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Checked by (HOD)</mat-label>
                  <input matInput [(ngModel)]="annexure.checkedByName" name="checkedByName" [disabled]="isLocked" />
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Approved by (HOD)</mat-label>
                  <input matInput [value]="annexure.approvedByName || '—'" readonly />
                </mat-form-field>
              </div>
            </section>
          </form>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    /* Card chrome (head strip, status chip, action cluster) is shared
       across all four lifecycle stage cards via the stage-card classes
       in styles.scss. Only the annexure-specific bits live here. */
    /* Soft-flow approval banner — same shape as the viability component. */
    .soft-flow-banner {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 10px 14px;
      margin-bottom: 12px;
      background: rgba(255, 220, 100, 0.18);
      border: 1px solid rgba(200, 150, 30, 0.45);
      border-left: 4px solid rgba(200, 150, 30, 0.85);
      border-radius: 6px;
      color: var(--snm-text-primary);
      font-size: 13px;
      line-height: 1.5;
    }
    .soft-flow-banner .banner-icon {
      color: rgba(200, 150, 30, 1);
      margin-top: 1px;
      flex: 0 0 auto;
    }
    .soft-flow-banner .banner-text strong { display: block; }

    .ann-spinner { display: flex; justify-content: center; padding: 40px 0; }
    .ann-empty {
      text-align: center; padding: 40px 20px;
      color: var(--snm-text-muted);
    }
    .ann-empty mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.6; }
    .ann-empty .hint { font-size: 12px; margin-bottom: 16px; }

    .ann-form { padding: 12px 0; }
    .ann-section {
      padding: 16px 0;
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .ann-section:last-child { border-bottom: none; }
    .ann-section h3 {
      margin: 0 0 12px;
      font-size: 13px;
      font-weight: 700;
      color: var(--snm-accent-dark);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .ann-breakup-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    .ann-breakup-head h3 { margin: 0; }
    .ann-breakup-source {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .ann-source-pick { min-width: 220px; margin-bottom: -1.25em; }
    .ann-breakup-source-hint {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin: 0 0 8px;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .ann-breakup-source-hint mat-icon {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--snm-accent);
    }

    .ann-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px 16px;
    }
    .ann-wide { grid-column: 1 / -1; }
    .ann-grid mat-form-field { width: 100%; }

    .ann-dia-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .ann-dia-table th, .ann-dia-table td {
      padding: 6px 10px;
      border: 1px solid var(--snm-border-divider);
      text-align: center;
    }
    .ann-dia-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .ann-dia-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .ann-empty-hint { color: var(--snm-text-muted); font-size: 12px; padding: 12px 0; }
  `],
})
export class QuotationAnnexureComponent implements OnChanges {
  @Input({ required: true }) quotId!: number;
  /** Cycle context — passed by the parent (quotation-form) since the
   *  annexure component doesn't know about cycles directly. Required
   *  by the Generate dialog (Slice E) so the PO/LOI picker can scope
   *  to the right cycle. Optional for back-compat with older callers. */
  @Input() cycleId: number | null = null;
  @Input() cycleNo: number | null = null;
  @Input() canApprove = false;
  /** Granted to the Commercial HOD role. Two effects:
   *    1. Approve button visibility — only shown when this is true.
   *    2. Override of the post-approval lock — Commercial HODs can edit
   *       an annexure even after status = Approved. */
  @Input() canApproveAnnexure = false;
  @Input() readOnly = false;
  // Phase 1 Unlock-and-Edit flag for the Annexure stage. Resolved
  // from the menu service in the constructor. Distinct from
  // ``canApproveAnnexure``: that flag has historically also let
  // Commercial HODs edit approved annexures (pre-Phase-1 escape
  // valve); the new flag is the formal per-stage Unlock pattern and
  // also writes a LifecycleUnlockAudit row.
  canUnlockEditAnnexure = false;
  /** Feature flag — hides the in-place Unlock & Edit button regardless
   *  of permission. Restore / Re-source (which share the same gate) are
   *  unaffected. Flip to ``false`` to re-enable. */
  readonly unlockEditHidden = true;
  // Phase 3 — current upstream head versions. Annexure auto-fills
  // from quotation + PO + viability, so it watches all three.
  @Input() upstreamQuotationVersion: number | null = null;
  @Input() upstreamPoVersion: number | null = null;
  @Input() upstreamViabilityVersion: number | null = null;
  @Input() resourcing = false;
  /** Fires when the user clicks Re-source on the stale banner. */
  @Output() reSource = new EventEmitter<void>();

  /** Fires after generate / approve so the parent quotation-form can re-sync
   * its status, stepper, and tab locks without a page refresh. */
  @Output() stageChanged = new EventEmitter<void>();

  annexure: Annexure | null = null;
  loading = false;
  saving = false;

  // ---- Version-switch state (soft-flow Slice H) ----
  /** Cached snapshot list for the current annexure head. Drives the
   *  Switch Version button visibility and the dialog's picker. */
  snapshots: AnnexureApprovalSnapshot[] = [];
  /** Snapshot id the editor was last loaded from. */
  currentSnapshotId: number | null = null;
  /** True while a version-switch round-trip is in flight. */
  switching = false;

  /** Inline-picker items derived from ``snapshots``. */
  get versionItems(): VersionInlineItem[] {
    return this.snapshots.map(s => ({
      id: s.snapshotId,
      label: `V${s.versionNo}`,
      approvedAt: s.approvedAt,
      approvedByName: s.approvedByName,
    }));
  }

  // Issue #4 — viability-version picker for the Diawise Breakup
  // section. ``viabilityVersions`` is the full chain (head + archived)
  // for the quotation. ``selectedViabilityId`` tracks the dropdown's
  // current pick; defaults to the head once both lists arrive.
  viabilityVersions: Array<{
    entityId: number;
    versionNo: number;
    isHead: boolean;
    status: string | null;
  }> = [];
  selectedViabilityId: number | null = null;
  refilling = false;

  get isLocked(): boolean {
    // 2026-05-21 lifecycle rework: Approved annexure is locked.
    // Re-generate is the explicit unlock path (archives the head's
    // content into a snapshot and creates a fresh Draft from a
    // picked Viability + PO source). The parent-supplied
    // ``readOnly`` (Revised quotation hard freeze) still wins too.
    return !!this.readOnly || this.annexure?.status === 'Approved';
  }

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private router: Router,
    private location: Location,
    private menuService: MenuService,
    private cycleService: CycleService,
  ) {
    this.canUnlockEditAnnexure = this.menuService.hasPermission(
      'Quotations', 'canUnlockEditAnnexure',
    );
  }

  ngOnChanges(c: SimpleChanges): void {
    if (c['quotId']?.currentValue) this.load();
  }

  load(): void {
    if (!this.quotId) return;
    this.loading = true;
    this.api.get<Annexure | null>(`/quotations/${this.quotId}/annexure`).subscribe({
      next: (res) => {
        this.loading = false;
        this.annexure = res || null;
        if (this.annexure) {
          this.selectedViabilityId = this.annexure.viabilityId ?? null;
          this.loadViabilityVersions();
          this.refreshSnapshotList();
        } else {
          this.snapshots = [];
          this.currentSnapshotId = null;
        }
      },
      error: (e) => {
        this.loading = false;
        this.notify.error(e?.error?.detail || 'Failed to load annexure.');
      },
    });
  }

  /** Re-fetch the approval snapshot list for the current annexure
   *  head. Used after load, approve, and switch so the picker stays
   *  in sync with the backend. */
  private refreshSnapshotList(): void {
    if (!this.annexure?.annexureId) {
      this.snapshots = [];
      this.currentSnapshotId = null;
      return;
    }
    this.cycleService.listAnnexureSnapshots(this.annexure.annexureId).subscribe({
      next: (res) => {
        this.snapshots = res?.items || [];
        if (this.currentSnapshotId == null && this.snapshots.length > 0) {
          this.currentSnapshotId = this.snapshots[0].snapshotId;
        }
      },
      error: () => { this.snapshots = []; },
    });
  }

  /** Pull the viability version chain for the dropdown picker. The
   *  existing ``/{quot_id}/viability/versions`` endpoint returns
   *  every version (head + archived) keyed off ``entityId`` —
   *  perfect input for the picker. Failures fall back to a single-
   *  option list (just the currently-sourced version) so the user
   *  isn't blocked. */
  private loadViabilityVersions(): void {
    if (!this.quotId) return;
    this.api.get<any[]>(`/quotations/${this.quotId}/viability/versions`)
      .subscribe({
        next: (rs) => {
          this.viabilityVersions = (rs || []).map(r => ({
            entityId: r.entityId,
            versionNo: r.versionNo,
            isHead: !!r.isHead,
            status: r.status ?? null,
          }));
          if (this.annexure && !this.selectedViabilityId
              && this.viabilityVersions.length) {
            this.selectedViabilityId = this.viabilityVersions[0].entityId;
          }
        },
        error: () => { this.viabilityVersions = []; },
      });
  }

  /** Hit ``POST /annexure/{aid}/refill-from-viability/{vid}``. The
   *  backend recomputes Diawise Breakup + totals + freight/MT from
   *  the picked viability and re-emits the annexure. */
  refillFromSelectedViability(): void {
    if (!this.annexure || !this.selectedViabilityId) return;
    if (this.selectedViabilityId === this.annexure.viabilityId) return;
    this.refilling = true;
    this.api.post<Annexure>(
      `/annexure/${this.annexure.annexureId}/refill-from-viability/`
      + `${this.selectedViabilityId}`, {},
    ).subscribe({
      next: (res) => {
        this.refilling = false;
        this.annexure = res;
        this.notify.success('Annexure breakup refilled from selected viability.');
        this.stageChanged.emit();
      },
      error: (e) => {
        this.refilling = false;
        this.notify.error(
          e?.error?.message || e?.error?.detail || 'Failed to refill annexure.',
        );
      },
    });
  }

  /** User clicked a past annexure version in the version-selector
   *  dropdown. Phase-2 time-travel preview is a larger UX change;
   *  for now we surface a hint that the action is acknowledged and
   *  point the user at the restore path. Once the read-only-preview
   *  pane lands this handler will swap in a banner instead. */
  onAnnexureVersionClicked(annexureId: number): void {
    this.notify.info(
      `Selected annexure #${annexureId}. Use Restore to roll this version forward; ` +
      `read-only preview will land in a follow-up.`,
    );
  }

  /** Human-readable label for the viability version currently
   *  sourced. Shown as a small hint above the breakup table so the
   *  user knows which version's numbers they're looking at. */
  currentViabilityLabel(): string | null {
    if (!this.annexure?.viabilityId) return null;
    const match = this.viabilityVersions.find(
      v => v.entityId === this.annexure!.viabilityId,
    );
    if (!match) return `viability #${this.annexure.viabilityId}`;
    return `v${match.versionNo} (${match.status || 'Draft'})`;
  }

  /** Internal POST helper — shared between the direct generate path
   *  and the picker-dialog path so success/error handling stays in
   *  one place. */
  private postGenerate(
    sourcedFromViabilityId: number | null,
    sourcedFromPOId: number | null,
  ): void {
    if (!this.quotId) return;
    const body: Record<string, number> = {};
    if (sourcedFromViabilityId != null) body['sourcedFromViabilityId'] = sourcedFromViabilityId;
    if (sourcedFromPOId != null) body['sourcedFromPOId'] = sourcedFromPOId;
    this.saving = true;
    this.api.post<Annexure>(`/quotations/${this.quotId}/annexure`, body).subscribe({
      next: (res) => {
        this.saving = false;
        this.annexure = res;
        this.notify.success('Annexure generated.');
        this.stageChanged.emit();
      },
      error: (e) => {
        this.saving = false;
        this.notify.error(e?.error?.detail || 'Failed to generate annexure.');
      },
    });
  }

  /** Slice E — opens the source-picker dialog (viability + PO/LOI)
   *  before generating. Falls back to a direct POST with defaults if
   *  the parent didn't pass cycle context (back-compat). */
  generate(): void {
    if (!this.quotId) return;
    if (!this.cycleId) {
      // No cycle context — legacy direct generate with backend defaults.
      this.postGenerate(null, null);
      return;
    }
    const cycleId = this.cycleId;
    const cycleNo = this.cycleNo ?? 1;
    import('./generate-annexure-dialog.component').then(
      ({ GenerateAnnexureDialogComponent }) => {
        const ref = this.dialog.open(GenerateAnnexureDialogComponent, {
          data: { quotId: this.quotId, cycleId, cycleNo },
          width: '560px',
        });
        ref.afterClosed().subscribe((result) => {
          if (!result) return;
          this.postGenerate(
            result.sourcedFromViabilityId,
            result.sourcedFromPOId,
          );
        });
      },
    );
  }

  save(): void {
    if (!this.annexure) return;
    this.saving = true;
    const payload = this.annexure;  // partial update — backend ignores unknown
    this.api.put<Annexure>(`/annexure/${this.annexure.annexureId}`, payload).subscribe({
      next: (res) => {
        this.saving = false;
        this.annexure = res;
        this.notify.success('Saved.');
      },
      error: (e) => {
        this.saving = false;
        this.notify.error(e?.error?.detail || 'Save failed.');
      },
    });
  }

  approve(): void {
    if (!this.annexure) return;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Approve Annexure',
        message: 'Once approved, the annexure becomes read-only. Continue?',
        confirmText: 'Approve',
        confirmColor: 'primary',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok || !this.annexure) return;
      this.saving = true;
      this.api.put<Annexure>(`/annexure/${this.annexure.annexureId}/approve`, {}).subscribe({
        next: (res) => {
          this.saving = false;
          this.annexure = res;
          this.notify.success('Annexure approved.');
          this.refreshSnapshotList();
          this.stageChanged.emit();
        },
        error: (e) => {
          this.saving = false;
          this.notify.error(e?.error?.detail || 'Approval failed.');
        },
      });
    });
  }

  /** Re-generate the annexure: open the dialog with the two source
   *  pickers (every Viability version in the cycle + every PO/LOI),
   *  pre-select the current sources, and on confirm POST to
   *  /annexure/{id}/resource. Only the auto-populated header + diawise
   *  are refreshed on the backend — user-edited body fields stay
   *  intact.
   *
   *  Works on both Draft and Approved annexures (soft-flow). The
   *  previously approved snapshot stays frozen in history; the next
   *  Approve creates the next snapshot version. */
  resource(): void {
    if (!this.annexure?.annexureId) return;
    const cycleId = (this.annexure as any).quotOrderCycleId as number | null;
    if (!cycleId || !this.cycleNo) {
      this.notify.error(
        'Cannot re-generate: this annexure has no cycle context. Refresh the page and try again.',
      );
      return;
    }
    const annexureId = this.annexure.annexureId;
    const currentViabilityId = this.annexure.viabilityId ?? null;
    import('./generate-annexure-dialog.component').then(({ GenerateAnnexureDialogComponent }) => {
      const ref = this.dialog.open(GenerateAnnexureDialogComponent, {
        data: {
          quotId: this.quotId,
          cycleId,
          cycleNo: this.cycleNo!,
          title: 'Re-generate Annexure',
          confirmLabel: 'Re-generate',
          hint:
            'Pick a Viability version and/or PO/LOI to re-generate ' +
            'the annexure header + diawise from. Your edited body ' +
            'fields (payment terms, delivery schedule, remarks, ' +
            'signatures) stay exactly as they are.',
          preSelectedViabilityId: currentViabilityId,
          // Phase B follow-up: pass the current viabilityId so the
          // dialog can fetch the cycle's full viability snapshot
          // chain and render every past version (not just the head).
          listAllViabilityVersions: true,
        },
        width: '620px',
        maxHeight: '90vh',
      });
      ref.afterClosed().subscribe(result => {
        if (!result || !result.sourcedFromViabilityId || !result.sourcedFromPOId) {
          return;
        }
        this.performResource(
          annexureId,
          result.sourcedFromViabilityId,
          result.sourcedFromPOId,
          result.sourcedFromViabilitySnapshotId ?? null,
        );
      });
    });
  }

  private performResource(
    annexureId: number,
    viabilityId: number,
    poId: number,
    viabilitySnapshotId: number | null,
  ): void {
    this.saving = true;
    const body: Record<string, number> = {
      sourcedFromViabilityId: viabilityId,
      sourcedFromPOId: poId,
    };
    if (viabilitySnapshotId != null) {
      body['sourcedFromViabilitySnapshotId'] = viabilitySnapshotId;
    }
    this.api.post<Annexure>(`/annexure/${annexureId}/resource`, body).subscribe({
      next: (res) => {
        this.saving = false;
        this.annexure = res;
        this.notify.success(
          'Annexure re-generated — header and diawise refreshed from the picked Viability + PO.',
        );
        this.stageChanged.emit();
      },
      error: (e) => {
        this.saving = false;
        this.notify.error(
          e?.error?.detail || e?.error?.message ||
          'Failed to re-generate the annexure.',
        );
      },
    });
  }

  /** Called when the user picks a row in the inline version picker.
   *  One-click switch — no confirm dialog. Auto-approves the current
   *  live state first so nothing is lost (D3 short-circuit handles
   *  the no-change case), then loads the picked snapshot. No-ops if
   *  the picked row is already loaded. */
  onVersionPicked(pickedId: number): void {
    if (!this.annexure?.annexureId) return;
    if (pickedId === this.currentSnapshotId) {
      this.notify.info('That version is already loaded in the editor.');
      return;
    }
    const action = this.canApproveAnnexure ? 'saveAndSwitch' : 'discardAndSwitch';
    this.performVersionSwitch(pickedId, action);
  }

  private performVersionSwitch(pickedId: number, action: 'saveAndSwitch' | 'discardAndSwitch'): void {
    if (!this.annexure?.annexureId) return;
    this.switching = true;
    const annexureId = this.annexure.annexureId;
    const doLoad = () => {
      this.cycleService.loadAnnexureSnapshot(annexureId, pickedId).subscribe({
        next: (res) => {
          this.switching = false;
          this.currentSnapshotId = pickedId;
          this.notify.success(`Loaded ${res.restoredFromLabel} into the editor.`);
          this.load();
          this.stageChanged.emit();
        },
        error: (e) => {
          this.switching = false;
          this.notify.error(
            e?.error?.detail || e?.error?.message ||
            'Failed to load the picked version.',
          );
        },
      });
    };
    if (action === 'saveAndSwitch') {
      this.api.put<Annexure>(`/annexure/${annexureId}/approve`, {}).subscribe({
        next: () => doLoad(),
        error: (e) => {
          this.switching = false;
          this.notify.error(
            e?.error?.detail || e?.error?.message ||
            'Failed to save current state before switching. Aborted — your edits are still in the editor.',
          );
        },
      });
    } else {
      doLoad();
    }
  }

  /** Phase 3 staleness — annexure auto-fills from three upstream
   *  sources, so it's stale when any of the stamped versions is
   *  older than the matching head. */
  isAnnexureStale(): boolean {
    if (!this.annexure) return false;
    const a = this.annexure as any;
    if (
      this.upstreamQuotationVersion != null
      && a.sourcedFromQuotationVersion != null
      && a.sourcedFromQuotationVersion < this.upstreamQuotationVersion
    ) return true;
    if (
      this.upstreamPoVersion != null
      && a.sourcedFromPOVersion != null
      && a.sourcedFromPOVersion < this.upstreamPoVersion
    ) return true;
    if (
      this.upstreamViabilityVersion != null
      && a.sourcedFromViabilityVersion != null
      && a.sourcedFromViabilityVersion < this.upstreamViabilityVersion
    ) return true;
    return false;
  }

  annexureStaleMessage(): string {
    if (!this.annexure) return '';
    const a = this.annexure as any;
    const parts: string[] = [];
    if (
      this.upstreamQuotationVersion != null
      && a.sourcedFromQuotationVersion != null
      && a.sourcedFromQuotationVersion < this.upstreamQuotationVersion
    ) {
      parts.push(
        `Quotation v${a.sourcedFromQuotationVersion} → v${this.upstreamQuotationVersion}`,
      );
    }
    if (
      this.upstreamPoVersion != null
      && a.sourcedFromPOVersion != null
      && a.sourcedFromPOVersion < this.upstreamPoVersion
    ) {
      parts.push(
        `PO v${a.sourcedFromPOVersion} → v${this.upstreamPoVersion}`,
      );
    }
    if (
      this.upstreamViabilityVersion != null
      && a.sourcedFromViabilityVersion != null
      && a.sourcedFromViabilityVersion < this.upstreamViabilityVersion
    ) {
      parts.push(
        `Viability v${a.sourcedFromViabilityVersion} → v${this.upstreamViabilityVersion}`,
      );
    }
    return (
      `Out of date: ${parts.join('; ')}. ` +
      `Re-source to regenerate the annexure from current upstream heads.`
    );
  }

  /** Privileged Unlock-and-Edit on the annexure. Opens the shared
   *  reason-prompt dialog; on success the audit row is written and
   *  the parent re-fetches so locked-state UI clears. */
  openUnlockDialog(): void {
    if (!this.annexure) return;
    const ref = this.dialog.open(LifecycleUnlockDialogComponent, {
      data: {
        quotationId: this.quotId,
        stage: 'annexure',
        stageLabel: 'Annexure',
      },
      width: '560px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.stageChanged.emit();
    });
  }

  openPrint(): void {
    if (!this.quotId) return;
    // serializeUrl alone returns "/quotations/123/annexure-print" — when
    // window.open() resolves that on a sub-path host (e.g. /snmportal/) the
    // base href gets dropped and IIS returns 404. prepareExternalUrl()
    // prepends APP_BASE_HREF so the absolute URL is correct in both
    // local dev (base /) and the IIS sub-path deployment.
    const path = this.router.serializeUrl(
      this.router.createUrlTree(['/quotations', this.quotId, 'annexure-print']),
    );
    const fullUrl = this.location.prepareExternalUrl(path);
    window.open(fullUrl, '_blank');
  }
}
