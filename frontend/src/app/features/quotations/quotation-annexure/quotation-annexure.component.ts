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
import { VersionSelectorComponent } from '../version-selector/version-selector.component';
import { StaleBannerComponent } from '../stale-banner/stale-banner.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

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
    VersionSelectorComponent,
    StaleBannerComponent,
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
                <app-version-selector
                  [quotId]="quotId"
                  stage="annexure"
                  [headVersion]="annexure.versionNo || 1"
                  [canRestore]="canUnlockEditAnnexure"
                  (restored)="stageChanged.emit()">
                </app-version-selector>
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
            @if (!isLocked) {
              <button mat-raised-button color="primary" (click)="save()" [disabled]="saving">
                <mat-icon>save</mat-icon> Save
              </button>
            }
            @if (annexure.status === 'Draft' && canApproveAnnexure) {
              <button mat-raised-button color="accent" (click)="approve()" [disabled]="saving">
                <mat-icon>verified</mat-icon> Approve
              </button>
            }
            @if (annexure.status === 'Approved' && canUnlockEditAnnexure) {
              <button mat-stroked-button color="warn" (click)="openUnlockDialog()" [disabled]="saving"
                matTooltip="Privileged: unlock this approved annexure for in-place edits (audited)">
                <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
              </button>
            }
          }
        </div>
      </div>

      <mat-card-content>
        <app-stale-banner
          *ngIf="annexure"
          [stale]="isAnnexureStale()"
          stageLabel="Annexure"
          title="Annexure is stale relative to upstream"
          [message]="annexureStaleMessage()"
          [canResource]="canUnlockEditAnnexure"
          [busy]="resourcing"
          (resource)="reSource.emit()">
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

            <!-- 23: Diawise breakup (auto) -->
            <section class="ann-section">
              <h3>23. Diawise Breakup of Order</h3>
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

  get isLocked(): boolean {
    if (this.readOnly) return true;
    // Approved → locked, EXCEPT for Commercial HODs who keep edit
    // rights post-approval per the canApproveAnnexure permission flag.
    if (this.annexure?.status === 'Approved' && !this.canApproveAnnexure) {
      return true;
    }
    return false;
  }

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private router: Router,
    private location: Location,
    private menuService: MenuService,
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
      },
      error: (e) => {
        this.loading = false;
        this.notify.error(e?.error?.detail || 'Failed to load annexure.');
      },
    });
  }

  generate(): void {
    if (!this.quotId) return;
    this.saving = true;
    this.api.post<Annexure>(`/quotations/${this.quotId}/annexure`, {}).subscribe({
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
          this.stageChanged.emit();
        },
        error: (e) => {
          this.saving = false;
          this.notify.error(e?.error?.detail || 'Approval failed.');
        },
      });
    });
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
