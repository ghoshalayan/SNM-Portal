import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface TncItem {
  quotTncId?: number;
  quotId: number;
  masterTncId?: number;
  sortOrder: number;
  tncName?: string;
  tncDescription: string;
  // local-only UI state
  selected?: boolean;
  editDescription?: string;
  expanded?: boolean;
}

@Component({
  selector: 'app-quotation-tnc',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    DragDropModule,
  ],
  template: `
    <div class="tnc-container">
      <!-- Header -->
      <div class="section-header">
        <div class="header-left">
          <mat-icon class="header-icon">gavel</mat-icon>
          <h3>Terms &amp; Conditions</h3>
          <span class="item-badge" *ngIf="tncList.length > 0">
            {{ selectedCount }}/{{ tncList.length }}
          </span>
        </div>
        <div class="header-actions" *ngIf="!readOnly && tncList.length > 0">
          <button mat-stroked-button class="collapse-all-btn" (click)="toggleAll()">
            <mat-icon>{{ allExpanded ? 'unfold_less' : 'unfold_more' }}</mat-icon>
            {{ allExpanded ? 'Collapse All' : 'Expand All' }}
          </button>
          <button mat-raised-button color="primary" (click)="saveAll()" [disabled]="saving || !hasDirty()">
            <mat-spinner *ngIf="saving" diameter="16" style="display:inline-block;margin-right:6px;"></mat-spinner>
            <mat-icon *ngIf="!saving">save</mat-icon>
            Save Changes
          </button>
        </div>
      </div>

      <!-- Loading -->
      <div *ngIf="loading" class="spinner-container">
        <mat-spinner diameter="36"></mat-spinner>
        <span>Loading terms...</span>
      </div>

      <!-- Import Panel (always visible when not readOnly) -->
      <div *ngIf="!loading && !readOnly" class="import-panel">
        <div class="import-row">
          <mat-form-field appearance="outline" class="import-search">
            <mat-label>Import from old quotation</mat-label>
            <input matInput [(ngModel)]="quotSearchTerm"
              placeholder="Search by Quotation No or Customer Name..."
              (input)="searchQuotations()" />
            <mat-icon matSuffix>search</mat-icon>
          </mat-form-field>
          <button mat-stroked-button (click)="loadFromMaster()" [disabled]="loadingMaster" class="master-btn">
            <mat-spinner *ngIf="loadingMaster" diameter="16" style="display:inline-block;margin-right:6px;"></mat-spinner>
            <mat-icon *ngIf="!loadingMaster">library_add</mat-icon>
            {{ loadingMaster ? 'Loading...' : 'Top-up from Master' }}
          </button>
        </div>
        <div *ngIf="quotSearchResults.length > 0" class="search-results">
          <div *ngFor="let r of quotSearchResults" class="search-result-item" (click)="importFromQuotation(r.quotId)">
            <strong>{{ r.quotNo }}</strong> — {{ r.customerName }}
            <span class="result-date">{{ r.quotDate | date:'dd-MM-yyyy' }}</span>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div *ngIf="!loading && tncList.length === 0" class="empty-state">
        <mat-icon>description</mat-icon>
        <h4>No Terms &amp; Conditions</h4>
        <p>Search an old quotation above to import its TnCs, or load from the master list.</p>
      </div>

      <!-- T&C List -->
      <div *ngIf="!loading && tncList.length > 0"
        cdkDropList
        [cdkDropListDisabled]="readOnly"
        (cdkDropListDropped)="onDrop($event)"
        class="tnc-list">

        <div
          *ngFor="let item of tncList; let i = index"
          cdkDrag
          class="tnc-row"
          [class.checked]="item.selected"
          [class.unchecked]="!item.selected"
          [class.expanded]="item.expanded"
          [class.read-only]="readOnly">

          <!-- Drag handle -->
          <mat-icon cdkDragHandle class="drag-handle" *ngIf="!readOnly" matTooltip="Drag to reorder">
            drag_indicator
          </mat-icon>

          <!-- Checkbox -->
          <mat-checkbox
            *ngIf="!readOnly"
            [(ngModel)]="item.selected"
            color="primary"
            class="tnc-checkbox">
          </mat-checkbox>

          <!-- Row number -->
          <span class="tnc-number">{{ i + 1 }}.</span>

          <!-- Collapsible content -->
          <div class="tnc-body" (click)="item.expanded = !item.expanded">
            <!-- Collapsed: only tncName -->
            <div class="tnc-header-row">
              <mat-icon class="expand-icon">
                {{ item.expanded ? 'expand_less' : 'expand_more' }}
              </mat-icon>
              <strong class="tnc-name">{{ item.tncName || 'Untitled' }}</strong>
              <span *ngIf="!item.expanded" class="tnc-preview">
                — {{ (item.editDescription || item.tncDescription || '') | slice:0:80 }}{{ (item.editDescription || item.tncDescription || '').length > 80 ? '...' : '' }}
              </span>
            </div>

            <!-- Expanded: description + edit -->
            <div *ngIf="item.expanded" class="tnc-expanded" (click)="$event.stopPropagation()">
              <p class="tnc-desc-full">{{ item.tncDescription }}</p>

              <!-- Editable textarea (only when checked and not readOnly) -->
              <div *ngIf="item.selected && !readOnly" class="tnc-edit">
                <mat-form-field appearance="outline" class="edit-field">
                  <mat-label>Edit description</mat-label>
                  <textarea matInput
                    [(ngModel)]="item.editDescription"
                    rows="3"
                    placeholder="Modify the term description..."></textarea>
                </mat-form-field>
              </div>
            </div>
          </div>

          <!-- Refresh from master -->
          <button mat-icon-button
            *ngIf="!readOnly && item.masterTncId"
            class="refresh-btn"
            (click)="$event.stopPropagation(); refreshFromMaster(item)"
            [disabled]="item.quotTncId === refreshingId"
            matTooltip="Reset to master value">
            <mat-spinner *ngIf="item.quotTncId === refreshingId" diameter="18"></mat-spinner>
            <mat-icon *ngIf="item.quotTncId !== refreshingId">refresh</mat-icon>
          </button>
        </div>
      </div>

      <!-- Footer hint -->
      <div *ngIf="!loading && tncList.length > 0 && !readOnly" class="footer-hint">
        <mat-icon class="hint-icon">info_outline</mat-icon>
        Click row to expand/collapse. Check to include &amp; edit, uncheck to exclude. Drag to reorder.
      </div>
    </div>
  `,
  styles: [`
    .tnc-container { padding: 16px 0; }

    .section-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
    }
    .header-left { display: flex; align-items: center; gap: 8px; }
    .header-icon { color: var(--snm-accent, #1976d2); font-size: 22px; }
    .section-header h3 {
      margin: 0; font-size: 16px; font-weight: 600;
      color: var(--snm-text-primary, #212121);
    }
    .item-badge {
      background: var(--snm-accent, #1976d2); color: #fff;
      font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 12px;
    }
    .header-actions { display: flex; gap: 8px; align-items: center; }
    .collapse-all-btn {
      font-size: 12px; height: 34px; line-height: 34px; padding: 0 12px;
      mat-icon { font-size: 18px; width: 18px; height: 18px; margin-right: 4px; }
    }

    .spinner-container {
      display: flex; align-items: center; gap: 12px;
      justify-content: center; padding: 32px;
      color: var(--snm-text-secondary, #616161);
    }

    .import-panel { margin-bottom: 16px; }
    .import-row { display: flex; gap: 12px; align-items: flex-start; }
    .import-search { flex: 1; }
    .master-btn { height: 56px; white-space: nowrap; }
    .search-results {
      max-height: 200px; overflow-y: auto;
      border: 1px solid rgba(0,0,0,0.12); border-radius: 4px;
      margin-top: -8px; margin-bottom: 8px;
    }
    .search-result-item {
      padding: 8px 12px; cursor: pointer; font-size: 13px;
      border-bottom: 1px solid rgba(0,0,0,0.06);
    }
    .search-result-item:hover { background: rgba(0,0,0,0.04); }
    .result-date { float: right; color: rgba(0,0,0,0.45); font-size: 12px; }

    .empty-state {
      text-align: center; padding: 48px 24px;
      color: var(--snm-text-muted, #9e9e9e);
      mat-icon {
        font-size: 52px; width: 52px; height: 52px;
        opacity: 0.4; display: block; margin: 0 auto 12px;
      }
      h4 {
        margin: 0 0 6px; font-size: 16px;
        color: var(--snm-text-secondary, #616161);
      }
      p { margin: 0 0 20px; font-size: 13px; }
    }
    .load-master-btn {
      mat-icon { margin-right: 6px; }
    }

    .tnc-list { display: flex; flex-direction: column; gap: 4px; }

    .tnc-row {
      display: flex; align-items: flex-start; gap: 8px;
      padding: 8px 14px; border-radius: 6px;
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      background: var(--snm-bg-card, #fff);
      transition: background 0.15s, border-color 0.15s, opacity 0.15s;
    }
    .tnc-row.checked {
      border-color: var(--snm-accent, #1976d2);
      background: rgba(25,118,210,.03);
    }
    .tnc-row.unchecked { opacity: 0.5; }
    .tnc-row.read-only { padding-left: 14px; }
    .tnc-row:not(.read-only):hover { box-shadow: 0 1px 6px rgba(0,0,0,0.08); }
    .tnc-row.cdk-drag-preview { box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
    .tnc-row.cdk-drag-placeholder { opacity: 0.3; }

    .drag-handle {
      cursor: grab; color: var(--snm-text-muted, #bbb);
      margin-top: 4px; flex-shrink: 0; font-size: 20px;
    }
    .drag-handle:active { cursor: grabbing; }

    .tnc-checkbox { flex-shrink: 0; margin-top: 3px; }

    .tnc-number {
      font-weight: 600; color: var(--snm-text-secondary, #555);
      flex-shrink: 0; margin-top: 5px; min-width: 22px; font-size: 12px;
    }

    .tnc-body { flex: 1; min-width: 0; cursor: pointer; }

    .tnc-header-row {
      display: flex; align-items: center; gap: 4px;
      min-height: 28px; line-height: 28px;
    }
    .expand-icon {
      font-size: 20px; width: 20px; height: 20px;
      color: var(--snm-text-muted, #9e9e9e); flex-shrink: 0;
    }
    .tnc-name {
      font-size: 13px; font-weight: 600;
      color: var(--snm-text-primary, #212121); white-space: nowrap;
    }
    .tnc-preview {
      font-size: 12px; color: var(--snm-text-muted, #9e9e9e);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-left: 4px;
    }

    .tnc-expanded { padding: 8px 0 4px 24px; }
    .tnc-desc-full {
      font-size: 13px; line-height: 1.6; margin: 0 0 8px;
      color: var(--snm-text-secondary, #555);
    }

    .tnc-edit { margin-top: 4px; }
    .edit-field {
      width: 100%;
      ::ng-deep .mat-mdc-form-field-infix { padding: 6px 0 !important; min-height: 36px !important; }
      ::ng-deep .mat-mdc-text-field-wrapper { padding: 0 10px !important; }
      ::ng-deep .mdc-notched-outline__leading,
      ::ng-deep .mdc-notched-outline__trailing,
      ::ng-deep .mdc-notched-outline__notch { border-color: var(--snm-accent, #1976d2) !important; }
      ::ng-deep textarea { font-size: 12px; line-height: 1.5; }
    }

    .refresh-btn {
      flex-shrink: 0; width: 30px; height: 30px; line-height: 30px; margin-top: 2px;
      color: var(--snm-text-muted, #9e9e9e);
      mat-icon { font-size: 18px; width: 18px; height: 18px; }
    }
    .refresh-btn:hover { color: var(--snm-accent, #1976d2); }

    .footer-hint {
      display: flex; align-items: center; gap: 4px;
      margin-top: 12px; font-size: 11px;
      color: var(--snm-text-muted, #9e9e9e);
    }
    .hint-icon { font-size: 14px; width: 14px; height: 14px; }
  `],
})
export class QuotationTncComponent implements OnInit, OnChanges {
  @Input() quotId!: number;
  @Input() readOnly = false;

