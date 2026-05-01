import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatExpansionModule } from '@angular/material/expansion';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface QuotationVersion {
  id: number;
  versionNo: number;
  quotDate: string;
  status: string;
  approvedBy: string;
  approvedAt?: string;
  subject?: string;
  remarks?: string;
}

export interface ActivityLogEntry {
  logId: number;
  action: string;
  status?: string;
  outcome?: 'Success' | 'Failure';
  details?: string;
  actionOn: string;
  actionByUserId?: number;
  actionByName?: string;
}

@Component({
  selector: 'app-quotation-version-history',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatChipsModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatDividerModule,
    MatExpansionModule,
  ],
  template: `
    <div class="version-history-container">
      <div class="section-header">
        <h3>Version History</h3>
      </div>

      <div *ngIf="loading" class="spinner-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <p *ngIf="!loading && versions.length === 0" class="empty-state">
        No version history found.
      </p>

      <!-- Version Table -->
      <div class="table-wrapper" *ngIf="!loading && versions.length > 0">
        <table mat-table [dataSource]="dataSource" class="version-table">

          <ng-container matColumnDef="versionNo">
            <th mat-header-cell *matHeaderCellDef>Version</th>
            <td mat-cell *matCellDef="let row">
              <mat-chip-set>
                <mat-chip [class]="row.id === currentVersionId ? 'current-chip' : ''">
                  v{{ row.versionNo }}
                  <span *ngIf="row.id === currentVersionId" class="current-label"> (current)</span>
                </mat-chip>
              </mat-chip-set>
            </td>
          </ng-container>

          <ng-container matColumnDef="quotDate">
            <th mat-header-cell *matHeaderCellDef>Date</th>
            <td mat-cell *matCellDef="let row">{{ row.quotDate | date:'dd-MM-yyyy' }}</td>
          </ng-container>

          <ng-container matColumnDef="subject">
            <th mat-header-cell *matHeaderCellDef>Subject</th>
            <td mat-cell *matCellDef="let row">{{ row.subject || '—' }}</td>
          </ng-container>

          <ng-container matColumnDef="status">
            <th mat-header-cell *matHeaderCellDef>Status</th>
            <td mat-cell *matCellDef="let row">
              <span class="status-badge" [ngClass]="getStatusClass(row.status)">
                {{ row.status }}
              </span>
            </td>
          </ng-container>

          <ng-container matColumnDef="approvedBy">
            <th mat-header-cell *matHeaderCellDef>Approved By</th>
            <td mat-cell *matCellDef="let row">
              <ng-container *ngIf="row.approvedBy; else notApproved">
                <div>{{ row.approvedBy }}</div>
                <div class="approved-date" *ngIf="row.approvedAt">
                  {{ row.approvedAt | date:'dd-MM-yyyy HH:mm' }}
                </div>
              </ng-container>
              <ng-template #notApproved>—</ng-template>
            </td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button
                mat-icon-button
                color="primary"
                (click)="toggleVersionDetails(row)"
                [matTooltip]="selectedVersion?.id === row.id ? 'Collapse' : 'View Details'">
                <mat-icon>{{ selectedVersion?.id === row.id ? 'expand_less' : 'visibility' }}</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr
            mat-row
            *matRowDef="let row; columns: displayedColumns;"
            [class.selected-row]="selectedVersion?.id === row.id"
            class="version-row">
          </tr>
        </table>
      </div>

      <!-- Version Detail Panel -->
      <mat-card *ngIf="selectedVersion" class="version-detail-card">
        <mat-card-header>
          <mat-card-title>
            Version {{ selectedVersion.versionNo }} — Details
            <span class="status-badge" [ngClass]="getStatusClass(selectedVersion.status)" style="margin-left:12px;">
              {{ selectedVersion.status }}
            </span>
          </mat-card-title>
          <button mat-icon-button (click)="selectedVersion = null" style="margin-left:auto;" matTooltip="Close">
            <mat-icon>close</mat-icon>
          </button>
        </mat-card-header>
        <mat-card-content>
          <div class="detail-grid">
            <div class="detail-item">
              <label>Version No</label>
              <span>v{{ selectedVersion.versionNo }}</span>
            </div>
            <div class="detail-item">
              <label>Quotation Date</label>
              <span>{{ selectedVersion.quotDate | date:'dd-MM-yyyy' }}</span>
            </div>
            <div class="detail-item">
              <label>Status</label>
              <span>{{ selectedVersion.status }}</span>
            </div>
            <div class="detail-item">
              <label>Approved By</label>
              <span>{{ selectedVersion.approvedBy || '—' }}</span>
            </div>
            <div class="detail-item" *ngIf="selectedVersion.approvedAt">
              <label>Approved At</label>
              <span>{{ selectedVersion.approvedAt | date:'dd-MM-yyyy HH:mm' }}</span>
            </div>
            <div class="detail-item full-span" *ngIf="selectedVersion.subject">
              <label>Subject</label>
              <span>{{ selectedVersion.subject }}</span>
            </div>
            <div class="detail-item full-span" *ngIf="selectedVersion.remarks">
              <label>Remarks</label>
              <span>{{ selectedVersion.remarks }}</span>
            </div>
          </div>

          <p class="read-only-note">
            <mat-icon style="font-size:16px;vertical-align:middle;">info</mat-icon>
            This is a read-only view of a historical version.
          </p>
        </mat-card-content>
      </mat-card>

      <!-- Timewise Activity Log — appended below versions -->
      <div class="section-header activity-header">
        <h3><mat-icon class="act-icon">history</mat-icon> Activity Log</h3>
        <span class="act-hint">All lifecycle actions on this quotation, newest first</span>
      </div>

      <div *ngIf="loadingActivity" class="spinner-container">
        <mat-spinner diameter="32"></mat-spinner>
      </div>

      <p *ngIf="!loadingActivity && activityLog.length === 0" class="empty-state">
        No activity recorded yet.
      </p>

      <div class="table-wrapper" *ngIf="!loadingActivity && activityLog.length > 0">
        <table mat-table [dataSource]="activityLog" class="activity-table">
          <ng-container matColumnDef="date">
            <th mat-header-cell *matHeaderCellDef>Date</th>
            <td mat-cell *matCellDef="let row">{{ row.actionOn | date:'dd-MM-yyyy' }}</td>
          </ng-container>
          <ng-container matColumnDef="time">
            <th mat-header-cell *matHeaderCellDef>Time</th>
            <td mat-cell *matCellDef="let row">{{ row.actionOn | date:'HH:mm:ss' }}</td>
          </ng-container>
          <ng-container matColumnDef="action">
            <th mat-header-cell *matHeaderCellDef>Action Taken</th>
            <td mat-cell *matCellDef="let row">
              <strong>{{ row.action }}</strong>
              <div class="act-details" *ngIf="row.details">{{ row.details }}</div>
            </td>
          </ng-container>
          <ng-container matColumnDef="status">
            <th mat-header-cell *matHeaderCellDef>Stage</th>
            <td mat-cell *matCellDef="let row">
              <span *ngIf="row.status" class="status-badge" [ngClass]="getStatusClass(row.status)">
                {{ row.status }}
              </span>
              <span *ngIf="!row.status">—</span>
            </td>
          </ng-container>
          <ng-container matColumnDef="outcome">
            <th mat-header-cell *matHeaderCellDef>Outcome</th>
            <td mat-cell *matCellDef="let row">
              <span class="outcome-chip"
                    [class.outcome-success]="(row.outcome || 'Success') === 'Success'"
                    [class.outcome-failure]="row.outcome === 'Failure'">
                <mat-icon class="outcome-icon">
                  {{ row.outcome === 'Failure' ? 'error_outline' : 'check_circle_outline' }}
                </mat-icon>
                {{ row.outcome || 'Success' }}
              </span>
            </td>
          </ng-container>
          <ng-container matColumnDef="actor">
            <th mat-header-cell *matHeaderCellDef>Action Taken By</th>
            <td mat-cell *matCellDef="let row">{{ row.actionByName || '—' }}</td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="activityColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: activityColumns;"
              [class.log-row-failure]="row.outcome === 'Failure'"></tr>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .version-history-container {
      padding: 16px 0;
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .section-header h3 {
      margin: 0;
    }

    .spinner-container {
      display: flex;
      justify-content: center;
      padding: 32px;
    }

    .empty-state {
      text-align: center;
      color: #666;
      padding: 32px;
      font-style: italic;
    }

    .table-wrapper {
      overflow-x: auto;
      margin-bottom: 20px;
    }

    .version-table {
      width: 100%;
    }

    .version-row:hover {
      background-color: #f5f5f5;
    }

    .selected-row {
      background-color: #e3f2fd !important;
    }

    .current-chip {
      background-color: #1565c0 !important;
      color: #fff !important;
    }

    .current-label {
      font-size: 11px;
      opacity: 0.85;
    }

    .approved-date {
      font-size: 11px;
      color: #888;
      margin-top: 2px;
    }

    .version-detail-card {
      margin-top: 16px;
    }

    mat-card-header {
      display: flex;
      align-items: center;
    }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
      margin-top: 16px;
    }

    .detail-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .detail-item label {
      font-size: 12px;
      font-weight: 600;
      color: #777;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .detail-item span {
      font-size: 15px;
      color: #222;
    }

    .full-span {
      grid-column: 1 / -1;
    }

    .read-only-note {
      color: #888;
      font-size: 13px;
      margin-top: 20px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* Activity Log */
    .activity-header {
      margin-top: 28px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .activity-header h3 {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .act-icon { color: var(--snm-accent-dark, #3a6bb5); }
    .act-hint {
      font-size: 12px;
      color: var(--snm-text-muted);
      font-weight: 400;
    }
    .activity-table { width: 100%; }
    .activity-table th.mat-mdc-header-cell {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .activity-table td.mat-mdc-cell { font-size: 13px; }
    .act-details {
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }

    /* Outcome chip — green for Success, red for Failure */
    .outcome-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      line-height: 1.5;
    }
    .outcome-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .outcome-success {
      background: rgba(46, 125, 50, 0.12);
      color: #4caf50;
      border: 1px solid rgba(46, 125, 50, 0.28);
    }
    .outcome-failure {
      background: rgba(198, 40, 40, 0.12);
      color: #ef5350;
      border: 1px solid rgba(198, 40, 40, 0.28);
    }
    .log-row-failure td { background: rgba(198, 40, 40, 0.04); }
  `],
})
export class QuotationVersionHistoryComponent implements OnInit, OnChanges {
  @Input() quotId!: number;

