import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { MatRadioModule } from '@angular/material/radio';
import { QuillRichEditorComponent } from '../../../shared/components/quill-editor/quill-rich-editor.component';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import {
  Alignment,
  ColumnAlignment,
  ColumnId,
  COLUMN_LABELS,
  COLUMN_ORDER,
  DEFAULT_PRINT_STYLE,
  PrintStyle,
  RoundingMode,
  formatPrintNumber,
  formatTaxPercent,
  resolvePrintStyle,
} from '../../quotations/quotation-print/print-style.helpers';

const PLACEHOLDERS = [
  { token: '{{quotNo}}', desc: 'Quotation Number', group: 'Quotation' },
  { token: '{{quotDate}}', desc: 'Date', group: 'Quotation' },
  { token: '{{subject}}', desc: 'Subject', group: 'Quotation' },
  { token: '{{deliveryTerm}}', desc: 'Delivery Term', group: 'Quotation' },
  { token: '{{deliveryMode}}', desc: 'Delivery Mode', group: 'Quotation' },
  { token: '{{refQuotNo}}', desc: 'Ref. Quotation No', group: 'Quotation' },
  { token: '{{remarks}}', desc: 'Remarks', group: 'Quotation' },
  { token: '{{customerName}}', desc: 'Customer Name', group: 'Customer' },
  { token: '{{customerCode}}', desc: 'Customer Code', group: 'Customer' },
  { token: '{{customerGSTN}}', desc: 'Customer GSTN', group: 'Customer' },
  { token: '{{customerPAN}}', desc: 'Customer PAN', group: 'Customer' },
  { token: '{{customerHOAddress}}', desc: 'HO Address', group: 'Customer' },
  { token: '{{customerHOSiteCode}}', desc: 'HO Site Code', group: 'Customer' },
  { token: '{{contactName}}', desc: 'Contact Person', group: 'Contact' },
  { token: '{{contactDesignation}}', desc: 'Contact Designation', group: 'Contact' },
  { token: '{{contactPhone}}', desc: 'Contact Phone', group: 'Contact' },
  { token: '{{contactEmail}}', desc: 'Contact Email', group: 'Contact' },
  { token: '{{contactAddress}}', desc: 'Contact Address', group: 'Contact' },
  { token: '{{siteName}}', desc: 'Site Code', group: 'Delivery Site' },
  { token: '{{siteAddress}}', desc: 'Site Full Address', group: 'Delivery Site' },
  { token: '{{lineItemsTable}}', desc: 'Line Items with Grand Total', group: 'Content' },
  { token: '{{withGTlineItemsTable}}', desc: 'Line Items with Grand Total', group: 'Content' },
  { token: '{{withoutGTlineItemsTable}}', desc: 'Line Items without Grand Total', group: 'Content' },
  { token: '{{grandTotal}}', desc: 'Grand Total (text)', group: 'Content' },
  { token: '{{tncList}}', desc: 'T&C List', group: 'Content' },
  { token: '{{ownerName}}', desc: 'Owner Name', group: 'Owner' },
  { token: '{{ownerCode}}', desc: 'Owner Code', group: 'Owner' },
  { token: '{{ownerEmail}}', desc: 'Owner Email', group: 'Owner' },
  { token: '{{ownerPhone}}', desc: 'Owner Phone', group: 'Owner' },
  { token: '{{ownerDesignation}}', desc: 'Owner Designation', group: 'Owner' },
  { token: '{{companyName}}', desc: 'Company Name', group: 'Company' },
  { token: '{{companyAddress}}', desc: 'Full Address', group: 'Company' },
  { token: '{{companyGSTN}}', desc: 'GSTN', group: 'Company' },
  { token: '{{companyPAN}}', desc: 'PAN', group: 'Company' },
  { token: '{{companyPhone}}', desc: 'Phone', group: 'Company' },
  { token: '{{companyEmail}}', desc: 'Email', group: 'Company' },
  { token: '{{companyWebsite}}', desc: 'Website', group: 'Company' },
];

