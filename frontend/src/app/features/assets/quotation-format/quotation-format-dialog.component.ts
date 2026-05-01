import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { QuillRichEditorComponent } from '../../../shared/components/quill-editor/quill-rich-editor.component';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

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
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSlideToggleModule,
    MatTabsModule,
    MatIconModule,
    MatTooltipModule,
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
      padding: 10px 24px; border-bottom: 1px solid #e0e0e0; background: #fafafa;
    }
    .header-left { display: flex; align-items: center; gap: 10px; }
    .header-left h2 { margin: 0; font-size: 18px; font-weight: 600; }
    .header-icon { color: #1565c0; }

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
      border-right: 1px solid #e0e0e0;
      padding: 16px 14px; overflow-y: auto; background: #fafbfc;
    }
    .sidebar-section { margin-bottom: 20px; }
    .sidebar-section h3 {
      font-size: 12px; font-weight: 700; text-transform: uppercase;
      color: #555; letter-spacing: 0.5px; margin: 0 0 10px;
      display: flex; align-items: center; gap: 6px;
    }
    .section-icon { font-size: 18px; width: 18px; height: 18px; }
    .hint { font-size: 11px; color: #888; margin: 0 0 10px; }
    .full-width { width: 100%; }
    .placeholder-group { margin-bottom: 10px; }
    .group-label {
      font-size: 10px; font-weight: 600; color: #777;
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
    }
    .placeholder-chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .placeholder-chip {
      display: inline-block; padding: 2px 7px; font-size: 10px;
      font-family: 'Consolas', 'Courier New', monospace;
      background: #e8eef4; border: 1px solid #d0d9e3; border-radius: 3px;
      cursor: pointer; transition: all 0.15s; color: #1565c0;
    }
    .placeholder-chip:hover { background: #1565c0; color: #fff; border-color: #1565c0; }

    /* Editor area */
    .editor-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .editor-tabs { flex: 1; }

    .editor-pane {
      padding: 10px 16px;
      overflow-y: auto;
      height: calc(100vh - 220px);
    }
    .editor-hint {
      font-size: 12px; color: #777; margin-bottom: 8px; line-height: 1.5;
    }
    .editor-hint code {
      background: #e8eef4; padding: 1px 5px; border-radius: 3px;
      font-size: 11px; color: #1565c0;
    }

    /* Force mat-tab-body to fill height */
    :host ::ng-deep .mat-mdc-tab-body-wrapper { flex: 1; }
    :host ::ng-deep .mat-mdc-tab-body { height: 100%; }
    :host ::ng-deep .mat-mdc-tab-body-content { height: 100%; overflow: hidden; }

    /* Footer */
    .dialog-footer {
      border-top: 1px solid #e0e0e0;
      padding: 8px 24px !important; margin: 0 !important;
      display: flex; align-items: center;
    }
    .spacer { flex: 1; }
    .copy-feedback {
      font-size: 12px; color: #4caf50; font-weight: 500;
    }
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
    });

    if (this.data?.qfId) {
      this.isEdit = true;
      this.editId = this.data.qfId;
      this.loadingDetail = true;
      this.api.get<any>(`/quotation-formats/${this.editId}`).subscribe({
        next: (fmt) => {
          this.form.patchValue({
            formatName: fmt.formatName,
            qHeader: fmt.qHeader || '',
            qContent: fmt.qContent || '',
            qFooter: fmt.qFooter || '',
            isCurrent: fmt.isCurrent,
          });
          this.loadingDetail = false;
        },
        error: () => {
          this.notify.error('Failed to load format details');
          this.dialogRef.close();
        },
      });
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
    const payload = this.form.value;

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
