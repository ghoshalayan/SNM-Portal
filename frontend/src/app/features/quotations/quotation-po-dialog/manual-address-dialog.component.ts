import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  MatDialogModule, MatDialogRef, MAT_DIALOG_DATA,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface ManualAddressDialogData {
  /** Customer the address will be saved under (when the user opts to). */
  customerId: number;
  customerName: string;
  /** Either 'Billing' or 'Consignee' — drives the dialog title only. */
  label: 'Billing' | 'Consignee';
}

/**
 * Result returned to the parent PO dialog when the user clicks "Use
 * Address". Two shapes:
 *   - savedSiteId set: a new CustomerSite row was created via
 *     POST /customers/{id}/sites/ad-hoc; bind by FK.
 *   - addressManual set: free-text only; goes onto the PO row.
 * The two are mutually exclusive — the parent uses whichever is
 * present to populate the matching pair on its body.
 */
export interface ManualAddressDialogResult {
  savedSiteId?: number;
  /** Echoed back so the parent can show the address inline without
   *  re-fetching the new CustomerSite. */
  savedSiteAddressLine?: string;
  addressManual?: string;
}

@Component({
  selector: 'app-manual-address-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
    MatButtonModule, MatIconModule, MatCheckboxModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>edit_location_alt</mat-icon>
      {{ data.label }} Address — Manual Entry
    </h2>
    <mat-dialog-content>
      <p class="hint">
        Enter the address for this PO. You can use it just for this PO,
        or save it permanently under
        <strong>{{ data.customerName }}</strong> for re-use.
      </p>

      <mat-form-field appearance="outline" class="full">
        <mat-label>Address Line *</mat-label>
        <textarea matInput rows="2" [(ngModel)]="addressLine"
          placeholder="House / building, street, locality, city"></textarea>
      </mat-form-field>

      <!-- Country → State → District cascade. Sourced from
           /users/my-locations so the user only sees locations they
           have access to (the backend re-validates on save). -->
      <div class="row three">
        <mat-form-field appearance="outline">
          <mat-label>Country *</mat-label>
          <mat-select [(ngModel)]="country"
                      (selectionChange)="onCountryChange($event.value)"
                      panelClass="searchable-panel"
                      (openedChange)="countrySearch = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search country…"
                     [(ngModel)]="countrySearch"
                     [ngModelOptions]="{standalone: true}"
                     (keydown)="$event.stopPropagation()" />
            </div>
            @for (c of filteredCountries(); track c.countryName) {
              <mat-option [value]="c.countryName">{{ c.countryName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>State *</mat-label>
          <mat-select [(ngModel)]="state"
                      (selectionChange)="onStateChange($event.value)"
                      [disabled]="!states.length"
                      panelClass="searchable-panel"
                      (openedChange)="stateSearch = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search state…"
                     [(ngModel)]="stateSearch"
                     [ngModelOptions]="{standalone: true}"
                     (keydown)="$event.stopPropagation()" />
            </div>
            @for (s of filteredStates(); track s.StateName) {
              <mat-option [value]="s.StateName">{{ s.StateName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>District</mat-label>
          <mat-select [(ngModel)]="dist"
                      [disabled]="!districts.length"
                      panelClass="searchable-panel"
                      (openedChange)="distSearch = ''">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search district…"
                     [(ngModel)]="distSearch"
                     [ngModelOptions]="{standalone: true}"
                     (keydown)="$event.stopPropagation()" />
            </div>
            @for (d of filteredDistricts(); track d.districName) {
              <mat-option [value]="d.districName">{{ d.districName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      </div>

      <div class="row three">
        <mat-form-field appearance="outline">
          <mat-label>PIN</mat-label>
          <input matInput [(ngModel)]="pin" maxlength="10" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Contact Person (optional)</mat-label>
          <input matInput [(ngModel)]="contactPerson1" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Phone (optional)</mat-label>
          <input matInput [(ngModel)]="contactPhone1" />
        </mat-form-field>
      </div>

      <div class="row two">
        <mat-form-field appearance="outline">
          <mat-label>Email (optional)</mat-label>
          <input matInput type="email" [(ngModel)]="contactEmail1" />
        </mat-form-field>
        <mat-checkbox [(ngModel)]="isHeadOffice" class="ho-toggle">
          Mark as Head Office
        </mat-checkbox>
      </div>

      <mat-checkbox [(ngModel)]="saveAsPermanent" class="save-toggle">
        Save this address permanently under {{ data.customerName }}
        <span class="save-sub">
          (creates a regular site row — shows up in this customer's
          Sites tab and the Site picker on future POs)
        </span>
      </mat-checkbox>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary"
        (click)="confirm()"
        [disabled]="!addressLine.trim() || saving">
        <mat-spinner *ngIf="saving" diameter="16" class="inline-spinner"></mat-spinner>
        Use Address
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host mat-dialog-content { min-width: 640px; }
    .hint { color: rgba(0,0,0,.7); font-size: 13px; margin: 0 0 12px; }
    .full { width: 100%; }
    .row { display: grid; gap: 12px; margin-bottom: 4px; }
    .row.three { grid-template-columns: repeat(3, 1fr); }
    .row.two { grid-template-columns: 1fr 1fr; align-items: center; }
    .row mat-form-field { width: 100%; }
    .ho-toggle { padding-left: 4px; }
    .save-toggle { display: block; margin-top: 4px; }
    .save-sub { display: block; color: rgba(0,0,0,.6); font-size: 12px; margin-top: 2px; }
    h2[mat-dialog-title] { display: flex; align-items: center; gap: 8px; }
    .inline-spinner { display: inline-block; margin-right: 6px; }
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
export class ManualAddressDialogComponent implements OnInit {
  addressLine = '';
  country = '';
  state = '';
  dist = '';
  pin = '';
  contactPerson1 = '';
  contactPhone1 = '';
  contactEmail1 = '';
  isHeadOffice = false;
  saveAsPermanent = false;
  saving = false;

  // Location reference data — sourced from /users/my-locations so the
  // user only sees locations they're allowed to save against. Same
  // pattern as the customer-sites SiteDialogComponent.
  countries: any[] = [];
  states: any[] = [];
  districts: any[] = [];
  allAccess = false;
  countrySearch = '';
  stateSearch = '';
  distSearch = '';

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<ManualAddressDialogComponent, ManualAddressDialogResult | null>,
    @Inject(MAT_DIALOG_DATA) public data: ManualAddressDialogData,
  ) {}

  ngOnInit(): void {
    this.loadMyLocations();
  }

  private loadMyLocations(): void {
    this.api.get<any>('/users/my-locations').subscribe({
      next: (loc) => {
        this.allAccess = !!loc?.allAccess;
        this.countries = loc?.countries || [];
        // Default to single accessible country to skip a click.
        if (this.countries.length === 1) {
          this.country = this.countries[0].countryName;
          this.onCountryChange(this.country);
        }
      },
      error: () => {
        this.notify.error('Failed to load location list.');
      },
    });
  }

  onCountryChange(countryName: string): void {
    this.state = '';
    this.dist = '';
    this.districts = [];
    const c = this.countries.find((x: any) => x.countryName === countryName);
    this.states = c?.states || [];
  }

  onStateChange(stateName: string): void {
    this.dist = '';
    if (!stateName) { this.districts = []; return; }
    const stateEntry = this.states.find((s: any) => s.StateName === stateName);
    // If the user has unrestricted access (or unrestricted within this
    // state), pull the full district list from the master. Otherwise
    // use the restricted subset already on /users/my-locations.
    if (this.allAccess || stateEntry?.allDistricts) {
      this.api.get<any[]>('/masters/districts', { state: stateName }).subscribe({
        next: (data) => (this.districts = data || []),
        error: () => (this.districts = []),
      });
    } else {
      this.districts = (stateEntry?.districts || [])
        .map((d: any) => ({ districName: d.districName }));
    }
  }

  filteredCountries(): any[] {
    const t = this.countrySearch.trim().toLowerCase();
    if (!t) return this.countries;
    return this.countries.filter((c: any) =>
      (c.countryName || '').toLowerCase().includes(t),
    );
  }

  filteredStates(): any[] {
    const t = this.stateSearch.trim().toLowerCase();
    if (!t) return this.states;
    return this.states.filter((s: any) =>
      (s.StateName || '').toLowerCase().includes(t),
    );
  }

  filteredDistricts(): any[] {
    const t = this.distSearch.trim().toLowerCase();
    if (!t) return this.districts;
    return this.districts.filter((d: any) =>
      (d.districName || '').toLowerCase().includes(t),
    );
  }

  cancel(): void {
    this.dialogRef.close(null);
  }

  confirm(): void {
    const line = this.addressLine.trim();
    if (!line) return;
    if (!this.saveAsPermanent) {
      // Throwaway — return text only. The PO row stores it as a
      // free-text address; the parent doesn't care about state/dist.
      this.dialogRef.close({ addressManual: line });
      return;
    }
    // Persist as a regular CustomerSite (isAdHoc=False, server-side)
    // so it shows up in the Site picker and Customer → Sites tab on
    // future opens. Field set mirrors the regular New Site form;
    // siteAddressCode is auto-generated server-side from the
    // customer code + next index. Backend re-checks location
    // access against the requester's role on POST.
    this.saving = true;
    this.api.post<any>(`/customers/${this.data.customerId}/sites/ad-hoc`, {
      addressLine: line,
      state: this.state || null,
      dist: this.dist || null,
      PIN: this.pin || null,
      contactPerson1: this.contactPerson1 || null,
      contactPhone1: this.contactPhone1 || null,
      contactEmail1: this.contactEmail1 || null,
      isHeadOffice: this.isHeadOffice,
    }).subscribe({
      next: (site) => {
        this.dialogRef.close({
          savedSiteId: site.siteId,
          savedSiteAddressLine: site.addressLine,
        });
      },
      error: (err) => {
        this.saving = false;
        this.notify.error(err?.error?.detail || 'Failed to save address.');
      },
    });
  }
}
