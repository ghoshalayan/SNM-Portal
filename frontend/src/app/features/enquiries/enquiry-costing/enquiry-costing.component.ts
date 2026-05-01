import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatBadgeModule } from '@angular/material/badge';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface CostingVersion {
  id: number;
  versionNo: number;
  label: string;
  isLatest: boolean;
  createdAt: string;
}

export interface CostingRow {
  detailId: number;
  itemGradeName: string;
  itemDia: number;
  itemLength: number;
  itemUnit: string;

  // Transfer price
  TPWGST: number | null;
  Marketing: number | null;

  // Cost heads
  FreightTrailer: number | null;
  FreightTruck: number | null;
  Unloading: number | null;
  OHD: number | null;
  IFC: number | null;
  WeighmentDiff: number | null;
  CD: number | null;
  SWECharge: number | null;
  CRS: number | null;
  IncCharge: number | null;
  ShortLnthCharge: number | null;
  SpeciFicLnthCharge: number | null;
  ExtraCharge: number | null;
  Fluctuation: number | null;
  Commission: number | null;
  Misc: number | null;
  Testing: number | null;
  MOUTOD: number | null;
  SplDisc: number | null;
  JC: number | null;

  // Output fields
  basicRate: number | null;
  GST: number | null;
  EXFORPrice: number | null;

  isAutoFilling?: boolean;
}