  tncList: TncItem[] = [];
  loading = false;
  saving = false;
  loadingMaster = false;
  refreshingId: number | null = null;
  quotSearchTerm = '';
  quotSearchResults: { quotId: number; quotNo: string; customerName: string; quotDate: string }[] = [];
  private searchTimer: any;

  private originalMap = new Map<number, { selected: boolean; description: string }>();

  constructor(
    private apiService: ApiService,
    private notificationService: NotificationService,
  ) {}

  ngOnInit(): void {
    if (this.quotId) {
      this.fetchTerms();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && !changes['quotId'].firstChange && this.quotId) {
      this.fetchTerms();
    }
  }

  /** Fetch saved T&Cs from QuotTermsNConditions */
  fetchTerms(): void {
    this.loading = true;
    this.apiService.get<TncItem[]>(`/quotations/${this.quotId}/terms`).subscribe({
      next: (data) => {
        // All T&Cs unchecked by default — the user explicitly picks the ones
        // that apply to this quotation. Avoids accidental inclusion of
        // boilerplate clauses the customer never agreed to.
        this.tncList = data
          .sort((a, b) => a.sortOrder - b.sortOrder)
          .map(item => ({
            ...item,
            selected: false,
            editDescription: item.tncDescription,
            expanded: false,
          }));
        this.snapshotOriginal();
        this.loading = false;
      },
      error: () => {
        this.notificationService.error('Failed to load terms & conditions.');
        this.loading = false;
      },
    });
  }

