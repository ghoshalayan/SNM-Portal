import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatSliderModule } from '@angular/material/slider';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface PrintQuotation {
  quotId: number;
  quotNo: string;
  quotDate: string;
  subject: string;
  versionNo: number;
  status: string;
  customerName: string;
  customerCode?: string;
  customerGSTN?: string;
  customerPAN?: string;
  customerHOAddress?: string;
  customerHOSiteCode?: string;
  contactName?: string;
  contactDesignation?: string;
  contactPhone?: string;
  contactEmail?: string;
  contactAddress?: string;
  siteName?: string;
  siteAddress?: string;
  deliveryTerm?: string;
  deliveryMode?: string;
  refQuotNo?: string;
  CustomerPONo?: string;
  CustomerPODate?: string;
  remarks?: string;
  ownerName?: string;
  ownerCode?: string;
  ownerEmail?: string;
  ownerPhone?: string;
  ownerDesignation?: string;
  companyName?: string;
  companyAddress?: string;
  companyGSTN?: string;
  companyPhone?: string;
  companyEmail?: string;
  companyWebsite?: string;
  companyPAN?: string;
  companyLogoUrl?: string;
}

export interface PrintDetail {
  itemName?: string;
  itemGradeName: string;
  itemDia: number;
  itemLength: number;
  itemUnit: string;
  quantity: number;
  basicRate: number;
  totRate: number;
  gstMode: string;
  IGST: number;
  CGST: number;
  SGST: number;
  totAmount: number;
  modeOfDispatch?: string;
}

export interface PrintTnc {
  sortOrder: number;
  tncName?: string;
  tncDescription: string;
}

interface QuotFormat {
  qfId: number;
  formatName: string;
  qHeader?: string;
  qContent?: string;
  qFooter?: string;
  isCurrent: boolean;
}

interface FormatListItem {
  qfId: number;
  formatName: string;
  isCurrent: boolean;
}

