import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import {
  MatDialog, MatDialogModule, MatDialogRef, MAT_DIALOG_DATA,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ServerSearchSelectComponent } from '../../../shared/components/server-search-select/server-search-select.component';
import {
  ManualAddressDialogComponent,
  ManualAddressDialogResult,
} from './manual-address-dialog.component';
import { CycleService } from '../services/cycle.service';

export interface QuotationPoDialogData {
  quotationId: number;
  quotNo?: string | null;
  /** Mode controls labelling + which endpoint the dialog calls on save:
   *   - 'capture' = first time PO is being captured (calls
   *     ``PUT /quotations/{id}/mature`` which atomically creates the
   *     PO and flips the quotation status to ``Matured``).
   *   - 'edit' = updating an existing PO on a quotation already in
   *     ``Matured`` (calls ``PUT /quotations/{id}/purchase-order``).
   *     The server returns 409 if the quotation has moved past
   *     Matured — we surface that as an error toast.
   *   - 'append-cycle' = LOI / Multi-PO CR Phase 1D. Appends a fresh
   *     PO or LOI row to an Active cycle via
   *     ``POST /quotations/{qid}/cycles/{cId}/purchase-orders``.
   *     Adds an "Is LOI?" toggle to the dialog body. Requires
   *     ``cycleId`` on the data object.
   */
  mode: 'capture' | 'edit' | 'append-cycle';
  /** Active cycle id — required when ``mode === 'append-cycle'``. */
  cycleId?: number;
  /** Display label for the active cycle in the dialog header. */
  cycleNo?: number;
  /** Initial value for the isLOI toggle in append-cycle mode. */
  isLOI?: boolean;
  /** Defaults from the quotation header when capturing for the first
   *  time, OR the existing PO row when editing. */
  defaults: {
    customerId: number | null;
    customerName?: string | null;
    customerContactId: number | null;
    siteId: number | null;
    poNo?: string | null;
    poDate?: string | Date | null;
    billingSiteId?: number | null;
    billingAddressManual?: string | null;
    consigneeSiteId?: number | null;
    consigneeAddressManual?: string | null;
    remarks?: string | null;
  };
}

interface ContactOpt { customerContactId: number; contactPersonName: string; }
interface SiteOpt {
  siteId: number;
  siteAddressCode: string | null;
  addressLine: string | null;
  isAdHoc?: boolean;
}

