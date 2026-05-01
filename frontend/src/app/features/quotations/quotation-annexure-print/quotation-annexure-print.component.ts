import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { Annexure } from '../quotation-annexure/quotation-annexure.component';

/**
 * Dedicated print route for the Annexure. Mirrors the exact Annexure-A
 * layout from the spec: two-column numbered rows, signature strip at the
 * bottom. Users trigger browser print via the button — @media print
 * styles hide the toolbar.
 */
@Component({
  selector: 'app-quotation-annexure-print',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="annx-toolbar no-print">
      <button mat-stroked-button (click)="back()">
        <mat-icon>arrow_back</mat-icon> Back
      </button>
      <span class="flex-spacer"></span>
      <button mat-raised-button color="primary" (click)="print()" [disabled]="!annexure">
        <mat-icon>print</mat-icon> Print
      </button>
    </div>

    @if (loading) {
      <div class="annx-loading"><mat-spinner diameter="48"></mat-spinner></div>
    } @else if (!annexure) {
      <div class="annx-empty">No annexure generated for this quotation.</div>
    } @else {
      <div class="annx-page">
        <h1 class="annx-title">ANNEXURE-A</h1>
        <p class="annx-subtitle">To read the Annexure thoroughly in conjunction with the Purchase order.</p>

        <div class="annx-header-block">
          <div class="annx-h-line"><strong>A/C:</strong> {{ annexure.clientName }}</div>
          <div class="annx-h-line">
            <strong>Attachment of PO No.</strong> {{ annexure.customerPONo }}
            <strong>Dated</strong> {{ annexure.customerPODate | date:'dd-MM-yyyy' }}
            for <strong>Rs. {{ annexure.totalBillableAmount | number:'1.2-2' }}</strong> /-
            For <strong>{{ annexure.totalQuantityMT | number:'1.2-2' }} MT</strong>.
          </div>
          <div class="annx-h-line"><strong>From:</strong> {{ annexure.preparedByName || 'KRO Name' }}</div>
          <div class="annx-h-line"><strong>To:</strong> Mr. A. Chaudhuri / Mrs. S. Basu Sengupta</div>
        </div>

        <table class="annx-table">
          <tbody>
            <tr><td class="num">1)</td><td class="label">Invoicing:</td><td>{{ annexure.invoicing }}</td></tr>
            <tr><td class="num">2)</td><td class="label">Transportation:</td><td>{{ annexure.transportationMode }}</td></tr>
            <tr><td class="num">3)</td><td class="label">TC:</td><td>{{ annexure.tcType }}</td></tr>
            <tr><td class="num">4)</td><td class="label">Payment Terms:</td><td class="pre">{{ annexure.paymentTerms }}</td></tr>
            <tr><td class="num">5)</td><td class="label">Loadability:</td>
              <td>
                @if (annexure.loadabilityQty) { {{ annexure.loadabilityQty | number:'1.2-2' }} MT per {{ annexure.transportationMode || 'vehicle' }} }
              </td>
            </tr>
            <tr><td class="num">6)</td><td class="label">Transportation Charges per MT:</td>
              <td>
                @if (annexure.transportChargesPerMT) { Rs. {{ annexure.transportChargesPerMT | number:'1.2-2' }}/- per MT for {{ annexure.transportationMode || '—' }} }
              </td>
            </tr>
            <tr><td class="num">7)</td><td class="label">Transportation Charges FOR:</td><td>{{ annexure.transportChargesFOR }}</td></tr>
            <tr><td class="num">8)</td><td class="label">Specific Length of the Material:</td><td>{{ annexure.specificLength }}</td></tr>
            <tr><td class="num">9)</td><td class="label">Tolerance:</td><td>{{ annexure.tolerance }}</td></tr>
            <tr><td class="num">10)</td><td class="label">Delivery Schedule:</td><td class="pre">{{ annexure.deliverySchedule }}</td></tr>
            <tr><td class="num">11)</td><td class="label">Transportation Realization:</td>
              <td>
                @if (annexure.transportRealizationPerMT) { Rs. {{ annexure.transportRealizationPerMT | number:'1.2-2' }}/- per MT for {{ annexure.transportationMode || '—' }} }
              </td>
            </tr>
            <tr><td class="num">12)</td><td class="label">PAN No:</td><td>{{ annexure.panNo }}</td></tr>
            <tr><td class="num">13)</td><td class="label">GST No:</td><td>{{ annexure.gstNo }}</td></tr>
            <tr><td class="num">14)</td><td class="label">Contact Person:</td><td>{{ annexure.contactPerson }}</td></tr>
            <tr><td class="num">15)</td><td class="label">Contact Person's Number:</td><td>{{ annexure.contactPersonNumber }}</td></tr>
            <tr><td class="num">16)</td><td class="label">Billing Address:</td><td class="pre">{{ annexure.billingAddress }}</td></tr>
            <tr><td class="num">17)</td><td class="label">Consignee Address:</td><td class="pre">{{ annexure.consigneeAddress }}</td></tr>
            <tr><td class="num">18)</td><td class="label">Quality of Material:</td>
              <td>
                a) {{ annexure.qualityFe }}<br/>
                b) {{ annexure.qualityStandard }}<br/>
                c) {{ annexure.qualityStandardLength }}
              </td>
            </tr>
            <tr><td class="num">19)</td><td class="label">Company:</td><td>a) {{ annexure.companyName }}</td></tr>
            <tr><td class="num">20)</td><td class="label">Bills to Sent:</td>
              <td>
                a) 1 Set to site
                &nbsp;&nbsp;&nbsp;&nbsp;b) {{ annexure.billsTo === 'HO' ? '✓ 1 Set to H.O. (Original)' : '1 Set to H.O. (Original)' }}
              </td>
            </tr>
            <tr><td class="num">21)</td><td class="label">Total Outstanding:</td>
              <td>@if (annexure.totalOutstanding != null) { Rs. {{ annexure.totalOutstanding | number:'1.2-2' }} }</td>
            </tr>
            <tr><td class="num">22)</td><td class="label">Over Due Outstanding:</td>
              <td>@if (annexure.overdueOutstanding != null) { Rs. {{ annexure.overdueOutstanding | number:'1.2-2' }} }</td>
            </tr>
            <tr><td class="num">23)</td><td class="label">Diawise break up of order:</td>
              <td>
                @if (annexure.diawiseBreakup?.length) {
                  <table class="annx-dia">
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
                }
              </td>
            </tr>
            <tr><td class="num">24)</td><td class="label">Unloading charges:</td>
              <td>
                {{ annexure.unloadingScope === 'SRMB' ? 'SRMB Scope' : 'Customer\\'s Scope' }}
                @if (annexure.unloadingScope === 'SRMB' && annexure.unloadingRate != null) {
                  (Rs. {{ annexure.unloadingRate | number:'1.2-2' }}/MT)
                }
              </td>
            </tr>
            <tr><td class="num">25)</td><td class="label">Remarks (if any):</td><td class="pre">{{ annexure.remarks }}</td></tr>
          </tbody>
        </table>

        <div class="annx-signatures">
          <div class="sig-col">
            <div class="sig-label">Prepared by</div>
            <div class="sig-line"></div>
            <div class="sig-name">{{ annexure.preparedByName || '—' }}</div>
          </div>
          <div class="sig-col">
            <div class="sig-label">Checked by</div>
            <div class="sig-line"></div>
            <div class="sig-name">{{ annexure.checkedByName || '—' }}</div>
          </div>
          <div class="sig-col">
            <div class="sig-label">Approved by</div>
            <div class="sig-line"></div>
            <div class="sig-name">{{ annexure.approvedByName || '—' }}</div>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    :host { display: block; background: #fff; min-height: 100vh; }

    .annx-toolbar {
      display: flex; align-items: center;
      padding: 12px 24px;
      border-bottom: 1px solid var(--snm-border-divider);
      background: var(--snm-glass-bg-opaque);
      position: sticky; top: 0; z-index: 10;
    }
    .flex-spacer { flex: 1; }

    .annx-loading, .annx-empty {
      display: flex; justify-content: center; align-items: center;
      min-height: 60vh;
      color: var(--snm-text-muted);
    }

    .annx-page {
      max-width: 960px;
      margin: 20px auto;
      padding: 30px 40px;
      background: #ffffff;
      color: #000;
      font-family: 'Calibri', 'Arial', sans-serif;
      font-size: 12px;
      line-height: 1.4;
      border: 1px solid #ccc;
    }

    .annx-title {
      text-align: center;
      font-size: 16px;
      font-weight: 700;
      margin: 0 0 8px;
      text-decoration: underline;
    }
    .annx-subtitle {
      text-align: center;
      font-weight: 600;
      margin: 0 0 12px;
    }

    .annx-header-block {
      margin-bottom: 18px;
    }
    .annx-h-line { margin-bottom: 4px; }
    .annx-h-line strong { font-weight: 600; }

    .annx-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 24px;
    }
    .annx-table td {
      border: 1px solid #333;
      padding: 6px 10px;
      vertical-align: top;
    }
    .annx-table td.num {
      width: 40px;
      text-align: center;
      font-weight: 600;
    }
    .annx-table td.label {
      width: 240px;
      font-weight: 600;
    }
    .annx-table td.pre { white-space: pre-wrap; }

    .annx-dia {
      width: auto;
      border-collapse: collapse;
      font-size: 11px;
      margin: 4px 0;
    }
    .annx-dia th, .annx-dia td {
      border: 1px solid #666;
      padding: 3px 10px;
      text-align: center;
    }
    .annx-dia th { background: #f0f0f0; font-weight: 600; }
    .annx-dia td.num { text-align: right; }

    .annx-signatures {
      display: flex;
      justify-content: space-between;
      margin-top: 40px;
      padding-top: 30px;
    }
    .sig-col {
      flex: 1;
      text-align: center;
      padding: 0 12px;
    }
    .sig-label { font-weight: 600; font-size: 11px; margin-bottom: 40px; }
    .sig-line { border-top: 1px solid #000; margin: 0 auto 4px; width: 80%; }
    .sig-name { font-weight: 600; font-size: 12px; }

    @media print {
      .no-print { display: none !important; }
      :host { background: #fff; }
      .annx-page {
        max-width: 100%;
        margin: 0;
        padding: 0;
        border: none;
      }
      @page {
        size: A4 portrait;
        margin: 12mm;
      }
    }
  `],
})
export class QuotationAnnexurePrintComponent implements OnInit {
  annexure: Annexure | null = null;
  loading = false;
  private quotId!: number;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.quotId = Number(this.route.snapshot.paramMap.get('id'));
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

  print(): void { window.print(); }
  back(): void { window.close(); }
}