@Component({
  selector: 'app-quotation-print',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatSelectModule,
    MatFormFieldModule,
    MatExpansionModule,
    MatSliderModule,
  ],
  template: `
    <!-- Loading -->
    <div *ngIf="loading" class="spinner-container">
      <mat-spinner diameter="48"></mat-spinner>
      <p>Preparing quotation for print...</p>
    </div>

    <ng-container *ngIf="!loading && quotation">

      <!-- Controls -->
      <div class="print-controls no-print">
        <button mat-raised-button color="primary" (click)="printDocument()">
          <mat-icon>print</mat-icon> Print
        </button>
        <button mat-stroked-button (click)="goBack()">
          <mat-icon>arrow_back</mat-icon> Back
        </button>
      </div>

      <!-- Settings -->
      <div class="no-print">
        <mat-expansion-panel class="settings-panel">
          <mat-expansion-panel-header>
            <mat-panel-title><mat-icon>settings</mat-icon> Print Settings</mat-panel-title>
          </mat-expansion-panel-header>

          <div class="settings-row">
            <mat-form-field appearance="outline" class="template-select">
              <mat-label>Quotation Template</mat-label>
              <mat-select [(ngModel)]="selectedFormatId" (selectionChange)="onFormatChange()">
                <mat-option [value]="0">Default Template</mat-option>
                @for (f of allFormats; track f.qfId) {
                  <mat-option [value]="f.qfId">
                    {{ f.formatName }}
                    @if (f.isCurrent) { <span class="current-badge">(Current)</span> }
                  </mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-slide-toggle [(ngModel)]="headerOnAllPages" color="primary">
              Header on all pages
            </mat-slide-toggle>
            <mat-slide-toggle [(ngModel)]="footerOnAllPages" color="primary">
              Footer on all pages
            </mat-slide-toggle>
          </div>

          <div class="margin-section">
            <h4>Page Margins (mm)</h4>
            <div class="margin-grid">
              <div class="margin-item">
                <label>Top</label>
                <div class="margin-control">
                  <mat-slider min="0" max="30" step="1" discrete [displayWith]="mmLabel">
                    <input matSliderThumb [(ngModel)]="marginTop" (valueChange)="updatePageStyle()">
                  </mat-slider>
                  <span class="margin-val">{{ marginTop }}mm</span>
                </div>
              </div>
              <div class="margin-item">
                <label>Bottom</label>
                <div class="margin-control">
                  <mat-slider min="0" max="30" step="1" discrete [displayWith]="mmLabel">
                    <input matSliderThumb [(ngModel)]="marginBottom" (valueChange)="updatePageStyle()">
                  </mat-slider>
                  <span class="margin-val">{{ marginBottom }}mm</span>
                </div>
              </div>
              <div class="margin-item">
                <label>Left</label>
                <div class="margin-control">
                  <mat-slider min="0" max="30" step="1" discrete [displayWith]="mmLabel">
                    <input matSliderThumb [(ngModel)]="marginLeft" (valueChange)="updatePageStyle()">
                  </mat-slider>
                  <span class="margin-val">{{ marginLeft }}mm</span>
                </div>
              </div>
              <div class="margin-item">
                <label>Right</label>
                <div class="margin-control">
                  <mat-slider min="0" max="30" step="1" discrete [displayWith]="mmLabel">
                    <input matSliderThumb [(ngModel)]="marginRight" (valueChange)="updatePageStyle()">
                  </mat-slider>
                  <span class="margin-val">{{ marginRight }}mm</span>
                </div>
              </div>
            </div>
          </div>
        </mat-expansion-panel>
      </div>

      <!--
        ================================================================
        REAL <table> STRUCTURE for repeating header/footer in print.
        Browsers only reliably repeat <thead>/<tfoot> from actual
        <table> elements — NOT from divs with display:table-*.
        ================================================================
      -->
      <div class="print-preview">
        <table class="page-table">

          <!-- THEAD: repeated on every printed page by the browser -->
          <thead>
            <tr><td>
              <div class="thead-content" *ngIf="headerOnAllPages">
                <ng-container *ngTemplateOutlet="headerBlock"></ng-container>
              </div>
            </td></tr>
          </thead>

          <!-- TFOOT: repeated on every printed page by the browser -->
          <tfoot>
            <tr><td>
              <div class="tfoot-content" *ngIf="footerOnAllPages">
                <ng-container *ngTemplateOutlet="footerBlock"></ng-container>
              </div>
            </td></tr>
          </tfoot>

          <!-- TBODY: content that flows and paginates -->
          <tbody>
            <tr><td>

              <!-- Inline header (first page only, when not repeating) -->
              <ng-container *ngIf="!headerOnAllPages">
                <ng-container *ngTemplateOutlet="headerBlock"></ng-container>
              </ng-container>

              <!-- Body -->
              <ng-container *ngIf="activeFormat && renderedContent; else defaultBody">
                <div class="custom-html-block" [innerHTML]="renderedContent"></div>
              </ng-container>

              <ng-template #defaultBody>
                <div class="document-title-row">
                  <h1 class="document-title">QUOTATION</h1>
                  <div class="quotation-badge no-print">
                    v{{ quotation.versionNo }} &mdash; {{ quotation.status }}
                  </div>
                </div>

                <div class="meta-grid avoid-break">
                  <div class="meta-section">
                    <h4>Bill To</h4>
                    <div class="meta-value customer-name">{{ quotation.customerName }}</div>
                    <div class="meta-value" *ngIf="quotation.contactName">Attn: {{ quotation.contactName }}</div>
                    <div class="meta-value" *ngIf="quotation.customerHOAddress">{{ quotation.customerHOAddress }}</div>
                    <div class="meta-value" *ngIf="quotation.siteName">Site: {{ quotation.siteName }}</div>
                  </div>
                  <div class="meta-section">
                    <table class="info-table">
                      <tr><td class="info-label">Quotation No</td><td class="info-value">{{ quotation.quotNo }}</td></tr>
                      <tr><td class="info-label">Date</td><td class="info-value">{{ quotation.quotDate | date:'dd-MM-yyyy' }}</td></tr>
                      <tr *ngIf="quotation.refQuotNo"><td class="info-label">Ref. Quot No</td><td class="info-value">{{ quotation.refQuotNo }}</td></tr>
                      <tr *ngIf="quotation.CustomerPONo"><td class="info-label">Customer PO</td><td class="info-value">{{ quotation.CustomerPONo }}</td></tr>
                      <tr *ngIf="quotation.CustomerPODate"><td class="info-label">PO Date</td><td class="info-value">{{ quotation.CustomerPODate | date:'dd-MM-yyyy' }}</td></tr>
                      <tr *ngIf="quotation.deliveryTerm"><td class="info-label">Delivery Term</td><td class="info-value">{{ quotation.deliveryTerm }}</td></tr>
                      <tr *ngIf="quotation.deliveryMode"><td class="info-label">Delivery Mode</td><td class="info-value">{{ quotation.deliveryMode }}</td></tr>
                    </table>
                  </div>
                </div>

                <div class="subject-row avoid-break" *ngIf="quotation.subject">
                  <strong>Sub:</strong> {{ quotation.subject }}
                </div>

                <p class="salutation">Dear Sir,</p>
                <p class="intro-line">We are pleased to quote our rates as hereunder:</p>

                <table class="items-table">
                  <thead>
                    <tr>
                      <th class="col-sno">#</th>
                      <th class="col-grade">Grade</th>
                      <th class="col-dia">Dia</th>
                      <th class="col-length">Length</th>
                      <th class="col-unit">Unit</th>
                      <th class="col-qty">Qty</th>
                      <th class="col-rate">Basic (Rs./MT)</th>
                      <th class="col-tax" *ngIf="useIGST">IGST%</th>
                      <th class="col-tax" *ngIf="!useIGST">CGST%</th>
                      <th class="col-tax" *ngIf="!useIGST">SGST%</th>
                      <th class="col-total">{{ amountColumnLabel }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr *ngFor="let item of details; let i = index">
                      <td class="center">{{ i + 1 }}</td>
                      <td>{{ item.itemGradeName }}</td>
                      <td class="center">{{ item.itemDia }}</td>
                      <td class="center">{{ item.itemLength }}</td>
                      <td class="center">{{ item.itemUnit }}</td>
                      <td class="right">{{ item.quantity | number }}</td>
                      <td class="right">{{ item.totRate | number:'1.2-2' }}</td>
                      <td class="center" *ngIf="useIGST">{{ item.IGST | number:'1.2-2' }}</td>
                      <td class="center" *ngIf="!useIGST">{{ item.CGST | number:'1.2-2' }}</td>
                      <td class="center" *ngIf="!useIGST">{{ item.SGST | number:'1.2-2' }}</td>
                      <td class="right amount">{{ item.totAmount | number:'1.2-2' }}</td>
                    </tr>
                    <tr *ngIf="details.length === 0">
                      <td [attr.colspan]="useIGST ? 9 : 10" class="center no-items">No items.</td>
                    </tr>
                  </tbody>
                  <tfoot>
                    <tr class="total-row">
                      <td [attr.colspan]="useIGST ? 8 : 9" class="right total-label">Grand Total</td>
                      <td class="right total-amount">&#8377; {{ grandTotal | number:'1.2-2' }}</td>
                    </tr>
                  </tfoot>
                </table>

                <div class="remarks-section avoid-break" *ngIf="quotation.remarks">
                  <h4>Remarks</h4>
                  <p>{{ quotation.remarks }}</p>
                </div>

                <div class="tnc-section" *ngIf="tncList.length > 0">
                  <ol class="tnc-list">
                    <li *ngFor="let term of tncList" class="avoid-break">
                      <strong *ngIf="term.tncName">{{ term.tncName }}:</strong>
                      {{ term.tncDescription }}
                    </li>
                  </ol>
                </div>
              </ng-template>

              <!-- Inline footer (end of content, when not repeating) -->
              <ng-container *ngIf="!footerOnAllPages">
                <ng-container *ngTemplateOutlet="footerBlock"></ng-container>
              </ng-container>

            </td></tr>
          </tbody>

        </table>
      </div>
    </ng-container>

    <!-- ========== SHARED TEMPLATES ========== -->

    <ng-template #headerBlock>
      <div class="hdr-wrap">
        <ng-container *ngIf="renderedHeader; else defaultHeaderTpl">
          <div class="custom-html-block" [innerHTML]="renderedHeader"></div>
        </ng-container>
        <ng-template #defaultHeaderTpl>
          <div class="company-header">
            <div class="company-logo-area">
              <div class="company-name">{{ quotation?.companyName || 'S&amp;M Portal' }}</div>
            </div>
            <div class="company-contact">
              <div *ngIf="quotation?.companyAddress">{{ quotation?.companyAddress }}</div>
              <div *ngIf="quotation?.companyPhone">Tel: {{ quotation?.companyPhone }}</div>
              <div *ngIf="quotation?.companyEmail">Email: {{ quotation?.companyEmail }}</div>
              <div *ngIf="quotation?.companyWebsite">{{ quotation?.companyWebsite }}</div>
              <div *ngIf="quotation?.companyGSTN">GSTIN: {{ quotation?.companyGSTN }}</div>
            </div>
          </div>
        </ng-template>
        <div class="header-rule"></div>
      </div>
    </ng-template>

    <ng-template #footerBlock>
      <div class="ftr-wrap">
        <div class="footer-rule"></div>
        <ng-container *ngIf="renderedFooter; else defaultFooterTpl">
          <div class="custom-html-block" [innerHTML]="renderedFooter"></div>
        </ng-container>
        <ng-template #defaultFooterTpl>
          <div class="default-footer">
            <div class="signature-block">
              <div class="signature-line"></div>
              <div class="signature-label">Authorised Signatory</div>
              <div class="company-name-small">{{ quotation?.companyName || 'S&amp;M Portal' }}</div>
            </div>
            <div class="footer-note">
              This is a computer-generated quotation.<br>
              Prices are valid for 30 days from the date of issue.
            </div>
          </div>
        </ng-template>
      </div>
    </ng-template>
  `,
  styles: [`
    :host { display: block; font-family: 'Segoe UI', Arial, sans-serif; color: #222; }

    .print-controls {
      display: flex; gap: 12px; padding: 16px 24px;
      background: #f5f5f5; border-bottom: 1px solid #ddd;
      position: sticky; top: 0; z-index: 100;
    }
    .settings-panel { max-width: 960px; margin: 12px auto 0; }
    .settings-row { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
    .template-select { width: 300px; }
    .current-badge { font-size: 11px; color: #1565c0; font-weight: 600; margin-left: 4px; }

    .margin-section { margin-top: 16px; }
    .margin-section h4 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: #555; }
    .margin-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; }
    .margin-item label { display: block; font-size: 12px; color: #666; margin-bottom: 4px; font-weight: 600; }
    .margin-control { display: flex; align-items: center; gap: 8px; }
    .margin-control mat-slider { flex: 1; }
    .margin-val { font-size: 12px; color: #333; font-weight: 600; min-width: 40px; }

    .spinner-container {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 80px; gap: 16px; color: #555;
    }

    /* Screen preview */
    .print-preview {
      max-width: 960px; margin: 24px auto; padding: 40px 48px;
      background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,.1);
    }

    /* The outer page table — invisible borders on screen */
    .page-table {
      width: 100%; border-collapse: collapse; border: none;
    }
    .page-table > thead > tr > td,
    .page-table > tfoot > tr > td,
    .page-table > tbody > tr > td {
      padding: 0; border: none; vertical-align: top;
    }

    /* Header */
    .header-rule { border-bottom: 2px solid #1565c0; margin: 12px 0 16px; }
    .company-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .company-name { font-size: 24px; font-weight: 800; color: #1565c0; letter-spacing: 1px; }
    .company-tagline { font-size: 12px; color: #666; margin-top: 4px; }
    .company-contact { text-align: right; font-size: 12px; color: #444; line-height: 1.6; }

    /* Footer */
    .footer-rule { border-top: 1px solid #ccc; margin: 24px 0 12px; }
    .default-footer { display: flex; justify-content: space-between; align-items: flex-end; }
    .signature-block { text-align: center; }
    .signature-line { width: 160px; border-top: 1px solid #333; margin-bottom: 6px; }
    .signature-label { font-size: 11px; color: #555; }
    .company-name-small { font-size: 12px; font-weight: 700; color: #1565c0; margin-top: 2px; }
    .footer-note { max-width: 400px; font-size: 10px; color: #999; text-align: right; line-height: 1.5; }

    /* Body */
    .document-title-row { display: flex; align-items: center; justify-content: space-between; margin: 0 0 16px; }
    .document-title {
      font-size: 20px; font-weight: 700; letter-spacing: 4px; color: #1565c0;
      margin: 0; border-bottom: 3px solid #1565c0; padding-bottom: 4px;
    }
    .quotation-badge {
      font-size: 12px; background: #e3f2fd; color: #1565c0;
      padding: 4px 12px; border-radius: 20px; font-weight: 600;
    }
    .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px; }
    .meta-section h4 {
      margin: 0 0 6px; font-size: 11px; font-weight: 700;
      text-transform: uppercase; color: #777; letter-spacing: .8px;
    }
    .meta-value { font-size: 13px; color: #222; line-height: 1.6; }
    .customer-name { font-size: 15px; font-weight: 600; }
    .info-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .info-label { color: #666; padding: 2px 8px 2px 0; white-space: nowrap; font-weight: 600; width: 40%; }
    .info-value { color: #222; padding: 2px 0; }
    .subject-row {
      background: #f8f9fa; border-left: 4px solid #1565c0;
      padding: 8px 14px; margin-bottom: 12px; font-size: 13px; font-weight: 600;
    }
    .salutation { margin: 8px 0 2px; font-size: 13px; }
    .intro-line { margin: 0 0 12px; font-size: 13px; }

    .items-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 16px; }
    .items-table thead tr { background-color: #1565c0; color: #fff; }
    .items-table th { padding: 6px 5px; text-align: left; font-weight: 600; white-space: nowrap; }
    .items-table td { padding: 5px; border-bottom: 1px solid #e0e0e0; }
    .items-table tbody tr:nth-child(even) { background-color: #f9f9f9; }
    .items-table tfoot .total-row td {
      border-top: 2px solid #1565c0; padding: 8px 5px; background-color: #f0f4ff;
    }
    .center { text-align: center; } .right { text-align: right; }
    .amount { font-weight: 500; }
    .total-label { font-weight: 700; font-size: 12px; }
    .total-amount { font-weight: 700; font-size: 13px; color: #1565c0; }
    .no-items { color: #999; padding: 20px; font-style: italic; }
    .col-sno { width: 4%; } .col-grade { width: 16%; } .col-dia { width: 7%; }
    .col-length { width: 8%; } .col-unit { width: 5%; } .col-qty { width: 6%; }
    .col-rate { width: 12%; } .col-tax { width: 6%; } .col-total { width: 12%; }

    .remarks-section { margin-bottom: 16px; }
    .remarks-section h4 { font-size: 12px; font-weight: 700; text-transform: uppercase; color: #555; margin-bottom: 4px; }
    .remarks-section p { font-size: 12px; color: #444; margin: 0; line-height: 1.6; }
    .tnc-section { margin-bottom: 24px; }
    .tnc-list { margin: 0; padding-left: 20px; font-size: 11px; color: #444; line-height: 1.7; }

    :host ::ng-deep .ql-align-center { text-align: center; }
    :host ::ng-deep .ql-align-right { text-align: right; }
    :host ::ng-deep .ql-align-justify { text-align: justify; }
    :host ::ng-deep .ql-indent-1 { padding-left: 3em; }
    :host ::ng-deep .ql-indent-2 { padding-left: 6em; }
    :host ::ng-deep .ql-indent-3 { padding-left: 9em; }
    :host ::ng-deep .ql-font-arial { font-family: Arial, sans-serif; }
    :host ::ng-deep .ql-font-times-new-roman { font-family: 'Times New Roman', serif; }
    :host ::ng-deep .ql-font-calibri { font-family: Calibri, sans-serif; }
    :host ::ng-deep .custom-html-block p { margin: 0; padding: 0; }
    :host ::ng-deep .custom-html-block img { max-width: 100%; height: auto; }
    :host ::ng-deep .custom-html-block table { border-collapse: collapse; width: 100%; }
    :host ::ng-deep .custom-html-block td,
    :host ::ng-deep .custom-html-block th { border: 1px solid #ccc; padding: 4px 8px; }

    /* NO @media print here — all print CSS is injected globally */
  `],
})
export class QuotationPrintComponent implements OnInit, OnDestroy {
  quotation: PrintQuotation | null = null;
  details: PrintDetail[] = [];
  tncList: PrintTnc[] = [];
  loading = false;
  quotId: number | null = null;