  versions: QuotationVersion[] = [];
  dataSource = new MatTableDataSource<QuotationVersion>();
  selectedVersion: QuotationVersion | null = null;
  currentVersionId: number | null = null;
  loading = false;

  displayedColumns: string[] = ['versionNo', 'quotDate', 'subject', 'status', 'approvedBy', 'actions'];

  // Activity log (lifecycle audit trail)
  activityLog: ActivityLogEntry[] = [];
  loadingActivity = false;
  activityColumns: string[] = ['date', 'time', 'action', 'status', 'outcome', 'actor'];

  constructor(
    private apiService: ApiService,
    private notificationService: NotificationService,
  ) {}

  ngOnInit(): void {
    if (this.quotId) {
      this.loadVersions();
      this.loadActivityLog();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && !changes['quotId'].firstChange) {
      this.loadVersions();
      this.loadActivityLog();
    }
  }

  loadActivityLog(): void {
    if (!this.quotId) return;
    this.loadingActivity = true;
    this.apiService.get<ActivityLogEntry[]>(`/quotations/${this.quotId}/activity-log`).subscribe({
      next: (rows) => {
        this.loadingActivity = false;
        this.activityLog = rows || [];
      },
      error: () => {
        this.loadingActivity = false;
        this.activityLog = [];
      },
    });
  }