  /** First-time load: copy from TermsNConditionMaster then fetch */
  loadFromMaster(): void {
    this.loadingMaster = true;
    this.apiService.post(`/quotations/${this.quotId}/terms/from-master`, {}).subscribe({
      next: (res: any) => {
        this.loadingMaster = false;
        this.notificationService.success(res?.message || 'Terms loaded from master.');
        this.fetchTerms();
      },
      error: () => {
        this.loadingMaster = false;
        this.notificationService.error('Failed to load terms from master.');
      },
    });
  }

  searchQuotations(): void {
    clearTimeout(this.searchTimer);
    const term = this.quotSearchTerm?.trim();
    if (!term || term.length < 2) {
      this.quotSearchResults = [];
      return;
    }
    this.searchTimer = setTimeout(() => {
      this.apiService.get<any[]>('/quotations/search-for-tnc', { q: term }).subscribe({
        next: (results) => (this.quotSearchResults = results),
        error: () => (this.quotSearchResults = []),
      });
    }, 400);
  }

  importFromQuotation(sourceQuotId: number): void {
    this.quotSearchResults = [];
    this.quotSearchTerm = '';
    this.loading = true;
    this.apiService.post(`/quotations/${this.quotId}/terms/from-quotation/${sourceQuotId}`, {}).subscribe({
      next: (res: any) => {
        this.notificationService.success(res?.message || 'TnCs imported');
        this.fetchTerms();
      },
      error: () => {
        this.notificationService.error('Failed to import TnCs');
        this.loading = false;
      },
    });
  }