  activeFormat: QuotFormat | null = null;
  allFormats: FormatListItem[] = [];
  private formatsCache = new Map<number, QuotFormat>();

  selectedFormatId: number = 0;
  headerOnAllPages = false;
  footerOnAllPages = false;

  marginTop = 10;
  marginBottom = 10;
  marginLeft = 15;
  marginRight = 15;

  renderedHeader: SafeHtml | null = null;
  renderedContent: SafeHtml | null = null;
  renderedFooter: SafeHtml | null = null;

  get grandTotal(): number {
    return this.details.reduce((sum, d) => sum + (d.totAmount || 0), 0);
  }

  /**
   * True when the quotation's delivery term reads as "FOR" — token-match
   * mirrors the backend helper in quotations.py so "FOR", "FOR Site",
   * "F.O.R." (after split) all resolve consistently.
   */
  get isForDeliveryTerm(): boolean {
    const term = (this.quotation?.deliveryTerm || '').trim().toLowerCase();
    if (!term) return false;
    return term.split(/\s+/).includes('for');
  }

  /** Header label for the per-MT amount column in the line-items tables.
   * Reflects the delivery term: FOR → "FOR Price / MT", else "Ex-Factory Price / MT". */
  get amountColumnLabel(): string {
    return this.isForDeliveryTerm ? 'FOR Price / MT' : 'Ex-Factory Price / MT';
  }