@Component({
  selector: 'app-enquiry-costing',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatChipsModule,
    MatDividerModule,
    MatBadgeModule,
  ],
  template: `
    <div class="enquiry-costing-container">

      <!-- Toolbar -->
      <div class="costing-toolbar">
        <h3 class="section-title">
          <mat-icon>calculate</mat-icon>
          Costing
        </h3>

        <div class="toolbar-right">
          <!-- Version Selector -->
          <mat-form-field appearance="outline" class="version-select" *ngIf="versions.length">
            <mat-label>Version</mat-label>
            <mat-select [(ngModel)]="selectedVersionId" (ngModelChange)="onVersionChange($event)">
              <mat-option *ngFor="let v of versions" [value]="v.id">
                {{ v.label }}
                <span *ngIf="v.isLatest" class="latest-badge"> (Current)</span>
              </mat-option>
            </mat-select>
          </mat-form-field>

          <!-- New Version Button -->
          <button mat-raised-button color="primary"
            (click)="createNewVersion()"
            [disabled]="isCreatingVersion || isLoading"
            matTooltip="Create a new costing version from current data">
            <mat-spinner *ngIf="isCreatingVersion" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!isCreatingVersion">add_circle_outline</mat-icon>
            {{ isCreatingVersion ? 'Creating...' : 'New Version' }}
          </button>

          <!-- Save Button -->
          <button mat-raised-button color="accent"
            *ngIf="isCurrentVersion"
            (click)="saveCosting()"
            [disabled]="isSaving || isLoading">
            <mat-spinner *ngIf="isSaving" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!isSaving">save</mat-icon>
            {{ isSaving ? 'Saving...' : 'Save Costing' }}
          </button>
        </div>
      </div>

      <!-- Read-only warning for old versions -->
      <div class="readonly-banner" *ngIf="!isCurrentVersion && selectedVersionId">
        <mat-icon>lock</mat-icon>
        <span>You are viewing a previous version. Switch to the current version to edit.</span>
      </div>

      <!-- Loading -->
      <div class="loading-row" *ngIf="isLoading">
        <mat-spinner diameter="36"></mat-spinner>
        <span>Loading costing data...</span>
      </div>

      <!-- No versions yet -->
      <div class="no-data" *ngIf="!isLoading && !versions.length">
        <mat-icon>receipt_long</mat-icon>
        <p>No costing data yet. Click <strong>New Version</strong> to start costing.</p>
      </div>

      <!-- Costing Table -->
      <div class="table-wrapper" *ngIf="!isLoading && dataSource.data.length">
        <div class="table-scroll">
          <table mat-table [dataSource]="dataSource" class="costing-table">

            <!-- Item Description Column -->
            <ng-container matColumnDef="itemDesc" sticky>
              <th mat-header-cell *matHeaderCellDef class="sticky-col">Item</th>
              <td mat-cell *matCellDef="let row" class="sticky-col item-desc-cell">
                <div class="item-desc">
                  <strong>{{ row.itemGradeName }}</strong>
                  <span class="item-dim">Ø{{ row.itemDia }} × {{ row.itemLength }} {{ row.itemUnit }}</span>
                </div>
              </td>
            </ng-container>

            <!-- TP With GST -->
            <ng-container matColumnDef="TPWGST">
              <th mat-header-cell *matHeaderCellDef>TP w/ GST</th>
              <td mat-cell *matCellDef="let row">
                <div class="field-with-action">
                  <mat-form-field appearance="outline" class="cost-field" *ngIf="isCurrentVersion">
                    <input matInput type="number" [(ngModel)]="row.TPWGST"
                      [ngModelOptions]="{standalone: true}"
                      (blur)="onTPChange(row)"
                      placeholder="0.00" step="0.01" />
                  </mat-form-field>
                  <span *ngIf="!isCurrentVersion" class="readonly-val">
                    {{ row.TPWGST | number: '1.2-2' }}
                  </span>
                  <button mat-icon-button color="primary" class="autofill-btn"
                    *ngIf="isCurrentVersion"
                    (click)="autoFillTP(row)"
                    [disabled]="row.isAutoFilling"
                    matTooltip="Auto-fill TP from master">
                    <mat-spinner *ngIf="row.isAutoFilling" diameter="16"></mat-spinner>
                    <mat-icon *ngIf="!row.isAutoFilling">auto_fix_high</mat-icon>
                  </button>
                </div>
              </td>
            </ng-container>

            <!-- Marketing -->
            <ng-container matColumnDef="Marketing">
              <th mat-header-cell *matHeaderCellDef>Marketing</th>
              <td mat-cell *matCellDef="let row">
                <mat-form-field appearance="outline" class="cost-field" *ngIf="isCurrentVersion">
                  <input matInput type="number" [(ngModel)]="row.Marketing"
                    [ngModelOptions]="{standalone: true}" placeholder="0.00" step="0.01" />
                </mat-form-field>
                <span *ngIf="!isCurrentVersion" class="readonly-val">
                  {{ row.Marketing | number: '1.2-2' }}
                </span>
              </td>
            </ng-container>

            <!-- Dynamic cost head columns -->
            <ng-container *ngFor="let ch of visibleCostHeads" [matColumnDef]="ch.key">
              <th mat-header-cell *matHeaderCellDef>{{ ch.label }}</th>
              <td mat-cell *matCellDef="let row">
                <mat-form-field appearance="outline" class="cost-field" *ngIf="isCurrentVersion">
                  <input matInput type="number" [(ngModel)]="row[ch.key]"
                    [ngModelOptions]="{standalone: true}" placeholder="0.00" step="0.01" />
                </mat-form-field>
                <span *ngIf="!isCurrentVersion" class="readonly-val">
                  {{ row[ch.key] | number: '1.2-2' }}
                </span>
              </td>
            </ng-container>

            <!-- Basic Rate -->
            <ng-container matColumnDef="basicRate">
              <th mat-header-cell *matHeaderCellDef class="highlight-col">Basic Rate</th>
              <td mat-cell *matCellDef="let row" class="highlight-col">
                <mat-form-field appearance="outline" class="cost-field" *ngIf="isCurrentVersion">
                  <input matInput type="number" [(ngModel)]="row.basicRate"
                    [ngModelOptions]="{standalone: true}" placeholder="0.00" step="0.01" />
                </mat-form-field>
                <span *ngIf="!isCurrentVersion" class="readonly-val font-bold">
                  {{ row.basicRate | number: '1.2-2' }}
                </span>
              </td>
            </ng-container>

            <!-- GST -->
            <ng-container matColumnDef="GST">
              <th mat-header-cell *matHeaderCellDef>GST %</th>
              <td mat-cell *matCellDef="let row">
                <mat-form-field appearance="outline" class="cost-field-sm" *ngIf="isCurrentVersion">
                  <input matInput type="number" [(ngModel)]="row.GST"
                    [ngModelOptions]="{standalone: true}" placeholder="18" min="0" max="100" />
                </mat-form-field>
                <span *ngIf="!isCurrentVersion" class="readonly-val">
                  {{ row.GST }}%
                </span>
              </td>
            </ng-container>

            <!-- EXFOR Price -->
            <ng-container matColumnDef="EXFORPrice">
              <th mat-header-cell *matHeaderCellDef class="highlight-col">EXFOR Price</th>
              <td mat-cell *matCellDef="let row" class="highlight-col">
                <mat-form-field appearance="outline" class="cost-field" *ngIf="isCurrentVersion">
                  <input matInput type="number" [(ngModel)]="row.EXFORPrice"
                    [ngModelOptions]="{standalone: true}" placeholder="0.00" step="0.01" />
                </mat-form-field>
                <span *ngIf="!isCurrentVersion" class="readonly-val font-bold">
                  {{ row.EXFORPrice | number: '1.2-2' }}
                </span>
              </td>
            </ng-container>

            <tr mat-header-row *matHeaderRowDef="displayedColumns; sticky: true"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          </table>
        </div>

        <!-- Toggle extra cost points -->
        <div class="show-more-row">
          <button mat-stroked-button (click)="toggleExtraCostPoints()">
            <mat-icon>{{ showAllCostPoints ? 'expand_less' : 'expand_more' }}</mat-icon>
            {{ showAllCostPoints ? 'Show fewer cost heads' : 'Show all 20 cost heads' }}
          </button>
        </div>
      </div>

    </div>
  `,
  styles: [`
    .enquiry-costing-container {
      padding: 8px 0;
    }

    .costing-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .section-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 16px;
      font-weight: 500;
      color: #424242;
    }

    .section-title mat-icon {
      color: #1976d2;
    }

    .toolbar-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .version-select {
      width: 200px;
      margin-bottom: -1.25em;
    }

    .toolbar-right button mat-spinner {
      display: inline-block;
      margin-right: 6px;
      vertical-align: middle;
    }

    .readonly-banner {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #fff8e1;
      border: 1px solid #ffe082;
      border-radius: 4px;
      padding: 8px 12px;
      margin-bottom: 12px;
      color: #5d4037;
      font-size: 13px;
    }

    .loading-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 24px;
      color: #616161;
    }

    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px;
      color: #9e9e9e;
    }

    .no-data mat-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      margin-bottom: 8px;
    }

    .table-wrapper {
      border: 1px solid #e0e0e0;
      border-radius: 4px;
      overflow: hidden;
    }

    .table-scroll {
      overflow-x: auto;
    }

    .costing-table {
      width: max-content;
      min-width: 100%;
    }

    .sticky-col {
      position: sticky;
      left: 0;
      background: white;
      z-index: 2;
      border-right: 2px solid #e0e0e0;
    }

    th.sticky-col {
      background: #f5f5f5;
      z-index: 3;
    }

    .item-desc-cell {
      min-width: 180px;
    }

    .item-desc {
      display: flex;
      flex-direction: column;
    }

    .item-dim {
      font-size: 11px;
      color: #757575;
    }

    .cost-field {
      width: 110px;
      margin-bottom: -1.25em;
    }

    .cost-field-sm {
      width: 80px;
      margin-bottom: -1.25em;
    }

    .readonly-val {
      display: inline-block;
      padding: 6px 4px;
      min-width: 80px;
      font-size: 13px;
      color: #424242;
    }

    .font-bold {
      font-weight: 600;
    }

    .highlight-col {
      background: #e3f2fd;
    }

    th.highlight-col {
      background: #bbdefb;
      font-weight: 600;
    }

    .field-with-action {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .autofill-btn {
      flex-shrink: 0;
    }

    .latest-badge {
      font-size: 11px;
      color: #2e7d32;
      font-weight: 600;
    }

    .show-more-row {
      display: flex;
      justify-content: center;
      padding: 8px;
      border-top: 1px solid #e0e0e0;
      background: #fafafa;
    }
  `],
})
export class EnquiryCostingComponent implements OnInit, OnChanges {
  @Input() enqId!: number;

