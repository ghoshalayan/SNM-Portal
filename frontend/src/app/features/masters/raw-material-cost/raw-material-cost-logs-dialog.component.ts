import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatTableModule } from '@angular/material/table';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { environment } from '../../../../environments/environment';

export interface RawMatCostLogsDialogData {
  rawMaterialCostId: number;
  dia: string;
  currentCost: number;
}

interface LogRow {
  logId: number;
  dia: string;
  oldCost: number | null;
  newCost: number;
  oldEffectedFrom: string | null;
  newEffectedFrom: string | null;
  action: string;
  remarks: string | null;
  changedBy: number | null;
  changedByName: string | null;
  changedOn: string;
}

@Component({
  selector: 'app-raw-material-cost-logs-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatButtonModule, MatIconModule,
    MatFormFieldModule, MatInputModule, MatDatepickerModule, MatNativeDateModule,
    MatTableModule, MatPaginatorModule, MatProgressBarModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>history</mat-icon>
      Update Logs — Dia {{ data.dia }}
      <span class="current-cost">Current Cost: ₹ {{ data.currentCost | number:'1.2-2' }}</span>
    </h2>

    <mat-dialog-content>
      <div class="filters">
        <mat-form-field appearance="outline">
          <mat-label>From Date</mat-label>
          <input matInput [matDatepicker]="fromPicker" [(ngModel)]="fromDate" (dateChange)="onFilterChange()">
          <mat-datepicker-toggle matSuffix [for]="fromPicker"></mat-datepicker-toggle>
          <mat-datepicker #fromPicker></mat-datepicker>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>To Date</mat-label>
          <input matInput [matDatepicker]="toPicker" [(ngModel)]="toDate" (dateChange)="onFilterChange()">
          <mat-datepicker-toggle matSuffix [for]="toPicker"></mat-datepicker-toggle>
          <mat-datepicker #toPicker></mat-datepicker>
        </mat-form-field>

        <button mat-stroked-button (click)="clearFilters()" [disabled]="!fromDate && !toDate">
          <mat-icon>clear</mat-icon> Clear
        </button>

        <span class="spacer"></span>

        <button mat-stroked-button class="excel-btn"
          (click)="downloadExcel()"
          [disabled]="downloading"
          matTooltip="Download logs as Excel">
          <mat-icon>download</mat-icon>
          {{ downloading ? 'Downloading...' : 'Excel' }}
        </button>
      </div>

      <mat-progress-bar *ngIf="loading" mode="indeterminate"></mat-progress-bar>

      <table mat-table [dataSource]="logs" class="logs-table">
        <ng-container matColumnDef="changedOn">
          <th mat-header-cell *matHeaderCellDef>Changed On (IST)</th>
          <td mat-cell *matCellDef="let r">{{ r.changedOn | date:'dd-MM-yyyy HH:mm' }}</td>
        </ng-container>

        <ng-container matColumnDef="changedByName">
          <th mat-header-cell *matHeaderCellDef>Changed By</th>
          <td mat-cell *matCellDef="let r">{{ r.changedByName || '—' }}</td>
        </ng-container>

        <ng-container matColumnDef="oldCost">
          <th mat-header-cell *matHeaderCellDef class="num">Old Cost</th>
          <td mat-cell *matCellDef="let r" class="num">
            {{ r.oldCost != null ? (r.oldCost | number:'1.2-2') : '—' }}
          </td>
        </ng-container>

        <ng-container matColumnDef="newCost">
          <th mat-header-cell *matHeaderCellDef class="num">New Cost</th>
          <td mat-cell *matCellDef="let r" class="num">{{ r.newCost | number:'1.2-2' }}</td>
        </ng-container>

        <ng-container matColumnDef="delta">
          <th mat-header-cell *matHeaderCellDef class="num">Change</th>
          <td mat-cell *matCellDef="let r" class="num"
            [class.positive]="getDelta(r) > 0"
            [class.negative]="getDelta(r) < 0">
            <ng-container *ngIf="r.oldCost != null; else noDelta">
              {{ getDelta(r) > 0 ? '+' : '' }}{{ getDelta(r) | number:'1.2-2' }}
            </ng-container>
            <ng-template #noDelta>—</ng-template>
          </td>
        </ng-container>

        <ng-container matColumnDef="effectedFrom">
          <th mat-header-cell *matHeaderCellDef>Effected From</th>
          <td mat-cell *matCellDef="let r">
            {{ r.newEffectedFrom | date:'dd-MM-yyyy' }}
            <span *ngIf="r.oldEffectedFrom !== r.newEffectedFrom" class="was">
              (was: {{ r.oldEffectedFrom | date:'dd-MM-yyyy' }})
            </span>
          </td>
        </ng-container>

        <ng-container matColumnDef="remarks">
          <th mat-header-cell *matHeaderCellDef>Remarks</th>
          <td mat-cell *matCellDef="let r">{{ r.remarks || '—' }}</td>
        </ng-container>

        <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
        <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
        <tr class="mat-row" *matNoDataRow>
          <td class="mat-cell empty" [attr.colspan]="displayedColumns.length">
            {{ loading ? '' : 'No logs found.' }}
          </td>
        </tr>
      </table>

      <mat-paginator
        [length]="total"
        [pageSize]="pageSize"
        [pageIndex]="page - 1"
        [pageSizeOptions]="[10, 25, 50, 100]"
        (page)="onPageChange($event)"
        showFirstLastButtons>
      </mat-paginator>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host mat-dialog-content { min-width: 900px; max-width: 1200px; max-height: 70vh; }
    h2[mat-dialog-title] { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .current-cost { font-size: 13px; color: #1565c0; font-weight: 500; margin-left: auto; }
    .filters {
      display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
    }
    .filters mat-form-field { width: 180px; }
    .spacer { flex: 1; }
    .excel-btn { border-color: #1d6f42; color: #1d6f42;
      mat-icon { color: #1d6f42; }
    }
    .logs-table { width: 100%; }
    .num { text-align: right; }
    .positive { color: #00703c; font-weight: 500; }
    .negative { color: #c00000; font-weight: 500; }
    .was { font-size: 11px; color: #888; margin-left: 4px; }
    .empty { padding: 20px; text-align: center; color: #888; }
  `],
})
export class RawMaterialCostLogsDialogComponent implements OnInit {
  logs: LogRow[] = [];
  total = 0;
  page = 1;
  pageSize = 25;
  loading = false;
  downloading = false;
  fromDate: Date | null = null;
  toDate: Date | null = null;

  displayedColumns = [
    'changedOn', 'changedByName', 'oldCost', 'newCost', 'delta', 'effectedFrom', 'remarks',
  ];

  constructor(
    private api: ApiService,
    private http: HttpClient,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<RawMaterialCostLogsDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: RawMatCostLogsDialogData,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  getDelta(r: LogRow): number {
    if (r.oldCost == null) return 0;
    return r.newCost - r.oldCost;
  }

  buildParams(): Record<string, string> {
    const params: Record<string, string> = {
      page: String(this.page),
      pageSize: String(this.pageSize),
    };
    if (this.fromDate) {
      params['dateFrom'] = this.toIso(this.fromDate, false);
    }
    if (this.toDate) {
      params['dateTo'] = this.toIso(this.toDate, true);
    }
    return params;
  }

  private toIso(d: Date, endOfDay: boolean): string {
    const day = new Date(d);
    if (endOfDay) {
      day.setHours(23, 59, 59, 999);
    } else {
      day.setHours(0, 0, 0, 0);
    }
    return day.toISOString();
  }

  load(): void {
    this.loading = true;
    const url = `/masters/raw-material-costs/${this.data.rawMaterialCostId}/logs`;
    this.api.get<any>(url, this.buildParams()).subscribe({
      next: (res) => {
        this.logs = res.items || [];
        this.total = res.total || 0;
        this.loading = false;
      },
      error: () => {
        this.notify.error('Failed to load logs');
        this.loading = false;
      },
    });
  }

  onFilterChange(): void {
    this.page = 1;
    this.load();
  }

  clearFilters(): void {
    this.fromDate = null;
    this.toDate = null;
    this.onFilterChange();
  }

  onPageChange(ev: PageEvent): void {
    this.page = ev.pageIndex + 1;
    this.pageSize = ev.pageSize;
    this.load();
  }

  downloadExcel(): void {
    if (this.downloading) return;
    this.downloading = true;
    const url = `${environment.apiUrl}/masters/raw-material-costs/${this.data.rawMaterialCostId}/logs/export-excel`;
    const params: any = {};
    if (this.fromDate) params.dateFrom = this.toIso(this.fromDate, false);
    if (this.toDate) params.dateTo = this.toIso(this.toDate, true);
    this.http.get(url, { params, responseType: 'blob', observe: 'response' }).subscribe({
      next: (resp) => {
        const blob = resp.body;
        if (!blob) {
          this.notify.error('Empty response');
          this.downloading = false;
          return;
        }
        let filename = `rawmat-cost-${this.data.dia}-logs.xlsx`;
        const cd = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
        if (cd) {
          const m = /filename="?([^";]+)"?/i.exec(cd);
          if (m && m[1]) filename = m[1];
        }
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
        this.downloading = false;
      },
      error: () => {
        this.notify.error('Failed to download Excel');
        this.downloading = false;
      },
    });
  }

  close(): void {
    this.dialogRef.close();
  }
}