@Component({
  selector: 'app-quotation-po-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
    MatButtonModule, MatIconModule, MatDatepickerModule, MatNativeDateModule,
    MatProgressSpinnerModule, MatDividerModule, MatTooltipModule,
    MatSlideToggleModule,
    ServerSearchSelectComponent,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>receipt_long</mat-icon>
      {{ titleText() }}
      <span class="quot-no" *ngIf="data.quotNo">— {{ data.quotNo }}</span>
      <span class="cycle-chip"
            *ngIf="data.mode === 'append-cycle' && data.cycleNo != null">
        Cycle {{ data.cycleNo }}
      </span>
    </h2>

    <!-- LOI toggle. Visible in append-cycle AND capture modes — the
         first call-off on a quotation can be captured as either an
         LOI or a formal PO. Server-side permission gate picks
         CanCaptureLOI vs CanConvert/CanSubmitPO based on this flag. -->
    <div class="loi-toggle-row" *ngIf="showLoiToggle()">
      <mat-slide-toggle [(ngModel)]="isLOI" [ngModelOptions]="{standalone: true}"
                        (ngModelChange)="onIsLoiChange()">
        Capture as Letter of Intent (LOI) — non-binding, no formal PO yet
      </mat-slide-toggle>
    </div>

    <mat-dialog-content>
      <form [formGroup]="form" class="po-form">
        <!-- PO header row. PO No is hidden when capturing as LOI
             (server auto-generates LOI-{quotId}-{seq}). The date
             label switches between "PO Date" and "LOI Date" too. -->
        <div class="row two" [class.row-one-when-loi]="isLOI">
          <mat-form-field appearance="outline" *ngIf="!isLOI">
            <mat-label>PO No *</mat-label>
            <input matInput formControlName="poNo" maxlength="50" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>{{ isLOI ? 'LOI Date *' : 'PO Date *' }}</mat-label>
            <input matInput [matDatepicker]="poPicker" formControlName="poDate" />
            <mat-datepicker-toggle matSuffix [for]="poPicker"></mat-datepicker-toggle>
            <mat-datepicker #poPicker></mat-datepicker>
          </mat-form-field>
        </div>

        <!-- Customer (server-search across the whole master) -->
        <div class="row one">
          <app-server-search-select
            endpoint="/customers/search"
            label="Customer *"
            placeholder="Defaults to quotation's customer; pick another for group billing"
            [required]="true"
            formControlName="customerId"
            (selectionChange)="onCustomerChange($event?.id || null, $event?.label || null)">
          </app-server-search-select>
        </div>

        <!-- Contact picker — same searchable-panel pattern as the
             quotation form (sticky search input, filtered list). -->
        <div class="row one">
          <mat-form-field appearance="outline">
            <mat-label>Contact Person</mat-label>
            <mat-select formControlName="customerContactId"
                        panelClass="searchable-panel"
                        (openedChange)="contactSearch = ''">
              <div class="select-search" (click)="$event.stopPropagation()">
                <mat-icon class="search-ico">search</mat-icon>
                <input placeholder="Search contacts…"
                       [(ngModel)]="contactSearch"
                       [ngModelOptions]="{standalone: true}"
                       (keydown)="$event.stopPropagation()" />
              </div>
              <mat-option [value]="null">— None —</mat-option>
              @for (c of filteredContacts(); track c.customerContactId) {
                <mat-option [value]="c.customerContactId">{{ c.contactPersonName }}</mat-option>
              }
            </mat-select>
            <mat-hint *ngIf="!contacts.length && form.value.customerId">
              No contacts on file for this customer.
            </mat-hint>
          </mat-form-field>
        </div>

        <mat-divider></mat-divider>

        <!-- Billing — searchable saved-site picker + trailing manual-entry option. -->
        <div class="row one">
          <div class="addr-block">
            <label class="addr-label">Billing Address *</label>
            <mat-form-field appearance="outline" class="addr-select"
                            *ngIf="!form.value.billingAddressManual">
              <mat-label>Pick a saved site or enter manually</mat-label>
              <mat-select [value]="form.value.billingSiteId"
                          panelClass="searchable-panel"
                          (selectionChange)="onBillingPick($event.value)"
                          (openedChange)="billingSearch = ''">
                <div class="select-search" (click)="$event.stopPropagation()">
                  <mat-icon class="search-ico">search</mat-icon>
                  <input placeholder="Search sites…"
                         [(ngModel)]="billingSearch"
                         [ngModelOptions]="{standalone: true}"
                         (keydown)="$event.stopPropagation()" />
                </div>
                @for (s of filteredSites(billingSearch); track s.siteId) {
                  <mat-option [value]="s.siteId">{{ siteLabel(s) }}</mat-option>
                }
                <mat-option value="__manual__">
                  <mat-icon class="manual-ico">add_location_alt</mat-icon>
                  Enter manually…
                </mat-option>
              </mat-select>
              <mat-hint *ngIf="!sites.length && form.value.customerId">
                No saved sites for this customer — use "Enter manually".
              </mat-hint>
            </mat-form-field>
            <div class="addr-manual" *ngIf="form.value.billingAddressManual">
              <mat-icon>place</mat-icon>
              <span class="addr-text">{{ form.value.billingAddressManual }}</span>
              <button mat-icon-button type="button" (click)="clearBillingManual()"
                      matTooltip="Clear and pick again">
                <mat-icon>close</mat-icon>
              </button>
            </div>
          </div>
        </div>

        <!-- Consignee — same pattern. -->
        <div class="row one">
          <div class="addr-block">
            <label class="addr-label">Consignee Address *</label>
            <mat-form-field appearance="outline" class="addr-select"
                            *ngIf="!form.value.consigneeAddressManual">
              <mat-label>Pick a saved site or enter manually</mat-label>
              <mat-select [value]="form.value.consigneeSiteId"
                          panelClass="searchable-panel"
                          (selectionChange)="onConsigneePick($event.value)"
                          (openedChange)="consigneeSearch = ''">
                <div class="select-search" (click)="$event.stopPropagation()">
                  <mat-icon class="search-ico">search</mat-icon>
                  <input placeholder="Search sites…"
                         [(ngModel)]="consigneeSearch"
                         [ngModelOptions]="{standalone: true}"
                         (keydown)="$event.stopPropagation()" />
                </div>
                @for (s of filteredSites(consigneeSearch); track s.siteId) {
                  <mat-option [value]="s.siteId">{{ siteLabel(s) }}</mat-option>
                }
                <mat-option value="__manual__">
                  <mat-icon class="manual-ico">add_location_alt</mat-icon>
                  Enter manually…
                </mat-option>
              </mat-select>
            </mat-form-field>
            <div class="addr-manual" *ngIf="form.value.consigneeAddressManual">
              <mat-icon>place</mat-icon>
              <span class="addr-text">{{ form.value.consigneeAddressManual }}</span>
              <button mat-icon-button type="button" (click)="clearConsigneeManual()"
                      matTooltip="Clear and pick again">
                <mat-icon>close</mat-icon>
              </button>
            </div>
          </div>
        </div>

        <mat-form-field appearance="outline" class="full" *ngIf="isLOI">
          <mat-label>LOI Text (optional)</mat-label>
          <textarea matInput rows="3" formControlName="loiText" maxlength="2000"
                    placeholder="The intent / scope language from the customer's letter — quantities, timeline, sign-off conditions, etc."></textarea>
          <mat-hint align="end">{{ loiTextLength }}/2000</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full">
          <mat-label>Remarks (optional)</mat-label>
          <textarea matInput rows="2" formControlName="remarks" maxlength="500"></textarea>
        </mat-form-field>
      </form>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary"
        (click)="save()"
        [disabled]="!canSubmit() || saving">
        <mat-spinner *ngIf="saving" diameter="16" class="inline-spinner"></mat-spinner>
        {{ saveButtonText() }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host mat-dialog-content { min-width: 720px; max-width: 820px; }
    h2[mat-dialog-title] { display: flex; align-items: center; gap: 8px; }
    .quot-no { color: rgba(0,0,0,.55); font-weight: 400; }
    .cycle-chip {
      margin-left: auto;
      padding: 2px 10px;
      border-radius: 12px;
      background: var(--snm-accent-shadow, rgba(25,118,210,.12));
      color: var(--snm-accent, #1976d2);
      font-size: 13px;
      font-weight: 500;
    }
    .loi-toggle-row {
      padding: 8px 24px 0;
      display: flex;
      align-items: center;
    }
    .po-form { display: flex; flex-direction: column; gap: 8px; padding-top: 8px; }
    .row { display: grid; gap: 12px; }
    .row.one { grid-template-columns: 1fr; }
    .row.two { grid-template-columns: 1fr 1fr; }
    /* When LOI hides PO No, the trailing date field expands to full
       width instead of leaving an awkward empty half-row. */
    .row.two.row-one-when-loi { grid-template-columns: 1fr; }
    .row mat-form-field, .row .addr-block { width: 100%; }
    .full { width: 100%; }
    mat-divider { margin: 4px 0; }
    .addr-block { display: flex; flex-direction: column; gap: 4px; }
    .addr-label { font-weight: 500; font-size: 13px; color: rgba(0,0,0,.75); }
    .addr-select { width: 100%; }
    .addr-manual {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 12px; border: 1px solid rgba(0,0,0,.18);
      border-radius: 6px; background: #fafafa;
    }
    .addr-manual .addr-text { flex: 1; font-size: 13px; }
    .manual-ico { vertical-align: middle; margin-right: 6px; color: #1976d2; }
    .inline-spinner { display: inline-block; margin-right: 6px; }
    /* Sticky search input inside searchable mat-select panels. Mirrors
       the pattern used elsewhere (quotation-form, customer-sites). */
    .select-search {
      position: sticky; top: 0; z-index: 1;
      display: flex; align-items: center; gap: 6px;
      padding: 8px 12px;
      background: var(--mat-sys-surface, #fff);
      border-bottom: 1px solid rgba(0,0,0,0.08);
    }
    .select-search input {
      flex: 1;
      border: 1px solid #ccc;
      border-radius: 4px;
      padding: 6px 8px;
      font-size: 13px;
      outline: none;
    }
    .search-ico { color: #888; font-size: 18px; width: 18px; height: 18px; }
  `],
})
export class QuotationPoDialogComponent implements OnInit {
  form: FormGroup;
  contacts: ContactOpt[] = [];
  sites: SiteOpt[] = [];
  saving = false;
  /** Snapshot of the customer name backing the current customerId.
   *  Used in the manual-address dialog header so the user knows which
   *  customer the saved-permanently option will attach the new site
   *  to. Updated when the user picks a different customer. */
  selectedCustomerName = '';
  // In-panel search state for the three searchable dropdowns. Reset on
  // open via ``(openedChange)`` so each fresh open starts from the
  // full list — mirrors the pattern used on the quotation form.
  contactSearch = '';
  billingSearch = '';
  consigneeSearch = '';
  /** isLOI toggle state — only meaningful in append-cycle mode. */
  isLOI = false;

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private dialogRef: MatDialogRef<QuotationPoDialogComponent, boolean>,
    private cycles: CycleService,
    @Inject(MAT_DIALOG_DATA) public data: QuotationPoDialogData,
  ) {
    this.isLOI = !!data.isLOI;
    const d = data.defaults;
    this.form = this.fb.group({
      // poNo validator is conditionally cleared in ngOnInit (and on
      // isLOI toggle) — LOIs get a server-generated identifier so
      // the user shouldn't be forced to type one.
      poNo: [d.poNo || '', [Validators.required, Validators.maxLength(50)]],
      poDate: [d.poDate ? new Date(d.poDate) : null, Validators.required],
      customerId: [d.customerId, Validators.required],
      customerContactId: [d.customerContactId ?? null],
      // Billing pair — exactly one populated.
      billingSiteId: [d.billingSiteId ?? d.siteId ?? null],
      billingAddressManual: [d.billingAddressManual ?? null],
      // Consignee pair — exactly one populated.
      consigneeSiteId: [d.consigneeSiteId ?? d.siteId ?? null],
      consigneeAddressManual: [d.consigneeAddressManual ?? null],
      remarks: [d.remarks ?? ''],
      // LOI-specific free-text. Only meaningful when isLOI=true; the
      // template hides this field otherwise.
      loiText: ['', [Validators.maxLength(2000)]],
    });
    this.selectedCustomerName = d.customerName || '';
    // Keep poNo's validator in sync with the isLOI toggle on init.
    this.applyIsLoiState();
  }

  ngOnInit(): void {
    if (this.form.value.customerId) {
      this.loadContactsAndSites(this.form.value.customerId);
    }
  }

  // ----- customer change -----

  onCustomerChange(newId: number | null, label: string | null): void {
    this.selectedCustomerName = label || '';
    // Clear contact + site picks since they're scoped to the previous
    // customer. The user can re-pick in the rebuilt dropdowns.
    this.form.patchValue({
      customerContactId: null,
      billingSiteId: null,
      billingAddressManual: null,
      consigneeSiteId: null,
      consigneeAddressManual: null,
    });
    this.contacts = [];
    this.sites = [];
    if (newId) this.loadContactsAndSites(newId);
  }

  private loadContactsAndSites(customerId: number): void {
    this.api.get<ContactOpt[]>(`/customers/${customerId}/contacts`).subscribe({
      next: (rs) => (this.contacts = rs || []),
      error: () => (this.contacts = []),
    });
    // Default behavior excludes ad-hoc rows; the dialog wants only the
    // canonical sites in its dropdown.
    this.api.get<SiteOpt[]>(`/customers/${customerId}/sites`).subscribe({
      next: (rs) => (this.sites = rs || []),
      error: () => (this.sites = []),
    });
  }

  siteLabel(s: SiteOpt): string {
    const code = (s.siteAddressCode || '').trim();
    const line = (s.addressLine || '').trim();
    if (code && line) return `${code} — ${line}`;
    return code || line || `Site #${s.siteId}`;
  }

  /** Filter helpers for the in-panel search inputs — case-insensitive
   *  substring match. Empty term short-circuits to the full list. */
  filteredContacts(): ContactOpt[] {
    const term = (this.contactSearch || '').trim().toLowerCase();
    if (!term) return this.contacts;
    return this.contacts.filter(c =>
      (c.contactPersonName || '').toLowerCase().includes(term),
    );
  }

  filteredSites(term: string): SiteOpt[] {
    const t = (term || '').trim().toLowerCase();
    if (!t) return this.sites;
    return this.sites.filter(s =>
      this.siteLabel(s).toLowerCase().includes(t),
    );
  }

  // ----- billing / consignee picker -----

  onBillingPick(value: number | string): void {
    if (value === '__manual__') {
      this.openManualDialog('Billing').then(res => {
        if (!res) return;
        if (res.savedSiteId) {
          // Permanent saves now create a regular site row — refresh
          // the dropdown from the server so the new entry sticks
          // across re-opens of the dialog and the Customer → Sites
          // tab. Selection is patched immediately; the reload races
          // in the background but the canonical row will be there.
          this.refreshSitesAndSelect('billing', res.savedSiteId, res.savedSiteAddressLine);
        } else if (res.addressManual) {
          this.form.patchValue({
            billingSiteId: null,
            billingAddressManual: res.addressManual,
          });
        }
      });
      return;
    }
    this.form.patchValue({
      billingSiteId: value,
      billingAddressManual: null,
    });
  }

  onConsigneePick(value: number | string): void {
    if (value === '__manual__') {
      this.openManualDialog('Consignee').then(res => {
        if (!res) return;
        if (res.savedSiteId) {
          this.refreshSitesAndSelect('consignee', res.savedSiteId, res.savedSiteAddressLine);
        } else if (res.addressManual) {
          this.form.patchValue({
            consigneeSiteId: null,
            consigneeAddressManual: res.addressManual,
          });
        }
      });
      return;
    }
    this.form.patchValue({
      consigneeSiteId: value,
      consigneeAddressManual: null,
    });
  }

  /** Patch the picked side's selection immediately so the user sees
   *  it bound, then re-fetch the canonical sites list from the
   *  server. The just-saved row is included synchronously as a
   *  fallback in case the refresh is slow — it'll be replaced by
   *  the server-canonical version once the GET resolves. */
  private refreshSitesAndSelect(
    side: 'billing' | 'consignee',
    siteId: number,
    addressLine?: string,
  ): void {
    if (!this.sites.some(s => s.siteId === siteId)) {
      this.sites = [
        ...this.sites,
        { siteId, siteAddressCode: null, addressLine: addressLine ?? null },
      ];
    }
    if (side === 'billing') {
      this.form.patchValue({ billingSiteId: siteId, billingAddressManual: null });
    } else {
      this.form.patchValue({ consigneeSiteId: siteId, consigneeAddressManual: null });
    }
    const cid = this.form.value.customerId;
    if (!cid) return;
    this.api.get<SiteOpt[]>(`/customers/${cid}/sites`).subscribe({
      next: (rs) => (this.sites = rs || this.sites),
      error: () => { /* keep the synchronous fallback */ },
    });
  }

  clearBillingManual(): void {
    this.form.patchValue({ billingAddressManual: null });
  }

  clearConsigneeManual(): void {
    this.form.patchValue({ consigneeAddressManual: null });
  }

  private openManualDialog(label: 'Billing' | 'Consignee'): Promise<ManualAddressDialogResult | null> {
    if (!this.form.value.customerId) {
      this.notify.error('Pick a customer first.');
      return Promise.resolve(null);
    }
    const ref = this.dialog.open(ManualAddressDialogComponent, {
      data: {
        customerId: this.form.value.customerId,
        customerName: this.selectedCustomerName || 'this customer',
        label,
      },
      width: '640px',
    });
    return ref.afterClosed().toPromise().then(r => r ?? null);
  }

  // ----- submit -----

  canSubmit(): boolean {
    if (!this.form.valid) return false;
    const v = this.form.value;
    const billingOk = !!v.billingSiteId !== !!(v.billingAddressManual && v.billingAddressManual.trim());
    const consigneeOk = !!v.consigneeSiteId !== !!(v.consigneeAddressManual && v.consigneeAddressManual.trim());
    return billingOk && consigneeOk;
  }

  cancel(): void {
    this.dialogRef.close(false);
  }

  save(): void {
    if (!this.canSubmit()) return;
    const v = this.form.value;
    const body: any = {
      poDate: this.formatDate(v.poDate),
      customerId: v.customerId,
      customerContactId: v.customerContactId ?? null,
      billingSiteId: v.billingSiteId ?? null,
      billingAddressManual: v.billingAddressManual?.trim() || null,
      consigneeSiteId: v.consigneeSiteId ?? null,
      consigneeAddressManual: v.consigneeAddressManual?.trim() || null,
      remarks: (v.remarks || '').trim() || null,
      isLOI: this.isLOI,
      loiText: this.isLOI ? ((v.loiText || '').trim() || null) : null,
    };
    // poNo is only sent for formal POs; the server auto-generates
    // ``LOI-{quotId}-{seq}`` when ``isLOI=true``.
    if (!this.isLOI) {
      body.poNo = (v.poNo || '').trim();
    }

    this.saving = true;

    // append-cycle mode hits the cycle-scoped endpoint; the server
    // picks the permission flag (CanCaptureLOI / CanSubmitPO) off the
    // isLOI bool so the same dialog can satisfy both flows.
    if (this.data.mode === 'append-cycle') {
      if (!this.data.cycleId) {
        this.notify.error('Missing cycle id — cannot append PO.');
        this.saving = false;
        return;
      }
      this.cycles.appendPurchaseOrder(
        this.data.quotationId, this.data.cycleId, body,
      ).subscribe({
        next: () => {
          this.notify.success(
            this.isLOI
              ? `LOI captured on Cycle ${this.data.cycleNo ?? ''}.`
              : `PO captured on Cycle ${this.data.cycleNo ?? ''}.`,
          );
          this.dialogRef.close(true);
        },
        error: (err) => {
          this.saving = false;
          this.notify.error(
            err?.error?.message || err?.error?.detail || 'Failed to append PO.',
          );
        },
      });
      return;
    }

    // Phase 1 — capture mode hits /convert (creates Draft PO + flips
    // quotation to Converted); edit mode hits /purchase-order. Both
    // accept the same body shape (including ``isLOI`` + ``loiText``).
    const path = this.data.mode === 'capture'
      ? `/quotations/${this.data.quotationId}/convert`
      : `/quotations/${this.data.quotationId}/purchase-order`;
    this.api.put(path, body).subscribe({
      next: () => {
        this.notify.success(this.successMessage());
        this.dialogRef.close(true);
      },
      error: (err) => {
        this.saving = false;
        this.notify.error(
          err?.error?.message || err?.error?.detail || 'Failed to save.',
        );
      },
    });
  }

  /** Show the LOI toggle in the modes where it makes semantic sense:
   *  ``capture`` (first call-off — the user picks PO or LOI) and
   *  ``append-cycle`` (subsequent call-offs in a cycle). Hidden in
   *  ``edit`` mode because flipping an existing row's flavour is
   *  not a supported transition. */
  showLoiToggle(): boolean {
    return this.data.mode === 'capture' || this.data.mode === 'append-cycle';
  }

  /** Track length for the LOI Text counter. */
  get loiTextLength(): number {
    const v = this.form.get('loiText')?.value ?? '';
    return typeof v === 'string' ? v.length : 0;
  }

  /** Apply / clear the ``poNo`` ``required`` validator based on the
   *  current isLOI state. Called on init and whenever the toggle
   *  flips. Re-runs validation so the save button enables/disables
   *  accordingly. */
  private applyIsLoiState(): void {
    const poNo = this.form.get('poNo');
    if (!poNo) return;
    if (this.isLOI) {
      poNo.clearValidators();
    } else {
      poNo.setValidators([Validators.required, Validators.maxLength(50)]);
    }
    poNo.updateValueAndValidity({ emitEvent: false });
  }

  /** Two-way binding hook: the slide-toggle writes ``isLOI`` directly,
   *  but we also need to re-run the validator pass. The template
   *  binds ``(ngModelChange)`` to this so toggling doesn't lock the
   *  Save button on a now-irrelevant required-poNo error. */
  onIsLoiChange(): void {
    this.applyIsLoiState();
  }

  private successMessage(): string {
    if (this.data.mode === 'capture') {
      return this.isLOI
        ? 'LOI captured. Quotation converted.'
        : 'PO captured. Quotation converted.';
    }
    if (this.data.mode === 'edit') return 'PO updated.';
    return 'Saved.';
  }

  titleText(): string {
    switch (this.data.mode) {
      case 'capture': return this.isLOI ? 'Capture LOI' : 'Capture Purchase Order';
      case 'edit': return 'Edit Purchase Order';
      case 'append-cycle': return this.isLOI ? 'Capture LOI' : 'Capture Purchase Order';
    }
  }

  saveButtonText(): string {
    switch (this.data.mode) {
      case 'capture': return 'Save & Mature';
      case 'edit': return 'Save Changes';
      case 'append-cycle': return this.isLOI ? 'Capture LOI' : 'Capture PO';
    }
  }

  private formatDate(date: Date | string | null): string | null {
    if (!date) return null;
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }
}