  versions: CostingVersion[] = [];
  selectedVersionId: number | null = null;
  isCurrentVersion = false;

  dataSource = new MatTableDataSource<CostingRow>([]);

  showAllCostPoints = false;

  allCostHeads: { key: string; label: string }[] = [
    { key: 'FreightTrailer', label: 'Freight Trailer' },
    { key: 'FreightTruck', label: 'Freight Truck' },
    { key: 'Unloading', label: 'Unloading' },
    { key: 'OHD', label: 'OHD' },
    { key: 'IFC', label: 'IFC' },
    { key: 'WeighmentDiff', label: 'Weighment Diff' },
    { key: 'CD', label: 'CD' },
    { key: 'SWECharge', label: 'SWE Charge' },
    { key: 'CRS', label: 'CRS' },
    { key: 'IncCharge', label: 'Inc Charge' },
    { key: 'ShortLnthCharge', label: 'Short Length' },
    { key: 'SpeciFicLnthCharge', label: 'Specific Length' },
    { key: 'ExtraCharge', label: 'Extra Charge' },
    { key: 'Fluctuation', label: 'Fluctuation' },
    { key: 'Commission', label: 'Commission' },
    { key: 'Misc', label: 'Misc' },
    { key: 'Testing', label: 'Testing' },
    { key: 'MOUTOD', label: 'MOUTOD' },
    { key: 'SplDisc', label: 'Spl Disc' },
    { key: 'JC', label: 'JC' },
  ];