  get useIGST(): boolean {
    if (this.details.length === 0) return true;
    return this.details[0].gstMode !== 'CGST_SGST';
  }

  mmLabel(value: number): string {
    return `${value}`;
  }

  constructor(
    private route: ActivatedRoute,
    private apiService: ApiService,
    private notificationService: NotificationService,
    private sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.updatePageStyle();
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.quotId = Number(id);
      this.loadPrintData(this.quotId);
    }
  }

  ngOnDestroy(): void {
    const el = document.getElementById('snm-print-page-style');
    if (el) el.remove();
  }

  updatePageStyle(): void {
    let el = document.getElementById('snm-print-page-style') as HTMLStyleElement;
    if (!el) {
      el = document.createElement('style');
      el.id = 'snm-print-page-style';
      document.head.appendChild(el);
    }
    el.textContent = `
@media print {
  @page {
    size: A4;
    margin: ${this.marginTop}mm ${this.marginRight}mm ${this.marginBottom}mm ${this.marginLeft}mm;
  }

  .no-print { display: none !important; }

  .print-preview {
    margin: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
    max-width: none !important;
  }

  .page-table {
    width: 100% !important;
  }

  .avoid-break {
    break-inside: avoid !important;
    page-break-inside: avoid !important;
  }

  h1, h4 {
    break-after: avoid !important;
    page-break-after: avoid !important;
  }

  .items-table { break-inside: auto !important; page-break-inside: auto !important; }
  .items-table tr { break-inside: avoid !important; page-break-inside: avoid !important; }
  .tnc-list li { break-inside: avoid !important; page-break-inside: avoid !important; }
  .default-footer { break-inside: avoid !important; page-break-inside: avoid !important; }
  .ftr-wrap { break-inside: avoid !important; page-break-inside: avoid !important; }

  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }

  .items-table thead tr { background-color: #1565c0 !important; color: #fff !important; }
  .document-title { color: #1565c0 !important; }
  .company-name { color: #1565c0 !important; }
}
`;
  }

  loadPrintData(id: number): void {
    this.loading = true;
    forkJoin({
      quotation: this.apiService.get<PrintQuotation>(`/quotations/${id}/print-data`),
      details: this.apiService.get<PrintDetail[]>(`/quotations/${id}/details`),
      terms: this.apiService.get<PrintTnc[]>(`/quotations/${id}/terms`),
      currentFormat: this.apiService.get<QuotFormat>('/quotation-formats/current').pipe(
        catchError(() => of(null))
      ),
      allFormats: this.apiService.get<any>('/quotation-formats', { page: 1, page_size: 100 }).pipe(
        catchError(() => of({ items: [] }))
      ),
    }).subscribe({
      next: ({ quotation, details, terms, currentFormat, allFormats }) => {
        this.quotation = quotation;
        this.details = details;
        this.tncList = terms.sort((a, b) => a.sortOrder - b.sortOrder);
        this.allFormats = allFormats.items || [];

        if (currentFormat) {
          this.formatsCache.set(currentFormat.qfId, currentFormat);
          this.selectedFormatId = currentFormat.qfId;
          this.applyFormat(currentFormat);
        } else {
          this.selectedFormatId = 0;
          this.applyDefault();
        }
        this.loading = false;
      },
      error: () => {
        this.notificationService.error('Failed to load quotation data for printing.');
        this.loading = false;
      },
    });
  }

  onFormatChange(): void {
    if (this.selectedFormatId === 0) { this.applyDefault(); return; }
    const cached = this.formatsCache.get(this.selectedFormatId);
    if (cached) { this.applyFormat(cached); return; }
    this.apiService.get<QuotFormat>(`/quotation-formats/${this.selectedFormatId}`).subscribe({
      next: (fmt) => { this.formatsCache.set(fmt.qfId, fmt); this.applyFormat(fmt); },
      error: () => {
        this.notificationService.error('Failed to load format');
        this.selectedFormatId = 0; this.applyDefault();
      },
    });
  }

  printDocument(): void {
    this.updatePageStyle();
    window.print();
  }

  goBack(): void {
    window.history.back();
  }

  private applyFormat(fmt: QuotFormat): void {
    this.activeFormat = fmt;
    this.renderedHeader = fmt.qHeader
      ? this.sanitizer.bypassSecurityTrustHtml(this.replacePlaceholders(fmt.qHeader)) : null;
    this.renderedContent = fmt.qContent
      ? this.sanitizer.bypassSecurityTrustHtml(this.replacePlaceholders(fmt.qContent)) : null;
    this.renderedFooter = fmt.qFooter
      ? this.sanitizer.bypassSecurityTrustHtml(this.replacePlaceholders(fmt.qFooter)) : null;
  }

  private applyDefault(): void {
    this.activeFormat = null;
    this.renderedHeader = null;
    this.renderedContent = null;
    this.renderedFooter = null;
  }

  replacePlaceholders(html: string): string {
    if (!html || !this.quotation) return html;
    const q = this.quotation;
    const map: Record<string, string> = {
      '{{quotNo}}': q.quotNo || '',
      '{{quotDate}}': q.quotDate ? new Date(q.quotDate).toLocaleDateString('en-IN') : '',
      '{{customerName}}': q.customerName || '',
      '{{customerCode}}': q.customerCode || '',
      '{{customerGSTN}}': q.customerGSTN || '',
      '{{customerPAN}}': q.customerPAN || '',
      '{{customerHOAddress}}': q.customerHOAddress || '',
      '{{customerHOSiteCode}}': q.customerHOSiteCode || '',
      '{{contactName}}': q.contactName || '',
      '{{contactDesignation}}': q.contactDesignation || '',
      '{{contactPhone}}': q.contactPhone || '',
      '{{contactEmail}}': q.contactEmail || '',
      '{{contactAddress}}': q.contactAddress || '',
      '{{siteName}}': q.siteName || '',
      '{{siteAddress}}': q.siteAddress || '',
      '{{subject}}': q.subject || '',
      '{{deliveryTerm}}': q.deliveryTerm || '',
      '{{deliveryMode}}': q.deliveryMode || '',
      '{{refQuotNo}}': q.refQuotNo || '',
      '{{remarks}}': q.remarks || '',
      '{{grandTotal}}': '₹ ' + this.grandTotal.toLocaleString('en-IN',
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      '{{lineItemsTable}}': this.buildLineItemsHtml(true),
      '{{withGTlineItemsTable}}': this.buildLineItemsHtml(true),
      '{{withoutGTlineItemsTable}}': this.buildLineItemsHtml(false),
      '{{tncList}}': this.buildTncHtml(),
      '{{companyName}}': q.companyName || '',
      '{{companyAddress}}': q.companyAddress || '',
      '{{companyGSTN}}': q.companyGSTN || '',
      '{{companyPhone}}': q.companyPhone || '',
      '{{companyEmail}}': q.companyEmail || '',
      '{{companyWebsite}}': q.companyWebsite || '',
      '{{companyPAN}}': q.companyPAN || '',
      // Owner placeholders
      '{{ownerName}}': q.ownerName || '',
      '{{ownerCode}}': q.ownerCode || '',
      '{{ownerEmail}}': q.ownerEmail || '',
      '{{ownerPhone}}': q.ownerPhone || '',
      '{{ownerDesignation}}': q.ownerDesignation || '',
    };
    let result = html;
    for (const [token, value] of Object.entries(map)) {
      result = result.split(token).join(value);
    }
    return result;
  }

  private buildLineItemsHtml(includeGrandTotal = true): string {
    if (this.details.length === 0) return '<p>No line items.</p>';
    const igst = this.useIGST;
    const th = 'padding:6px;';
    const gstH = igst
      ? `<th style="${th}text-align:center;">IGST%</th>`
      : `<th style="${th}text-align:center;">CGST%</th><th style="${th}text-align:center;">SGST%</th>`;
    let html = `<table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead><tr style="background-color:#1565c0;color:#fff;">
        <th style="${th}text-align:left;">#</th>
        <th style="${th}text-align:left;">Item</th>
        <th style="${th}text-align:left;">Grade</th>
        <th style="${th}text-align:center;">Dia</th>
        <th style="${th}text-align:center;">Length</th>
        <th style="${th}text-align:center;">Unit</th>
        <th style="${th}text-align:right;">Qty</th>
        <th style="${th}text-align:right;">Basic (Rs./MT)</th>
        ${gstH}
        <th style="${th}text-align:right;">${this.amountColumnLabel}</th>
        <th style="${th}text-align:left;">Mode of Dispatch</th>
      </tr></thead><tbody>`;
    const td = 'padding:5px 6px;border-bottom:1px solid #e0e0e0;';
    this.details.forEach((d, i) => {
      const bg = i % 2 === 1 ? 'background:#f9f9f9;' : '';
      const gc = igst
        ? `<td style="${td}${bg}text-align:center;">${d.IGST?.toFixed(2) ?? ''}</td>`
        : `<td style="${td}${bg}text-align:center;">${d.CGST?.toFixed(2) ?? ''}</td>
           <td style="${td}${bg}text-align:center;">${d.SGST?.toFixed(2) ?? ''}</td>`;
      html += `<tr>
        <td style="${td}${bg}text-align:center;">${i + 1}</td>
        <td style="${td}${bg}">${d.itemName || ''}</td>
        <td style="${td}${bg}">${d.itemGradeName || ''}</td>
        <td style="${td}${bg}text-align:center;">${d.itemDia || ''}</td>
        <td style="${td}${bg}text-align:center;">${d.itemLength || ''}</td>
        <td style="${td}${bg}text-align:center;">${d.itemUnit || ''}</td>
        <td style="${td}${bg}text-align:right;">${d.quantity ?? ''}</td>
        <td style="${td}${bg}text-align:right;">${d.totRate?.toFixed(2) ?? ''}</td>
        ${gc}
        <td style="${td}${bg}text-align:right;font-weight:500;">${d.totAmount?.toFixed(2) ?? ''}</td>
        <td style="${td}${bg}">${d.modeOfDispatch || ''}</td>
      </tr>`;
    });
    html += `</tbody>`;
    if (includeGrandTotal) {
      const cs = igst ? 10 : 11;  // +2 for Item + Dispatch columns
      const gt = this.grandTotal.toLocaleString('en-IN',
        { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      html += `<tfoot><tr style="border-top:2px solid #1565c0;background:#f0f4ff;">
        <td colspan="${cs}" style="padding:8px 6px;text-align:right;font-weight:700;">Grand Total</td>
        <td style="padding:8px 6px;text-align:right;font-weight:700;color:#1565c0;">₹ ${gt}</td>
      </tr></tfoot>`;
    }
    html += `</table>`;
    return html;
  }

  private buildTncHtml(): string {
    if (this.tncList.length === 0) return '';
    let html = '<ol style="margin:0;padding-left:20px;font-size:11px;line-height:1.7;">';
    for (const t of this.tncList) {
      html += `<li>${t.tncName ? '<strong>' + t.tncName + ':</strong> ' : ''}${t.tncDescription || ''}</li>`;
    }
    html += '</ol>';
    return html;
  }
}