  loadVersions(): void {
    this.loading = true;
    this.apiService.get<QuotationVersion[]>(`/quotations/${this.quotId}/versions`).subscribe({
      next: (data) => {
        this.versions = data.sort((a, b) => b.versionNo - a.versionNo);
        this.dataSource.data = this.versions;
        // Mark the current version as the one with the highest version number
        if (this.versions.length > 0) {
          this.currentVersionId = this.versions[0].id;
        }
        this.loading = false;
      },
      error: () => {
        this.notificationService.error('Failed to load version history.');
        this.loading = false;
      },
    });
  }

  toggleVersionDetails(version: QuotationVersion): void {
    if (this.selectedVersion?.id === version.id) {
      this.selectedVersion = null;
    } else {
      this.selectedVersion = version;
    }
  }

  getStatusClass(status: string): string {
    const map: Record<string, string> = {
      Draft: 'status-draft',
      Pending: 'status-pending',
      Approved: 'status-approved',
      Matured: 'status-matured',
      Reject: 'status-reject',
      Rejected: 'status-rejected',
      Revised: 'status-revised',
      ViabilityGenerated: 'status-viability-generated',
      ViabilityApproved: 'status-viability-approved',
      AnnexureGenerated: 'status-annexure-generated',
      AnnexureApproved: 'status-annexure-approved',
    };
    return map[status] ?? 'status-draft';
  }
}