  get visibleCostHeads(): { key: string; label: string }[] {
    return this.showAllCostPoints ? this.allCostHeads : this.allCostHeads.slice(0, 6);
  }

  isLoading = false;
  isSaving = false;
  isCreatingVersion = false;

  get displayedColumns(): string[] {
    const chCols = this.visibleCostHeads.map((ch) => ch.key);
    return ['itemDesc', 'TPWGST', 'Marketing', ...chCols, 'basicRate', 'GST', 'EXFORPrice'];
  }

  constructor(
    private apiService: ApiService,
    private notificationService: NotificationService,
  ) { }

  ngOnInit(): void {
    if (this.enqId) {
      this.loadVersions();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['enqId'] && !changes['enqId'].firstChange && this.enqId) {
      this.loadVersions();
    }
  }

  loadVersions(): void {
    this.apiService.get<CostingVersion[]>(`/enquiries/${this.enqId}/costing/versions`).subscribe({
      next: (versions) => {
        this.versions = versions;
        if (versions.length) {
          const latest = versions.find((v) => v.isLatest) ?? versions[versions.length - 1];
          this.selectedVersionId = latest.id;
          this.onVersionChange(latest.id);
        }
      },
      error: () => this.notificationService.error('Failed to load costing versions'),
    });
  }

  onVersionChange(versionId: number): void {
    this.selectedVersionId = versionId;
    const version = this.versions.find((v) => v.id === versionId);
    this.isCurrentVersion = version?.isLatest ?? false;
    this.loadCostingData(versionId);
  }

  loadCostingData(versionId: number): void {
    this.isLoading = true;
    this.apiService
      .get<CostingRow[]>(`/enquiries/${this.enqId}/costing/versions/${versionId}`)
      .subscribe({
        next: (data) => {
          this.dataSource.data = data.map((r) => ({ ...r, isAutoFilling: false }));
          this.isLoading = false;
        },
        error: () => {
          this.notificationService.error('Failed to load costing data');
          this.isLoading = false;
        },
      });
  }

  createNewVersion(): void {
    this.isCreatingVersion = true;
    this.apiService
      .post<CostingVersion>(`/enquiries/${this.enqId}/costing/new-version`, {})
      .subscribe({
        next: (newVersion) => {
          this.isCreatingVersion = false;
          this.notificationService.success(`Version ${newVersion.versionNo} created`);
          this.loadVersions();
        },
        error: () => {
          this.notificationService.error('Failed to create new version');
          this.isCreatingVersion = false;
        },
      });
  }

  autoFillTP(row: CostingRow): void {
    if (!row.itemDia) {
      this.notificationService.error('No diameter specified for this line item');
      return;
    }
    row.isAutoFilling = true;
    this.apiService
      .get<{ tpcost: number }>(
        `/enquiries/${this.enqId}/costing/auto-fill/${row.itemDia}`
      )
      .subscribe({
        next: (data) => {
          row.TPWGST = data.tpcost;
          row.isAutoFilling = false;
          this.notificationService.success('TP auto-filled from master');
          this.refreshTable();
        },
        error: () => {
          this.notificationService.error('Failed to auto-fill TP cost');
          row.isAutoFilling = false;
        },
      });
  }

  onTPChange(row: CostingRow): void {
    // Optionally compute Marketing from TPWGST if GST% is known
    if (row.TPWGST && row.GST) {
      row.Marketing = parseFloat((row.TPWGST / (1 + row.GST / 100)).toFixed(2));
      this.refreshTable();
    }
  }

  saveCosting(): void {
    if (!this.isCurrentVersion) return;

    this.isSaving = true;
    const payload = this.dataSource.data.map(({ isAutoFilling, ...rest }) => rest);

    this.apiService
      .put<any>(
        `/enquiries/${this.enqId}/costing/versions/${this.selectedVersionId}`,
        payload
      )
      .subscribe({
        next: () => {
          this.isSaving = false;
          this.notificationService.success('Costing saved successfully');
        },
        error: () => {
          this.isSaving = false;
          this.notificationService.error('Failed to save costing');
        },
      });
  }

  toggleExtraCostPoints(): void {
    this.showAllCostPoints = !this.showAllCostPoints;
  }

  private refreshTable(): void {
    this.dataSource.data = [...this.dataSource.data];
  }
}