@Component({
  selector: 'app-quotation-format-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSlideToggleModule,
    MatTabsModule,
    MatIconModule,
    MatTooltipModule,
    MatSelectModule,
    MatRadioModule,
    QuillRichEditorComponent,
  ],
  template: `
    <!-- Top bar -->
    <div class="dialog-header">
      <div class="header-left">
        <mat-icon class="header-icon">article</mat-icon>
        <h2>{{ isEdit ? 'Edit' : 'New' }} Quotation Format</h2>
      </div>
      <div class="header-right">
        <button mat-icon-button (click)="dialogRef.close()" matTooltip="Close">
          <mat-icon>close</mat-icon>
        </button>
      </div>
    </div>

    <mat-dialog-content class="fullscreen-content">
      @if (loadingDetail) {
        <div class="loading-spinner">Loading format...</div>
      } @else {
        <form [formGroup]="form" class="editor-layout">

          <!-- Left sidebar -->
          <div class="sidebar">
            <div class="sidebar-section">
              <h3>Format Info</h3>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Format Name</mat-label>
                <input matInput formControlName="formatName" placeholder="e.g. Standard Quotation" />
                <mat-error *ngIf="form.get('formatName')?.hasError('required')">Required</mat-error>
              </mat-form-field>
              <mat-slide-toggle formControlName="isCurrent" color="primary">Set as Current</mat-slide-toggle>
            </div>

            <div class="sidebar-section">
              <h3>
                <mat-icon class="section-icon">data_object</mat-icon>
                Placeholders
              </h3>
              <p class="hint">Click to copy, then paste in editor.</p>

              @for (group of placeholderGroups; track group.name) {
                <div class="placeholder-group">
                  <div class="group-label">{{ group.name }}</div>
                  <div class="placeholder-chips">
                    @for (p of group.items; track p.token) {
                      <button class="placeholder-chip"
                        [matTooltip]="p.desc"
                        (click)="copyPlaceholder(p.token)">
                        {{ p.token }}
                      </button>
                    }
                  </div>
                </div>
              }
            </div>
          </div>

          <!-- Right: Tabbed editors -->
          <div class="editor-area">
            <mat-tab-group animationDuration="0ms" class="editor-tabs">

              <mat-tab>
                <ng-template mat-tab-label>
                  <mat-icon>vertical_align_top</mat-icon> Header
                </ng-template>
                <div class="editor-pane">
                  <div class="editor-hint">
                    Document header — company logo, address, quotation no & date.
                    <strong>Paste from MS Word</strong> to keep formatting.
                  </div>
                  <app-quill-rich-editor
                    formControlName="qHeader"
                    placeholder="Paste header content from Word or design here..."
                    [editorHeight]="editorHeight">
                  </app-quill-rich-editor>
                </div>
              </mat-tab>

              <mat-tab>
                <ng-template mat-tab-label>
                  <mat-icon>article</mat-icon> Content
                </ng-template>
                <div class="editor-pane">
                  <div class="editor-hint">
                    Quotation body — use <code>{{'{{lineItemsTable}}'}}</code> for line items,
                    <code>{{'{{tncList}}'}}</code> for terms. Create tables, paste from Word/Excel.
                  </div>
                  <app-quill-rich-editor
                    formControlName="qContent"
                    placeholder="Design quotation body with placeholders..."
                    [editorHeight]="editorHeight">
                  </app-quill-rich-editor>
                </div>
              </mat-tab>

              <mat-tab>
                <ng-template mat-tab-label>
                  <mat-icon>vertical_align_bottom</mat-icon> Footer
                </ng-template>
                <div class="editor-pane">
                  <div class="editor-hint">
                    Document footer — signature block, company seal area, disclaimers.
                  </div>
                  <app-quill-rich-editor
                    formControlName="qFooter"
                    placeholder="Paste footer content from Word or design here..."
                    [editorHeight]="editorHeight">
                  </app-quill-rich-editor>
                </div>
              </mat-tab>

              <mat-tab>
                <ng-template mat-tab-label>
                  <mat-icon>palette</mat-icon> Print Styling
                </ng-template>
                <div class="editor-pane styling-pane">

                  <div class="styling-header">
                    <div class="editor-hint">
                      Controls how the items table renders on the printed
                      quotation. Changes apply only when this format is
                      selected on the print page.
                    </div>
                    <button mat-stroked-button type="button" (click)="resetStylingDefaults()"
                            matTooltip="Restore the factory defaults: blue header, white text, 0 decimals, ceiling rounding.">
                      <mat-icon>restart_alt</mat-icon> Reset to Defaults
                    </button>
                  </div>

                  <!-- Header colors -->
                  <section class="styling-section">
                    <h4>Header Colors</h4>
                    <div class="row two-col">
                      <mat-form-field appearance="outline">
                        <mat-label>Header Background</mat-label>
                        <input matInput formControlName="headerBgColor"
                               placeholder="e.g. saffron or #FF9933" />
                        <input matSuffix type="color" class="color-swatch"
                               [value]="resolveHexForSwatch(form.value.headerBgColor || '#1565c0')"
                               (input)="form.controls['headerBgColor'].setValue($any($event.target).value)" />
                      </mat-form-field>
                      <mat-form-field appearance="outline">
                        <mat-label>Header Text Color</mat-label>
                        <input matInput formControlName="headerTextColor"
                               placeholder="e.g. white or #FFFFFF" />
                        <input matSuffix type="color" class="color-swatch"
                               [value]="resolveHexForSwatch(form.value.headerTextColor || '#FFFFFF')"
                               (input)="form.controls['headerTextColor'].setValue($any($event.target).value)" />
                      </mat-form-field>
                    </div>
                    <p class="micro-hint">
                      Accepts any CSS color name (<code>cornflowerblue</code>) or
                      hex code (<code>#FF9933</code>). Typos render as black.
                    </p>
                  </section>

                  <!-- Number formatting -->
                  <section class="styling-section">
                    <h4>Number Formatting</h4>
                    <div class="row four-col">
                      <mat-form-field appearance="outline">
                        <mat-label>Rounding Mode</mat-label>
                        <mat-select formControlName="roundingMode">
                          <mat-option value="ceiling">Ceiling (1.01 → 2)</mat-option>
                          <mat-option value="floor">Floor (1.99 → 1)</mat-option>
                          <mat-option value="round">Round (Half-Up)</mat-option>
                        </mat-select>
                      </mat-form-field>
                      <mat-form-field appearance="outline">
                        <mat-label>Amount Decimals</mat-label>
                        <mat-select formControlName="amountDecimals">
                          <mat-option [value]="0">0</mat-option>
                          <mat-option [value]="1">1</mat-option>
                          <mat-option [value]="2">2</mat-option>
                        </mat-select>
                      </mat-form-field>
                      <mat-form-field appearance="outline">
                        <mat-label>Tax Decimals</mat-label>
                        <mat-select formControlName="taxDecimals">
                          <mat-option [value]="0">0</mat-option>
                          <mat-option [value]="1">1</mat-option>
                          <mat-option [value]="2">2</mat-option>
                        </mat-select>
                      </mat-form-field>
                      <mat-form-field appearance="outline">
                        <mat-label>Qty Decimals</mat-label>
                        <mat-select formControlName="qtyDecimals">
                          <mat-option [value]="0">0</mat-option>
                          <mat-option [value]="1">1</mat-option>
                          <mat-option [value]="2">2</mat-option>
                          <mat-option [value]="3">3</mat-option>
                        </mat-select>
                      </mat-form-field>
                    </div>
                    <div class="row two-col">
                      <mat-form-field appearance="outline">
                        <mat-label>Dimension Decimals (Dia/Length)</mat-label>
                        <mat-select formControlName="dimensionDecimals">
                          <mat-option [value]="0">0</mat-option>
                          <mat-option [value]="1">1</mat-option>
                        </mat-select>
                      </mat-form-field>
                      <mat-slide-toggle formControlName="taxShowPercent" color="primary"
                                        class="row-toggle">
                        Show <code>%</code> suffix on tax columns
                      </mat-slide-toggle>
                    </div>
                  </section>

                  <!-- Column alignment grid -->
                  <section class="styling-section">
                    <h4>Column Alignment</h4>
                    <p class="micro-hint">
                      Pick header and body alignment per column. Header
                      and body can differ — some teams prefer centered
                      headers above right-aligned numbers.
                    </p>
                    <div class="align-grid">
                      <div class="align-grid-head">
                        <span>Column</span>
                        <span>Header</span>
                        <span>Body</span>
                      </div>
                      <div class="align-grid-row" *ngFor="let col of columnOrder">
                        <span class="col-label">{{ columnLabels[col] }}</span>
                        <mat-radio-group [value]="columnAlignments[col].header"
                                         (change)="setAlignment(col, 'header', $event.value)"
                                         class="align-radios">
                          <mat-radio-button value="left" matTooltip="Left">
                            <mat-icon>format_align_left</mat-icon>
                          </mat-radio-button>
                          <mat-radio-button value="center" matTooltip="Center">
                            <mat-icon>format_align_center</mat-icon>
                          </mat-radio-button>
                          <mat-radio-button value="right" matTooltip="Right">
                            <mat-icon>format_align_right</mat-icon>
                          </mat-radio-button>
                        </mat-radio-group>
                        <mat-radio-group [value]="columnAlignments[col].body"
                                         (change)="setAlignment(col, 'body', $event.value)"
                                         class="align-radios">
                          <mat-radio-button value="left" matTooltip="Left">
                            <mat-icon>format_align_left</mat-icon>
                          </mat-radio-button>
                          <mat-radio-button value="center" matTooltip="Center">
                            <mat-icon>format_align_center</mat-icon>
                          </mat-radio-button>
                          <mat-radio-button value="right" matTooltip="Right">
                            <mat-icon>format_align_right</mat-icon>
                          </mat-radio-button>
                        </mat-radio-group>
                      </div>
                    </div>
                  </section>

                  <!-- Live preview -->
                  <section class="styling-section">
                    <h4>Live Preview</h4>
                    <div class="preview-box">
                      <table class="preview-table">
                        <thead>
                          <tr [style.background-color]="livePreviewStyle.headerBgColor"
                              [style.color]="livePreviewStyle.headerTextColor">
                            <th [style.text-align]="livePreviewStyle.columnAlignments.sno.header">#</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.grade.header">Grade</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.dia.header">Dia</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.length.header">Length</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.qty.header">Qty</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.basicRate.header">Basic</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.igst.header">IGST</th>
                            <th [style.text-align]="livePreviewStyle.columnAlignments.finalPrice.header">Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr *ngFor="let row of previewRows; let i = index">
                            <td [style.text-align]="livePreviewStyle.columnAlignments.sno.body">{{ i + 1 }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.grade.body">{{ row.grade }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.dia.body">{{ formatDim(row.dia) }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.length.body">{{ formatDim(row.length) }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.qty.body">{{ formatQ(row.qty) }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.basicRate.body">{{ formatA(row.basic) }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.igst.body">{{ formatT(row.igst) }}</td>
                            <td [style.text-align]="livePreviewStyle.columnAlignments.finalPrice.body">{{ formatA(row.total) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </section>

                </div>
              </mat-tab>

            </mat-tab-group>
          </div>

        </form>
      }
    </mat-dialog-content>

    <mat-dialog-actions class="dialog-footer">
      <span class="copy-feedback" *ngIf="copiedToken">Copied {{ copiedToken }}</span>
      <span class="spacer"></span>
      <button mat-stroked-button (click)="dialogRef.close()">Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid || saving || loadingDetail">
        <mat-icon>{{ saving ? 'hourglass_empty' : 'save' }}</mat-icon>
        {{ saving ? 'Saving...' : 'Save Format' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 10px 24px;
      border-bottom: 1px solid var(--snm-border-divider);
      background: var(--snm-bg-panel);
      color: var(--snm-text-primary);
    }
    .header-left { display: flex; align-items: center; gap: 10px; }
    .header-left h2 {
      margin: 0; font-size: 18px; font-weight: 600;
      color: var(--snm-text-primary);
    }
    .header-icon { color: var(--snm-accent); }

    .fullscreen-content {
      max-height: none !important;
      height: calc(100vh - 120px);
      padding: 0 !important;
      overflow: hidden;
    }

    .loading-spinner {
      display: flex; justify-content: center; align-items: center;
      height: 100%; color: #888; font-size: 16px;
    }

    .editor-layout { display: flex; height: 100%; overflow: hidden; }

    /* Sidebar */
    .sidebar {
      width: 260px; min-width: 260px;
      border-right: 1px solid var(--snm-border-divider);
      padding: 16px 14px; overflow-y: auto;
      background: var(--snm-bg-panel);
      color: var(--snm-text-primary);
    }
    .sidebar-section { margin-bottom: 20px; }
    .sidebar-section h3 {
      font-size: 12px; font-weight: 700; text-transform: uppercase;
      color: var(--snm-text-secondary);
      letter-spacing: 0.5px; margin: 0 0 10px;
      display: flex; align-items: center; gap: 6px;
    }
    .section-icon { font-size: 18px; width: 18px; height: 18px; }
    .hint {
      font-size: 11px; color: var(--snm-text-muted); margin: 0 0 10px;
    }
    .full-width { width: 100%; }
    .placeholder-group { margin-bottom: 10px; }
    .group-label {
      font-size: 10px; font-weight: 600;
      color: var(--snm-text-muted);
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
    }
    .placeholder-chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .placeholder-chip {
      display: inline-block; padding: 2px 7px; font-size: 10px;
      font-family: 'Consolas', 'Courier New', monospace;
      background: var(--snm-accent-subtle, rgba(74, 144, 226, 0.10));
      border: 1px solid var(--snm-border-field);
      border-radius: 3px;
      cursor: pointer; transition: all 0.15s;
      color: var(--snm-accent-dark, var(--snm-accent));
    }
    .placeholder-chip:hover {
      background: var(--snm-accent);
      color: var(--snm-text-on-primary, #fff);
      border-color: var(--snm-accent);
    }

    /* Editor area */
    .editor-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .editor-tabs { flex: 1; }

    .editor-pane {
      padding: 10px 16px;
      overflow-y: auto;
      height: calc(100vh - 220px);
    }
    .editor-hint {
      font-size: 12px; color: var(--snm-text-muted);
      margin-bottom: 8px; line-height: 1.5;
    }
    .editor-hint code {
      background: var(--snm-accent-subtle, rgba(74, 144, 226, 0.10));
      padding: 1px 5px; border-radius: 3px;
      font-size: 11px; color: var(--snm-accent-dark, var(--snm-accent));
    }

    /* Force mat-tab-body to fill height */
    :host ::ng-deep .mat-mdc-tab-body-wrapper { flex: 1; }
    :host ::ng-deep .mat-mdc-tab-body { height: 100%; }
    :host ::ng-deep .mat-mdc-tab-body-content { height: 100%; overflow: hidden; }

    /* Footer */
    .dialog-footer {
      border-top: 1px solid var(--snm-border-divider);
      padding: 8px 24px !important; margin: 0 !important;
      display: flex; align-items: center;
      background: var(--snm-bg-panel);
    }
    .spacer { flex: 1; }
    .copy-feedback {
      font-size: 12px; color: var(--snm-success, #4caf50); font-weight: 500;
    }

    /* Print-styling tab */
    .styling-pane { padding: 16px 20px; }
    .styling-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 12px; margin-bottom: 16px;
    }
    .styling-header .editor-hint { flex: 1; margin: 0; }
    .styling-section {
      margin-bottom: 20px;
      padding: 12px 14px;
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      background: var(--snm-bg-card);
      color: var(--snm-text-primary);
    }
    .styling-section h4 {
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 700;
      color: var(--snm-text-primary);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .row { display: grid; gap: 12px; }
    .row.two-col   { grid-template-columns: 1fr 1fr; align-items: center; }
    .row.four-col  { grid-template-columns: repeat(4, 1fr); }
    .row mat-form-field { width: 100%; }
    .row-toggle { padding-left: 4px; }
    .micro-hint {
      margin: 4px 0 0;
      font-size: 11px;
      color: var(--snm-text-muted);
      line-height: 1.5;
    }
    .micro-hint code {
      background: var(--snm-accent-subtle, rgba(74, 144, 226, 0.10));
      padding: 1px 4px; border-radius: 3px;
      font-size: 11px; color: var(--snm-accent-dark, var(--snm-accent));
    }
    .color-swatch {
      width: 28px; height: 28px; padding: 0;
      border: 1px solid var(--snm-border-field);
      border-radius: 4px; cursor: pointer; background: transparent;
    }
    /* Column alignment grid */
    .align-grid {
      display: flex; flex-direction: column;
      border: 1px solid var(--snm-border-divider);
      border-radius: 4px;
      background: var(--snm-bg-panel);
      overflow: hidden;
    }
    .align-grid-head, .align-grid-row {
      display: grid;
      grid-template-columns: 1.5fr 1fr 1fr;
      align-items: center;
      padding: 6px 10px;
    }
    .align-grid-head {
      background: var(--snm-bg-header-row, var(--snm-bg-panel));
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      color: var(--snm-text-secondary);
      letter-spacing: 0.4px;
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .align-grid-row { border-top: 1px solid var(--snm-border-divider); }
    /* Zebra striping via translucent overlay — works on both themes. */
    .align-grid-row:nth-child(odd) {
      background: var(--snm-bg-card);
    }
    .col-label { font-size: 12px; color: var(--snm-text-primary); }
    .align-radios { display: flex; gap: 0; }
    .align-radios mat-radio-button { margin-right: 0; }
    .align-radios mat-icon {
      font-size: 16px; width: 16px; height: 16px;
      vertical-align: middle;
      color: var(--snm-text-secondary);
    }
    /* Live preview — WYSIWYG of the printed output, which is always
       on white paper. Lock background AND text colors to fixed values
       so they don't flip with the app theme. Header colors stay driven
       by the user's chosen headerBgColor / headerTextColor (set via
       inline [style] bindings in the template). */
    .preview-box {
      padding: 12px;
      background: #fff;
      border: 1px solid #d0d0d0;
      border-radius: 4px;
      overflow-x: auto;
      color: #1a1a1a;
    }
    .preview-table {
      width: 100%; border-collapse: collapse; font-size: 11px;
      color: #1a1a1a;
    }
    .preview-table tbody td {
      color: #1a1a1a;
    }
    .preview-table th, .preview-table td {
      padding: 5px 8px; border-bottom: 1px solid #ececec;
    }
    .preview-table tbody tr:nth-child(even) { background: #f9f9f9; }
  `],
})
export class QuotationFormatDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  loadingDetail = false;
  copiedToken = '';

  placeholderGroups: { name: string; items: typeof PLACEHOLDERS }[] = [];
  editorHeight = Math.max(350, window.innerHeight - 320);

  private editId: number | null = null;

  // ===== Print-styling state =====
  /** Per-column alignment held outside the FormGroup — 26 radio
   *  groups would be tedious in a deep FormGroup. Bound directly
   *  via [value]/(change) on the radio buttons; serialized to JSON
   *  on save. */
  columnAlignments: Record<ColumnId, ColumnAlignment> = structuredClone(
    DEFAULT_PRINT_STYLE.columnAlignments,
  );
  readonly columnLabels = COLUMN_LABELS;
  readonly columnOrder = COLUMN_ORDER;

  /** Three sample rows for the live preview — chosen so the user can
   *  see how decimals, alignment, and rounding interact. */
  readonly previewRows = [
    { grade: 'Fe550D', dia: 12,   length: 12,   qty: 5.5,  basic: 53450.78, igst: 18.0, total: 268765.50 },
    { grade: 'Fe550D', dia: 16,   length: 12,   qty: 12.0, basic: 52950.34, igst: 18.0, total: 624925.12 },
    { grade: 'Fe550',  dia: 25,   length: 12,   qty: 8.25, basic: 52250.00, igst: 18.0, total: 405531.25 },
  ];

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    public dialogRef: MatDialogRef<QuotationFormatDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { qfId: number } | null,
  ) {}

  ngOnInit() {
    const groups = new Map<string, typeof PLACEHOLDERS>();
    for (const p of PLACEHOLDERS) {
      if (!groups.has(p.group)) groups.set(p.group, []);
      groups.get(p.group)!.push(p);
    }
    this.placeholderGroups = Array.from(groups, ([name, items]) => ({ name, items }));

    this.form = this.fb.group({
      formatName: ['', Validators.required],
      qHeader: [''],
      qContent: [''],
      qFooter: [''],
      isCurrent: [false],
      // Print styling defaults — preloaded so a brand-new format
      // already has a sensible look.
      headerBgColor: [DEFAULT_PRINT_STYLE.headerBgColor],
      headerTextColor: [DEFAULT_PRINT_STYLE.headerTextColor],
      roundingMode: [DEFAULT_PRINT_STYLE.roundingMode],
      amountDecimals: [DEFAULT_PRINT_STYLE.amountDecimals],
      taxDecimals: [DEFAULT_PRINT_STYLE.taxDecimals],
      taxShowPercent: [DEFAULT_PRINT_STYLE.taxShowPercent],
      qtyDecimals: [DEFAULT_PRINT_STYLE.qtyDecimals],
      dimensionDecimals: [DEFAULT_PRINT_STYLE.dimensionDecimals],
    });

    if (this.data?.qfId) {
      this.isEdit = true;
      this.editId = this.data.qfId;
      this.loadingDetail = true;
      this.api.get<any>(`/quotation-formats/${this.editId}`).subscribe({
        next: (fmt) => {
          // Resolve missing/null styling fields against defaults so the
          // form always has a value to bind.
          const resolved = resolvePrintStyle(fmt);
          this.form.patchValue({
            formatName: fmt.formatName,
            qHeader: fmt.qHeader || '',
            qContent: fmt.qContent || '',
            qFooter: fmt.qFooter || '',
            isCurrent: fmt.isCurrent,
            headerBgColor: resolved.headerBgColor,
            headerTextColor: resolved.headerTextColor,
            roundingMode: resolved.roundingMode,
            amountDecimals: resolved.amountDecimals,
            taxDecimals: resolved.taxDecimals,
            taxShowPercent: resolved.taxShowPercent,
            qtyDecimals: resolved.qtyDecimals,
            dimensionDecimals: resolved.dimensionDecimals,
          });
          this.columnAlignments = resolved.columnAlignments;
          this.loadingDetail = false;
        },
        error: () => {
          this.notify.error('Failed to load format details');
          this.dialogRef.close();
        },
      });
    }
  }

  // ===== Print-styling helpers (template-bound) =====

  setAlignment(col: ColumnId, place: 'header' | 'body', value: Alignment): void {
    this.columnAlignments = {
      ...this.columnAlignments,
      [col]: { ...this.columnAlignments[col], [place]: value },
    };
  }

  resetStylingDefaults(): void {
    this.form.patchValue({
      headerBgColor: DEFAULT_PRINT_STYLE.headerBgColor,
      headerTextColor: DEFAULT_PRINT_STYLE.headerTextColor,
      roundingMode: DEFAULT_PRINT_STYLE.roundingMode,
      amountDecimals: DEFAULT_PRINT_STYLE.amountDecimals,
      taxDecimals: DEFAULT_PRINT_STYLE.taxDecimals,
      taxShowPercent: DEFAULT_PRINT_STYLE.taxShowPercent,
      qtyDecimals: DEFAULT_PRINT_STYLE.qtyDecimals,
      dimensionDecimals: DEFAULT_PRINT_STYLE.dimensionDecimals,
    });
    this.columnAlignments = structuredClone(DEFAULT_PRINT_STYLE.columnAlignments);
  }

  /** Live preview re-resolves on every CD pass — cheap, since the inputs
   *  are tiny and the helper is pure. */
  get livePreviewStyle(): PrintStyle {
    const v = this.form?.value || {};
    return resolvePrintStyle({
      headerBgColor: v.headerBgColor,
      headerTextColor: v.headerTextColor,
      roundingMode: v.roundingMode,
      amountDecimals: v.amountDecimals,
      taxDecimals: v.taxDecimals,
      taxShowPercent: v.taxShowPercent,
      qtyDecimals: v.qtyDecimals,
      dimensionDecimals: v.dimensionDecimals,
      columnAlignments: this.columnAlignments,
    });
  }

  formatA(value: number): string {
    const s = this.livePreviewStyle;
    return formatPrintNumber(value, s.amountDecimals, s.roundingMode);
  }
  formatT(value: number): string {
    const s = this.livePreviewStyle;
    return formatTaxPercent(value, s.taxDecimals, s.roundingMode, s.taxShowPercent);
  }
  formatQ(value: number): string {
    const s = this.livePreviewStyle;
    return formatPrintNumber(value, s.qtyDecimals, s.roundingMode);
  }
  formatDim(value: number): string {
    const s = this.livePreviewStyle;
    return formatPrintNumber(value, s.dimensionDecimals, s.roundingMode);
  }

  /** The native ``<input type="color">`` only accepts #rrggbb. When the
   *  user types a CSS color name (`saffron`, `cornflowerblue`), reflect
   *  it back to the swatch by resolving via a hidden div's computedStyle.
   *  Falls back to the input string when resolution fails. */
  resolveHexForSwatch(value: string): string {
    if (!value) return '#000000';
    if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(value)) return value.length === 4
      ? '#' + [...value.slice(1)].map(c => c + c).join('')
      : value;
    try {
      const probe = document.createElement('div');
      probe.style.color = value;
      document.body.appendChild(probe);
      const computed = getComputedStyle(probe).color;
      document.body.removeChild(probe);
      const m = computed.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);
      if (!m) return '#000000';
      const hex = (n: string) => parseInt(n, 10).toString(16).padStart(2, '0');
      return `#${hex(m[1])}${hex(m[2])}${hex(m[3])}`;
    } catch {
      return '#000000';
    }
  }

  copyPlaceholder(token: string) {
    navigator.clipboard.writeText(token).then(() => {
      this.copiedToken = token;
      setTimeout(() => { this.copiedToken = ''; }, 2000);
    });
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    // Serialize columnAlignments alongside the form fields. Stored as a
    // JSON string on the server; resolvePrintStyle parses it back on
    // load. Sending the full map (not a delta) keeps server-side merge
    // logic simple.
    const payload = {
      ...this.form.value,
      columnAlignments: JSON.stringify(this.columnAlignments),
    };

    const call = this.isEdit
      ? this.api.put(`/quotation-formats/${this.editId}`, payload)
      : this.api.post('/quotation-formats', payload);

    call.subscribe({
      next: () => {
        this.notify.success(`Format ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