  get selectedCount(): number {
    return this.tncList.filter(t => t.selected).length;
  }

  get allExpanded(): boolean {
    return this.tncList.length > 0 && this.tncList.every(t => t.expanded);
  }

  toggleAll(): void {
    const expand = !this.allExpanded;
    this.tncList.forEach(t => t.expanded = expand);
  }

  hasDirty(): boolean {
    for (const item of this.tncList) {
      const orig = this.originalMap.get(item.quotTncId!);
      if (!orig) return true;
      if (item.selected !== orig.selected) return true;
      if (item.selected && item.editDescription !== orig.description) return true;
    }
    const currentOrder = this.tncList.map(t => t.quotTncId).join(',');
    const origOrder = [...this.originalMap.keys()].join(',');
    return currentOrder !== origOrder;
  }

  snapshotOriginal(): void {
    this.originalMap.clear();
    for (const item of this.tncList) {
      if (item.quotTncId) {
        this.originalMap.set(item.quotTncId, {
          selected: item.selected ?? true,
          description: item.editDescription ?? item.tncDescription,
        });
      }
    }
  }

  onDrop(event: CdkDragDrop<TncItem[]>): void {
    moveItemInArray(this.tncList, event.previousIndex, event.currentIndex);
    this.tncList.forEach((item, index) => {
      item.sortOrder = index + 1;
    });
  }

  refreshFromMaster(item: TncItem): void {
    if (!item.masterTncId) return;
    this.refreshingId = item.quotTncId ?? null;
    this.apiService.get<{ tncId: number; tncName: string; tncDescription: string }>(
      `/quotations/tnc-master/${item.masterTncId}`
    ).subscribe({
      next: (master) => {
        item.tncName = master.tncName;
        item.tncDescription = master.tncDescription;
        item.editDescription = master.tncDescription;
        this.refreshingId = null;
        this.notificationService.success(`"${master.tncName}" reset to master value.`);
      },
      error: () => {
        this.refreshingId = null;
        this.notificationService.error('Master term not found or failed to fetch.');
      },
    });
  }

  saveAll(): void {
    this.saving = true;
    const ops: Array<() => Promise<void>> = [];

    for (const item of this.tncList) {
      if (!item.quotTncId) continue;

      if (!item.selected) {
        ops.push(() =>
          this.apiService.delete(`/quotations/${this.quotId}/terms/${item.quotTncId}`)
            .toPromise().then(() => {})
        );
      } else {
        const orig = this.originalMap.get(item.quotTncId);
        if (orig && item.editDescription !== orig.description) {
          ops.push(() =>
            this.apiService.put(`/quotations/${this.quotId}/terms/${item.quotTncId}`, {
              tncName: item.tncName,
              tncDescription: item.editDescription,
            }).toPromise().then(() => {})
          );
        }
      }
    }

    const reorderPayload = this.tncList
      .filter(t => t.selected && t.quotTncId)
      .map((t, idx) => ({ quotTncId: t.quotTncId, sortOrder: idx + 1 }));

    if (reorderPayload.length > 0) {
      ops.push(() =>
        this.apiService.put(`/quotations/${this.quotId}/terms/reorder`, reorderPayload)
          .toPromise().then(() => {})
      );
    }

    Promise.all(ops.map(fn => fn()))
      .then(() => {
        this.notificationService.success('Terms & conditions saved.');
        this.fetchTerms();
      })
      .catch(() => {
        this.notificationService.error('Failed to save some changes.');
      })
      .finally(() => {
        this.saving = false;
      });
  }
}
