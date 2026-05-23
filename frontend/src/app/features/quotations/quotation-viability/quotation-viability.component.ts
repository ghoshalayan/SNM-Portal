import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatBadgeModule } from '@angular/material/badge';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';

import { environment } from '../../../../environments/environment';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuService } from '../../../core/services/menu.service';
import { LifecycleUnlockDialogComponent } from '../lifecycle-unlock-dialog/lifecycle-unlock-dialog.component';
import { StaleBannerComponent } from '../stale-banner/stale-banner.component';
import { ViabilitySnapshotViewerDialogComponent } from '../../../shared/components/snapshot-viewer/viability-snapshot-viewer-dialog.component';
import {
  CycleService,
  ViabilityApprovalSnapshot,
} from '../services/cycle.service';
import {
  VersionInlinePickerComponent,
  VersionInlineItem,
} from '../shared/version-inline-picker.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import {
  BulkApplyCandidateRow,
  BulkApplyDialogComponent,
  BulkApplyDialogData,
  BulkApplyDialogResult,
} from '../shared/bulk-apply-dialog.component';
import {
  SheetPreviewColumn,
  SheetPreviewDialogComponent,
  SheetPreviewDialogData,
} from '../shared/sheet-preview-dialog.component';
import {
  TextPromptDialogComponent,
  TextPromptDialogData,
} from '../../../shared/components/text-prompt-dialog/text-prompt-dialog.component';
import {
  ADJUSTABLE_HEADS,
  GoalSeekDialogComponent,
  GoalSeekDialogData,
  GoalSeekDialogResult,
  HEAD_LABEL,
} from './goal-seek-dialog.component';

// All cost-head columns in display order (TPWGST first, then 21 adjustable).
const COST_HEADS = ['TPWGST', ...ADJUSTABLE_HEADS];

// Column meta for the working-sheet table (read-only snapshot).
interface ColMeta { key: string; label: string; width: string; num?: boolean; neg?: boolean; deducted?: boolean; }

/** Rendered in the savings summary strip below the two tables. */
interface SavingsRow {
  lineId: number;
  itemName: string;
  /** Either `<dia>` or `<old> → <new>` when dia was changed in viability. */
  diaLabel: string;
  workingRate: number;
  viabRate: number;
  savingPerMt: number;
  orderedQty: number;
  totalSaving: number;
  /** true when dia differs between working sheet and viability — excluded from grand total. */
  excluded: boolean;
}
// Light-red text only (subtractive in totals via goal-seek before CR #2,
// or kept for visual context). CD + SplDisc graduate to a heavier
// `deducted` styling per CR #2 — see DEDUCTED_KEYS below.
const NEGATIVE_KEYS = new Set(['CD', 'ShortLnthCharge', 'SplDisc']);
// Cost heads users enter positively but the math subtracts (CR #2).
// Kept in sync with the backend ``DEDUCTED_COST_HEADS`` constant.
const DEDUCTED_KEYS = new Set(['CD', 'SplDisc']);

function headCol(key: string): ColMeta {
  return {
    key,
    label: HEAD_LABEL[key] || key,
    width: '90px',
    num: true,
    neg: NEGATIVE_KEYS.has(key),
    deducted: DEDUCTED_KEYS.has(key),
  };
}

const WORKING_COLS: ColMeta[] = [
  { key: '_sno', label: '#', width: '44px' },
  { key: 'itemName', label: 'Item', width: '150px' },
  { key: 'itemGradeName', label: 'Grade', width: '110px' },
  { key: 'itemDia', label: 'Dia', width: '70px' },
  { key: 'itemLength', label: 'Length', width: '90px' },
  { key: 'quantity', label: 'Qty', width: '70px', num: true },
  ...COST_HEADS.map(headCol),
  { key: 'totRate', label: 'Total Rs/MT', width: '110px', num: true },
  { key: '_gst', label: 'GST @ 18%', width: '90px', num: true },
  { key: 'totAmount', label: 'EX/FOR Price', width: '110px', num: true },
  { key: 'modeOfDispatch', label: 'Dispatch', width: '120px' },
];

// Viability table adds 4 gross columns after EX/FOR Price. Mode goes at the end.
const VIABILITY_COLS: ColMeta[] = [
  ...WORKING_COLS.slice(0, -1),
  { key: 'orderedQty', label: 'Ordered Qty (MT)', width: '100px', num: true },
  { key: 'totalAmount', label: 'Total Amount', width: '120px', num: true },
  { key: 'totalGst', label: 'Total GST', width: '110px', num: true },
  { key: 'grossExForPrice', label: 'Gross EX/FOR', width: '120px', num: true },
  WORKING_COLS[WORKING_COLS.length - 1],
];

const EDITABLE_IN_VIABILITY = new Set<string>([
  'itemName', 'itemGradeName', 'itemDia', 'itemLength', 'orderedQty',
  ...COST_HEADS,
]);

// Keys rendered as mat-select dropdowns (when editable). Everything else
// in the editable set falls back to a plain input.
const DROPDOWN_KEYS = new Set<string>(['itemName', 'itemGradeName', 'itemDia', 'itemLength']);

interface ItemNameOpt { itemId: number; itemName: string; itemGradeId?: number; itemGradeName?: string; }
interface ItemGradeOpt { itemGradeId: number; itemGradeName: string; }
interface DiaOpt { diaid: number; itemid: number; diadescription: string; }
interface LengthOpt { itemLengthId: number; itemId: number; itemLength: string; }

@Component({
  selector: 'app-quotation-viability',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatCardModule, MatButtonModule, MatIconModule, MatDialogModule,
    MatProgressSpinnerModule, MatTooltipModule, MatMenuModule,
    MatCheckboxModule, MatBadgeModule, MatSelectModule, MatFormFieldModule,
    MatInputModule, MatButtonToggleModule, MatDatepickerModule, MatNativeDateModule,
    StaleBannerComponent,
    VersionInlinePickerComponent,
  ],
  template: `
    <mat-card class="stage-card viab-card">
      <div class="stage-card-head">
        <div class="stage-card-head-left">
          <mat-icon class="stage-card-head-icon">query_stats</mat-icon>
          <div class="stage-card-head-text">
            <div class="stage-card-head-title">
              Viability Sheet
              @if (sheet) {
                <span class="stage-status-chip" [class.is-approved]="sheet.status === 'Approved'">
                  {{ sheet.status }}
                </span>
                @if (snapshots.length > 0) {
                  <app-version-inline-picker
                    [items]="versionItems"
                    [currentId]="currentSnapshotId"
                    [busy]="busy || switching"
                    [headLabel]="'Viability versions'"
                    (picked)="onVersionPicked($event)">
                  </app-version-inline-picker>
                }
              }
            </div>
            <div class="stage-card-head-meta">
              Compare the Working Sheet with the adjusted Viability Sheet. Use goal-seek per line to hit a target Total Rs/MT.
            </div>
          </div>
        </div>

        <div class="stage-card-head-actions">
          @if (sheet) {
            <button mat-icon-button class="viab-tool-btn"
              (click)="toggleCompactMode()"
              [color]="compactMode ? 'primary' : undefined"
              [matTooltip]="compactMode ? 'Show all columns' : 'Compact view — hide empty columns'">
              <mat-icon>{{ compactMode ? 'unfold_more' : 'unfold_less' }}</mat-icon>
            </button>
            <button mat-icon-button class="viab-tool-btn"
              [matMenuTriggerFor]="viabColMenu"
              [matBadge]="hiddenHeadCount > 0 ? hiddenHeadCount : null"
              matBadgeColor="warn" matBadgeSize="small"
              matTooltip="Show / hide cost head columns">
              <mat-icon>view_column</mat-icon>
            </button>
            <mat-menu #viabColMenu="matMenu" class="col-picker-menu" xPosition="before">
              <div class="cp-header" (click)="$event.stopPropagation()">
                <span>Cost Head Columns</span>
                <button mat-button color="primary" type="button" (click)="showAllHeads()">Reset</button>
              </div>
              <div class="cp-body" (click)="$event.stopPropagation()">
                @for (h of costHeads; track h) {
                  <mat-checkbox
                    [checked]="!hiddenCostHeads.has(h)"
                    (change)="toggleCostHead(h, $event.checked)"
                    class="cp-item">
                    {{ costHeadLabel[h] || h }}
                  </mat-checkbox>
                }
              </div>
            </mat-menu>
          }
          @if (sheet && sheet.status === 'Draft' && canApprove) {
            <button mat-stroked-button color="primary" (click)="approve()" [disabled]="busy || switching">
              <mat-icon>verified</mat-icon> Approve Viability
            </button>
          }
          @if (sheet && (canRegenerate || canApprove)) {
            <button mat-stroked-button color="primary" (click)="regenerate()" [disabled]="busy || switching"
              matTooltip="Pick a different FWS version or past Viability version as the source and build a fresh draft from it. Carries goal-seek state forward when sourcing from a past Viability.">
              <mat-icon>refresh</mat-icon> Re-generate
            </button>
          }
          @if (sheet && sheet.status === 'Approved' && canUnlockEditViability && !unlockEditHidden) {
            <button mat-stroked-button color="warn" (click)="openUnlockDialog()" [disabled]="busy"
              matTooltip="Privileged: unlock this approved viability sheet for in-place edits (audited)">
              <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
            </button>
          }
          @if (sheet) {
            <button mat-stroked-button (click)="openPreview()" [disabled]="busy"
              matTooltip="Preview the viability sheet with blank columns hidden">
              <mat-icon>visibility</mat-icon> Preview
            </button>
            <button mat-stroked-button (click)="downloadExcel()" [disabled]="busy"
              matTooltip="Download both sheets in one workbook">
              <mat-icon>download</mat-icon> Download Excel
            </button>
          }
        </div>
      </div>

      <mat-card-content>
        <app-stale-banner
          *ngIf="sheet"
          [stale]="isViabilityStaleVsPo()"
          stageLabel="Viability Sheet"
          title="Viability is stale relative to the PO"
          [message]="viabStaleMessage()"
          [canResource]="canUnlockEditViability"
          [busy]="resourcing"
          [hideAction]="true">
        </app-stale-banner>

        <!-- Soft-flow approval banner. Appears once the sheet is Approved;
             edits remain allowed but they're recorded as "after approval"
             entries in the activity log. The frozen "what was signed off"
             version lives in QuotViabilityApprovalSnapshot (SF6). -->
        @if (sheet && sheet.status === 'Approved') {
          <div class="soft-flow-banner">
            <mat-icon class="banner-icon">verified</mat-icon>
            <div class="banner-text">
              <strong>This viability sheet was approved.</strong>
              You can still edit it — any changes are recorded in the
              activity log as post-approval edits. The version signed
              off at approval is preserved in the approval-snapshot
              history.
            </div>
          </div>
        }

        <!-- TP-Cost sourcing toggle (Viability TP-Cost CR).
             Two modes: rate effective on a user-picked date, or rate
             effective on the parent quotation's approval date. Bulk-
             refresh runs immediately on flip; a confirm dialog
             interrupts if any line has a manual TPWGST edit. Under
             soft flow the toggle stays enabled post-approval — the
             refresh just produces a journaled post-approval edit. -->
        @if (sheet) {
          <div class="tp-cost-strip">
            <div class="tp-left">
              <mat-icon class="tp-icon">payments</mat-icon>
              <span class="tp-label">TP Cost source</span>
              <mat-button-toggle-group
                [value]="tpCostMode"
                (change)="onTpCostModeChange($event.value)"
                [disabled]="refreshingTp"
                class="tp-toggle">
                <mat-button-toggle value="as_of_date"
                                   matTooltip="Use rate from the master effective on the selected date">
                  <mat-icon>event</mat-icon>
                  Selected Datewise
                </mat-button-toggle>
                <mat-button-toggle value="po_working_sheet"
                                   [matTooltip]="hasPoWorkingSheet
                                     ? 'Use the TPWGST that was frozen on the Final Working Sheet when the PO was captured'
                                     : 'No PO Final Working Sheet exists for this quotation yet'"
                                   [disabled]="!hasPoWorkingSheet">
                  <mat-icon>inventory_2</mat-icon>
                  LTP on WS @PO
                </mat-button-toggle>
              </mat-button-toggle-group>

              @if (tpCostMode === 'as_of_date') {
                <mat-form-field appearance="outline" class="tp-date">
                  <mat-label>As-of date</mat-label>
                  <input matInput [matDatepicker]="tpDatePicker"
                         [value]="tpCostAsOfDate"
                         (dateChange)="onTpCostDateChange($event.value)"
                         [disabled]="refreshingTp"
                         placeholder="Today" />
                  <mat-datepicker-toggle matSuffix [for]="tpDatePicker"></mat-datepicker-toggle>
                  <mat-datepicker #tpDatePicker></mat-datepicker>
                </mat-form-field>
              } @else {
                <span class="tp-approved-hint">
                  <mat-icon class="tp-hint-ico">inventory_2</mat-icon>
                  From <strong>PO Final Working Sheet</strong>
                </span>
              }
            </div>
            <div class="tp-right">
              @if (refreshingTp) {
                <mat-spinner diameter="18"></mat-spinner>
                <span class="tp-busy">Refreshing TP Cost…</span>
              } @else if (lastRefreshSummary) {
                <span class="tp-summary" [matTooltip]="lastRefreshTooltip()">
                  <mat-icon class="ok-ico">check_circle</mat-icon>
                  Updated {{ lastRefreshSummary.updatedCount }}
                  @if (lastRefreshSummary.skippedManualCount) {
                    · skipped {{ lastRefreshSummary.skippedManualCount }} manual
                  }
                  @if (lastRefreshSummary.missingRateCount) {
                    · <span class="warn">{{ lastRefreshSummary.missingRateCount }} missing</span>
                  }
                </span>
              }
            </div>
          </div>
        }
        @if (loading) {
          <div class="viab-spinner"><mat-spinner diameter="40"></mat-spinner></div>
        } @else if (!sheet) {
          <div class="viab-empty">
            <mat-icon>query_stats</mat-icon>
            <p>No viability sheet yet for this quotation.</p>
            <button mat-raised-button color="primary" (click)="generate()" [disabled]="busy">
              <mat-icon>add</mat-icon> Generate Viability Sheet
            </button>
          </div>
        } @else {
          <!-- Working Sheet (read-only) -->
          <h3 class="viab-section-title">
            <mat-icon>description</mat-icon> Working Sheet (original, read-only)
          </h3>
          <div class="viab-table-wrap">
            <table class="viab-table">
              <thead>
                <tr>
                  @for (c of visibleWorkingCols(); track c.key) {
                    <th [style.min-width]="c.width"
                        [class.neg]="c.neg"
                        [class.deducted]="c.deducted"
                        [class.totrate]="c.key === 'totRate'">
                      {{ c.label }}
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of workingSheet; track row.quotDtlId; let i = $index) {
                  <tr>
                    @for (c of visibleWorkingCols(); track c.key) {
                      <td [class.num]="c.num"
                          [class.neg]="c.neg"
                          [class.deducted]="c.deducted"
                          [class.totrate]="c.key === 'totRate'">
                        {{ displayValue(row, c, i + 1) }}
                      </td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Viability Sheet (editable) -->
          <h3 class="viab-section-title viab-section-edit">
            <mat-icon>tune</mat-icon> Viability Sheet (adjusted)
            <span class="viab-section-hint">
              Tune cost heads directly or use Goal Seek per row · Total Rs/MT is computed · dia change refreshes TPWGST
            </span>
          </h3>
          <div class="viab-table-wrap">
            <table class="viab-table viab-table-edit">
              <thead>
                <tr>
                  @for (c of visibleViabilityCols(); track c.key) {
                    <th [style.min-width]="c.width"
                        [class.neg]="c.neg"
                        [class.deducted]="c.deducted"
                        [class.gross]="isGross(c.key)"
                        [class.totrate]="c.key === 'totRate'"
                        [class.sticky-dia]="c.key === 'itemDia'"
                        [class.sticky-total]="c.key === 'totRate'">
                      {{ c.label }}
                    </th>
                  }
                  <th style="min-width:56px">⚙</th>
                </tr>
              </thead>
              <tbody>
                @for (row of sheet.lines; track row.viabilityLineId; let i = $index) {
                  <tr [class.missing-rate]="missingRateLineIds.has(row.viabilityLineId)">
                    @for (c of visibleViabilityCols(); track c.key) {
                      <td [class.num]="c.num" [class.neg]="c.neg"
                          [class.deducted]="c.deducted"
                          [class.gross]="isGross(c.key)"
                          [class.totrate]="c.key === 'totRate'"
                          [class.sticky-dia]="c.key === 'itemDia'"
                          [class.sticky-total]="c.key === 'totRate'"
                          [class.editable]="!readOnly && isEditable(c.key)"
                          [class.has-select]="!readOnly && isDropdownKey(c.key)">
                        @if (!readOnly && isEditable(c.key)) {
                          @switch (c.key) {
                            @case ('itemName') {
                              <mat-select class="inline-select"
                                [ngModel]="row.itemName"
                                (openedChange)="onDropdownOpen($event, 'item')"
                                (selectionChange)="onCellChange(row, 'itemName', $event.value)"
                                panelClass="searchable-panel" [disabled]="busy">
                                <div class="select-search" (click)="$event.stopPropagation()">
                                  <mat-icon class="search-ico">search</mat-icon>
                                  <input placeholder="Search items..." [value]="search.item"
                                    (input)="search.item = $any($event.target).value"
                                    (keydown)="$event.stopPropagation()">
                                </div>
                                @for (it of filteredItems(); track it.itemId) {
                                  <mat-option [value]="it.itemName">{{ it.itemName }}</mat-option>
                                }
                              </mat-select>
                            }
                            @case ('itemGradeName') {
                              <mat-select class="inline-select"
                                [ngModel]="row.itemGradeName"
                                (openedChange)="onDropdownOpen($event, 'grade')"
                                (selectionChange)="onCellChange(row, 'itemGradeName', $event.value)"
                                panelClass="searchable-panel" [disabled]="busy">
                                <div class="select-search" (click)="$event.stopPropagation()">
                                  <mat-icon class="search-ico">search</mat-icon>
                                  <input placeholder="Search grades..." [value]="search.grade"
                                    (input)="search.grade = $any($event.target).value"
                                    (keydown)="$event.stopPropagation()">
                                </div>
                                @for (g of filteredGrades(); track g.itemGradeId) {
                                  <mat-option [value]="g.itemGradeName">{{ g.itemGradeName }}</mat-option>
                                }
                              </mat-select>
                            }
                            @case ('itemDia') {
                              <mat-select class="inline-select"
                                [ngModel]="row.itemDia"
                                (openedChange)="onDropdownOpen($event, 'dia')"
                                (selectionChange)="onCellChange(row, 'itemDia', $event.value)"
                                panelClass="searchable-panel" [disabled]="busy">
                                <div class="select-search" (click)="$event.stopPropagation()">
                                  <mat-icon class="search-ico">search</mat-icon>
                                  <input placeholder="Search dia..." [value]="search.dia"
                                    (input)="search.dia = $any($event.target).value"
                                    (keydown)="$event.stopPropagation()">
                                </div>
                                @for (d of filteredDias(); track d.diaid) {
                                  <mat-option [value]="d.diadescription">{{ d.diadescription }}</mat-option>
                                }
                              </mat-select>
                            }
                            @case ('itemLength') {
                              <mat-select class="inline-select"
                                [ngModel]="row.itemLength"
                                (openedChange)="onDropdownOpen($event, 'length')"
                                (selectionChange)="onCellChange(row, 'itemLength', $event.value)"
                                panelClass="searchable-panel" [disabled]="busy">
                                <div class="select-search" (click)="$event.stopPropagation()">
                                  <mat-icon class="search-ico">search</mat-icon>
                                  <input placeholder="Search lengths..." [value]="search.length"
                                    (input)="search.length = $any($event.target).value"
                                    (keydown)="$event.stopPropagation()">
                                </div>
                                @for (l of filteredLengths(); track l.itemLengthId) {
                                  <mat-option [value]="l.itemLength">{{ l.itemLength }}</mat-option>
                                }
                              </mat-select>
                            }
                            @default {
                              <input
                                [type]="c.num ? 'number' : 'text'"
                                step="0.01"
                                [ngModel]="row[c.key]"
                                (change)="onCellChange(row, c.key, $any($event.target).value)"
                                [disabled]="busy" />
                            }
                          }
                        } @else {
                          {{ displayValue(row, c, i + 1) }}
                        }
                      </td>
                    }
                    <td class="viab-actions-cell">
                      <button mat-icon-button color="primary"
                        (click)="openGoalSeek(row)"
                        [disabled]="readOnly || busy"
                        matTooltip="Goal Seek: hit a target Total Rs/MT">
                        <mat-icon>track_changes</mat-icon>
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Price Reduction Summary (working vs viability) -->
          <!-- Positive "Reduction / MT" = price was lowered to win the PO.     -->
          <!-- It's margin the company is giving up — not a saving — so we     -->
          <!-- present it neutrally, not with good/bad colour coding.          -->
          <h3 class="viab-section-title viab-section-reduction">
            <mat-icon>trending_down</mat-icon> Price Reduction Summary
            <span class="viab-section-hint">
              Rate reduction applied to win the PO · per MT × ordered qty · dia-changed lines excluded
            </span>
          </h3>
          <div class="viab-table-wrap">
            <table class="viab-table viab-reduction">
              <thead>
                <tr>
                  <th style="min-width:44px">#</th>
                  <th style="min-width:150px">Item</th>
                  <th style="min-width:100px">Dia</th>
                  <th style="min-width:120px">Working (Rs/MT)</th>
                  <th style="min-width:120px">Viability (Rs/MT)</th>
                  <th style="min-width:120px">Reduction / MT</th>
                  <th style="min-width:110px">Ordered Qty</th>
                  <th style="min-width:150px">Total Reduction</th>
                </tr>
              </thead>
              <tbody>
                @for (s of savingsRows(); track s.lineId; let i = $index) {
                  <tr [class.excluded]="s.excluded">
                    <td>{{ i + 1 }}</td>
                    <td class="left">{{ s.itemName }}</td>
                    <td>{{ s.diaLabel }}</td>
                    <td class="num">{{ s.workingRate | number:'1.2-2' }}</td>
                    <td class="num">{{ s.viabRate | number:'1.2-2' }}</td>
                    <td class="num">
                      @if (s.excluded) {
                        <span class="excluded-tag">Dia changed</span>
                      } @else {
                        {{ s.savingPerMt | number:'1.2-2' }}
                      }
                    </td>
                    <td class="num">{{ s.orderedQty | number:'1.2-2' }}</td>
                    <td class="num total">
                      {{ s.excluded ? '—' : (s.totalSaving | number:'1.2-2') }}
                    </td>
                  </tr>
                }
              </tbody>
              <tfoot>
                <tr class="grand-row">
                  <td colspan="7" class="left">
                    <strong>Total Price Reduction</strong>
                    @if (excludedCount() > 0) {
                      <span class="excluded-note">
                        · {{ excludedCount() }} line{{ excludedCount() > 1 ? 's' : '' }} excluded (dia changed)
                      </span>
                    }
                  </td>
                  <td class="num total">
                    <strong>{{ grandSaving() | number:'1.2-2' }}</strong>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    /* Card chrome (head strip, status chip, action cluster) is shared
       across all four lifecycle stage cards via the stage-card classes
       in styles.scss. Only the viability-specific bits live here. */
    .viab-tool-btn { width: 36px; height: 36px; }

    .viab-spinner { display: flex; justify-content: center; padding: 40px 0; }
    .viab-empty {
      text-align: center;
      padding: 40px 20px;
      color: var(--snm-text-muted);
    }
    .viab-empty mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.6; }

    .viab-section-title {
      display: flex; align-items: center; gap: 6px;
      margin: 18px 0 8px;
      font-size: 14px;
      font-weight: 600;
      color: var(--snm-text-primary);
    }
    .viab-section-edit { color: var(--snm-accent-dark, #3a6bb5); }
    .viab-section-hint {
      font-weight: 400;
      font-size: 12px;
      color: var(--snm-text-muted);
      margin-left: 8px;
    }

    .viab-table-wrap {
      overflow-x: auto;
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
      margin-bottom: 8px;
    }

    /* Font sizes mirror the Quotation Line Items table:
       13px data, 12px headers (uppercase label-style), 11px badges. */
    table.viab-table {
      width: 100%;
      border-collapse: collapse;
    }
    .viab-table th, .viab-table td {
      border: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
      white-space: nowrap;
      text-align: center;
    }
    .viab-table td {
      font-size: 13px;
      color: var(--snm-text-primary);
    }
    .viab-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      position: sticky; top: 0; z-index: 1;
    }
    .viab-table td.num, .viab-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
    .viab-table .neg { color: #ef5350; }
    /* CR #2 — CD + Spl. Discount: heavy red wash so the user sees these
       columns behave as deductions (positive entry → negative effect on
       totRate). Overrides .neg's lighter color. */
    .viab-table th.deducted {
      background: rgba(229, 57, 53, 0.18) !important;
      color: #c62828 !important;
    }
    .viab-table td.deducted {
      background: rgba(229, 57, 53, 0.08);
      color: #c62828 !important;
      font-weight: 500;
    }
    .viab-table td.deducted input {
      color: #c62828 !important;
      font-weight: 600;
    }
    .viab-table .gross { background: rgba(255, 242, 204, 0.35); }

    /* Soft-flow approval banner (SF5). Appears when sheet.status ===
       'Approved' to make it visually obvious that subsequent edits are
       being recorded as post-approval changes — replaces the old "locked
       and disabled" affordance with informed-consent UX. */
    .soft-flow-banner {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 10px 14px;
      margin-bottom: 12px;
      background: rgba(255, 220, 100, 0.18);
      border: 1px solid rgba(200, 150, 30, 0.45);
      border-left: 4px solid rgba(200, 150, 30, 0.85);
      border-radius: 6px;
      color: var(--snm-text-primary);
      font-size: 13px;
      line-height: 1.5;
    }
    .soft-flow-banner .banner-icon {
      color: rgba(200, 150, 30, 1);
      margin-top: 1px;
      flex: 0 0 auto;
    }
    .soft-flow-banner .banner-text strong { display: block; }

    /* TP-Cost sourcing strip (Viability TP-Cost CR). Sits above the
       working-sheet table and stays visible while scrolling. */
    .tp-cost-strip {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      margin-bottom: 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      flex-wrap: wrap;
    }
    .tp-cost-strip.tp-locked { opacity: 0.85; }
    .tp-left, .tp-right {
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    }
    .tp-icon { color: var(--snm-accent); }
    .tp-label {
      font-weight: 600; font-size: 13px; color: var(--snm-text-primary);
    }
    .tp-toggle ::ng-deep .mat-button-toggle {
      font-size: 12px;
    }
    .tp-toggle ::ng-deep .mat-button-toggle mat-icon {
      font-size: 16px; width: 16px; height: 16px;
      vertical-align: middle; margin-right: 4px;
    }
    .tp-date { width: 200px; margin-top: 4px; }
    .tp-date ::ng-deep .mat-mdc-form-field-infix {
      padding-top: 6px !important; padding-bottom: 6px !important;
      min-height: 32px;
    }
    .tp-approved-hint {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px;
      color: var(--snm-text-secondary);
      padding: 4px 10px;
      background: var(--snm-accent-subtle);
      border-radius: 4px;
    }
    .tp-hint-ico {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--snm-accent);
    }
    .tp-busy {
      font-size: 12px; color: var(--snm-text-secondary);
    }
    .tp-summary {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px; color: var(--snm-text-secondary);
      padding: 4px 10px;
      background: var(--snm-bg-card);
      border-radius: 4px;
    }
    .tp-summary .ok-ico {
      color: #2e7d32; font-size: 16px; width: 16px; height: 16px;
    }
    .tp-summary .warn { color: #c62828; font-weight: 600; }
    /* Missing-rate row highlight — applied to the viability table row
       when the line's viabilityLineId is in missingRateLineIds. */
    .viab-table tr.missing-rate td {
      background: rgba(229, 57, 53, 0.05) !important;
    }
    .viab-table tr.missing-rate td.totrate { background: rgba(229, 57, 53, 0.10) !important; }
    .missing-chip {
      display: inline-flex; align-items: center; gap: 2px;
      margin-left: 4px;
      padding: 1px 6px;
      background: rgba(229, 57, 53, 0.12);
      color: #c62828;
      border-radius: 10px;
      font-size: 10px;
      font-weight: 600;
    }
    .missing-chip mat-icon {
      font-size: 12px; width: 12px; height: 12px;
    }

    /* Total Rs/MT — static / computed, never directly editable.
       Opaque band makes it read as a result column, not a tuning knob. */
    .viab-table th.totrate {
      background: var(--snm-accent-subtle) !important;
      color: var(--snm-accent-dark);
      font-weight: 700;
      letter-spacing: 0.2px;
    }
    .viab-table td.totrate {
      background: var(--snm-accent-subtle);
      color: var(--snm-accent-dark);
      font-weight: 600;
    }

    /* ---- Sticky columns in the viability (editable) table only ----
       Dia stays anchored at the left edge, Total Rs/MT at the right edge,
       so the identity and the live result are always visible while the
       user scrolls through the cost heads in between.
       Backgrounds use theme-aware CSS vars (see --snm-sticky-bg /
       --snm-sticky-accent-bg in styles.scss) and are fully opaque so
       scrolling content never bleeds through. */
    .viab-table-edit th.sticky-dia,
    .viab-table-edit td.sticky-dia {
      position: sticky;
      left: 0;
      z-index: 2;
      min-width: 80px; max-width: 80px; width: 80px;
      background-color: var(--snm-sticky-bg) !important;
      color: var(--snm-text-primary);
      box-shadow: 4px 0 6px -3px rgba(0, 0, 0, 0.12),
                  inset -1px 0 0 var(--snm-border-divider);
    }
    .viab-table-edit th.sticky-total,
    .viab-table-edit td.sticky-total {
      position: sticky;
      right: 0;
      z-index: 2;
      min-width: 120px; max-width: 120px; width: 120px;
      background-color: var(--snm-sticky-accent-bg) !important;
      color: var(--snm-accent-dark);
      font-weight: 600;
      /* Shadow casts leftward so it separates from scrolling content */
      box-shadow: -4px 0 6px -3px rgba(0, 0, 0, 0.12),
                  inset 1px 0 0 var(--snm-border-divider);
    }
    /* Headers must sit above body cells when both are sticky */
    .viab-table-edit thead th.sticky-dia,
    .viab-table-edit thead th.sticky-total {
      z-index: 3;
    }
    .viab-table-edit td.editable {
      background: rgba(91,143,217,0.04);
      padding: 2px 4px;
    }
    .viab-table-edit input {
      border: none;
      background: transparent;
      width: 100%;
      color: inherit;
      /* Force 13px so edit vs display heights line up with the data cell size */
      font-family: inherit;
      font-size: 13px;
      text-align: inherit;
      padding: 4px 6px;
      outline: none;
    }
    .viab-table-edit input:focus {
      background: rgba(91,143,217,0.15);
      outline: 1px solid var(--snm-accent);
    }

    /* Inline mat-select for Item / Grade / Dia / Length in edit cells. */
    .viab-table-edit td.has-select {
      padding: 2px 6px;
    }
    .viab-table-edit .inline-select {
      width: 100%;
      font: inherit;
      color: inherit;
      background: rgba(91,143,217,0.04);
      border-radius: 4px;
      padding: 4px 6px;
      cursor: pointer;
    }
    .viab-table-edit .inline-select:hover {
      background: rgba(91,143,217,0.12);
    }
    .viab-table-edit .inline-select.mat-mdc-select {
      --mat-select-trigger-text-font: inherit;
      /* Match data-cell font-size so dropdown values line up with other cells */
      --mat-select-trigger-text-size: 13px;
    }
    .viab-actions-cell { padding: 0 !important; }
    .viab-actions-cell button { width: 32px; height: 32px; line-height: 32px; }
    .viab-actions-cell mat-icon { font-size: 18px; width: 18px; height: 18px; }

    /* Price reduction summary — neutral tone; the reduction is a cost to
       the company, not a saving, so we avoid good/bad colour semantics. */
    .viab-section-reduction { color: var(--snm-accent-dark, #3a6bb5); }
    .viab-reduction td.left { text-align: left; }
    .viab-reduction td.total {
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .viab-reduction tr.excluded td { opacity: 0.65; }
    .viab-reduction .excluded-tag {
      display: inline-block;
      padding: 1px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 600;
      color: #8d6e00;
      background: rgba(255,213,79,0.18);
      border: 1px solid rgba(141,110,0,0.25);
    }
    .viab-reduction .excluded-note {
      font-weight: 400;
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-left: 6px;
    }
    .viab-reduction tr.grand-row td {
      background: var(--snm-accent-subtle);
      border-top: 2px solid var(--snm-accent);
      padding-top: 10px;
      padding-bottom: 10px;
      color: var(--snm-accent-dark);
    }
  `],
})
export class QuotationViabilityComponent implements OnChanges {
  @Input({ required: true }) quotId!: number;
  @Input() canApprove = false;
  /** Gates the Re-generate button. Falls back to ``canApprove`` for
   *  legacy roles that don't yet have the dedicated
   *  ``CanRegenerateViability`` flag. */
  @Input() canRegenerate = false;
  @Input() readOnly = false;
  // Phase 1 Unlock-and-Edit flag for the Viability stage. Resolved
  // from the menu service in the constructor (privileged users only).
  canUnlockEditViability = false;
  /** Feature flag — hides the in-place Unlock & Edit button regardless
   *  of permission. Restore / Re-source (which share the same gate) are
   *  unaffected. Flip to ``false`` to re-enable. */
  readonly unlockEditHidden = true;
  // Phase 3 — current PO head versionNo (the upstream this stage
  // sources from). Parent passes it; we compare to ``sheet.sourcedFromPOVersion``
  // to surface a stale banner when the PO has moved on.
  @Input() upstreamPoVersion: number | null = null;
  // Mirrors the form's ``resourcing`` flag for the inline spinner on
  // the Re-source button.
  @Input() resourcing = false;
  /** Fires when the user clicks Re-source on the stale banner. The
   *  parent owns the API call (single dispatcher across stages). */
  @Output() reSource = new EventEmitter<void>();

  /** Fires after a state-changing action (generate / approve) so the parent
   * quotation-form can re-sync its status, stepper, and tab locks. */
  @Output() stageChanged = new EventEmitter<void>();

  workingCols = WORKING_COLS;
  viabilityCols = VIABILITY_COLS;

  workingSheet: any[] = [];
  sheet: any | null = null;

  loading = false;
  busy = false;

  // ---- Version-switch state (soft-flow Slice H) ----
  /** Cached snapshot list for the current viability head. Refreshed on
   *  load + after every approve/switch. Drives the Switch Version
   *  button visibility and the dialog's picker. */
  snapshots: ViabilityApprovalSnapshot[] = [];
  /** Snapshot id the editor was last loaded from — highlighted as
   *  "current" in the switch dialog. */
  currentSnapshotId: number | null = null;
  /** True while a version-switch round-trip is in flight. Disables
   *  the action buttons so the user can't fire two restores in
   *  parallel. */
  switching = false;

  /** Inline-picker items derived from ``snapshots``. */
  get versionItems(): VersionInlineItem[] {
    return this.snapshots.map(s => ({
      id: s.snapshotId,
      label: `V${s.versionNo}`,
      approvedAt: s.approvedAt,
      approvedByName: s.approvedByName,
      // Upstream-source transparency. ``sourcedFromPOVersion`` carries
      // the FWS snapshot's versionNo on the soft-flow path (legacy:
      // the PO's versionNo). Render with the FWS prefix so the user
      // knows which working sheet fed this viability draft.
      sourceText:
        s.sourcedFromPOVersion != null
          ? `from FWS V${s.sourcedFromPOVersion}`
          : null,
    }));
  }

  // ---- TP-Cost sourcing toggle (Viability TP-Cost CR) ----
  /** Mode picked in the toggle group. Hydrated from sheet.tpCostMode on
   *  load; falls back to 'as_of_date' for legacy sheets. */
  tpCostMode: 'as_of_date' | 'po_working_sheet' = 'as_of_date';
  /** Date picker value when mode is 'as_of_date'. null = today. */
  tpCostAsOfDate: Date | null = null;
  /** True when this quotation's PO has a Final Working Sheet —
   *  enables the "LTP on WS @PO" toggle option. False when no PO
   *  exists yet or its FWS hasn't been populated. */
  hasPoWorkingSheet = false;
  /** Lines flagged "missing_rate" by the last refresh — rendered as
   *  warning chips. Keyed by viabilityLineId. */
  missingRateLineIds = new Set<number>();
  /** True while the refresh PUT is in flight; disables the toggle. */
  refreshingTp = false;
  /** Summary of the most recent refresh — shown next to the toggle. */
  lastRefreshSummary: {
    updatedCount: number;
    skippedManualCount: number;
    missingRateCount: number;
  } | null = null;

  // ---- Column visibility (shared between both grids) ----
  private readonly COL_PREFS_KEY = 'snm-viab-cols';
  hiddenCostHeads = new Set<string>();
  compactMode = false;
  costHeads = COST_HEADS;
  costHeadLabel = HEAD_LABEL;

  // ---- Master data for Item / Grade / Dia / Length dropdowns ----
  itemNames: ItemNameOpt[] = [];
  itemGrades: ItemGradeOpt[] = [];
  allDias: DiaOpt[] = [];
  allLengths: LengthOpt[] = [];
  search = { item: '', grade: '', dia: '', length: '' };

  isDropdownKey(key: string): boolean { return DROPDOWN_KEYS.has(key); }

  onDropdownOpen(opened: boolean, key: keyof typeof this.search): void {
    if (opened) this.search[key] = '';
  }

  filteredItems(): ItemNameOpt[] {
    const t = this.search.item.toLowerCase();
    return t ? this.itemNames.filter(i => (i.itemName || '').toLowerCase().includes(t)) : this.itemNames;
  }
  filteredGrades(): ItemGradeOpt[] {
    const t = this.search.grade.toLowerCase();
    return t ? this.itemGrades.filter(g => g.itemGradeName.toLowerCase().includes(t)) : this.itemGrades;
  }
  filteredDias(): DiaOpt[] {
    const t = this.search.dia.toLowerCase();
    return t ? this.allDias.filter(d => d.diadescription.toLowerCase().includes(t)) : this.allDias;
  }
  filteredLengths(): LengthOpt[] {
    const t = this.search.length.toLowerCase();
    return t ? this.allLengths.filter(l => l.itemLength.toLowerCase().includes(t)) : this.allLengths;
  }

  private loadMasters(): void {
    this.api.get<ItemNameOpt[]>('/masters/item-names').subscribe({
      next: d => this.itemNames = d || [],
    });
    this.api.get<ItemGradeOpt[]>('/masters/item-grades').subscribe({
      next: d => this.itemGrades = d || [],
    });
    this.api.get<DiaOpt[]>('/masters/dia-masters').subscribe({
      next: d => this.allDias = d || [],
    });
    this.api.get<LengthOpt[]>('/masters/item-lengths').subscribe({
      next: d => this.allLengths = d || [],
    });
  }

  constructor(
    private api: ApiService,
    private http: HttpClient,
    private notify: NotificationService,
    private dialog: MatDialog,
    private menuService: MenuService,
    private cycleService: CycleService,
  ) {
    this.canUnlockEditViability = this.menuService.hasPermission(
      'Quotations', 'canUnlockEditViability',
    );
    this.loadColumnPrefs();
    this.loadMasters();
  }

  ngOnChanges(c: SimpleChanges): void {
    if (c['quotId']?.currentValue) this.load();
  }

  // Column visibility applies to cost heads only; identity/total columns stay visible.
  visibleWorkingCols(): ColMeta[] {
    return this.workingCols.filter(c => this.isColVisible(c.key, this.workingSheet));
  }

  visibleViabilityCols(): ColMeta[] {
    return this.viabilityCols.filter(c => this.isColVisible(c.key, this.sheet?.lines || []));
  }

  private isColVisible(key: string, rows: any[]): boolean {
    if (!COST_HEADS.includes(key)) return true; // only cost heads are hideable
    if (this.hiddenCostHeads.has(key)) return false;
    if (this.compactMode) {
      if (!rows || rows.length === 0) return true;
      return rows.some(r => {
        const v = r[key];
        return v != null && Number(v) !== 0;
      });
    }
    return true;
  }

  toggleCompactMode(): void {
    this.compactMode = !this.compactMode;
    this.saveColumnPrefs();
  }

  toggleCostHead(key: string, visible: boolean): void {
    if (visible) this.hiddenCostHeads.delete(key);
    else this.hiddenCostHeads.add(key);
    this.saveColumnPrefs();
  }

  showAllHeads(): void {
    this.hiddenCostHeads.clear();
    this.compactMode = false;
    this.saveColumnPrefs();
  }

  get hiddenHeadCount(): number {
    return this.hiddenCostHeads.size;
  }

  private loadColumnPrefs(): void {
    try {
      const raw = localStorage.getItem(this.COL_PREFS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed?.hidden)) this.hiddenCostHeads = new Set(parsed.hidden);
      if (typeof parsed?.compact === 'boolean') this.compactMode = parsed.compact;
    } catch { /* ignore */ }
  }

  private saveColumnPrefs(): void {
    try {
      localStorage.setItem(this.COL_PREFS_KEY, JSON.stringify({
        hidden: Array.from(this.hiddenCostHeads),
        compact: this.compactMode,
      }));
    } catch { /* ignore */ }
  }

  // ---- Savings comparison (working vs viability) ----
  /**
   * Per-line savings strip rendered below the two tables.
   *   savingPerMt  = workingRate − viabilityRate   (positive = cost reduced)
   *   totalSaving  = savingPerMt × orderedQty
   * Lines whose dia was changed during viability are flagged `excluded = true`
   * and their totalSaving is omitted from the grand total — the comparison
   * isn't apples-to-apples once the dia differs (different raw material rate).
   */
  savingsRows(): SavingsRow[] {
    if (!this.sheet) return [];
    const map = new Map<number, any>();
    for (const w of this.workingSheet) map.set(w.quotDtlId, w);

    return (this.sheet.lines || []).map((line: any) => {
      const src = line.sourceQuotDtlId ? map.get(line.sourceQuotDtlId) : null;
      const workingDia = src?.itemDia ?? null;
      const currentDia = line.itemDia ?? null;
      const diaChanged = !!workingDia && workingDia !== currentDia;
      const workingRate = Number(src?.totRate ?? 0);
      const viabRate = Number(line.totRate ?? 0);
      const orderedQty = Number(line.orderedQty ?? 0);
      const savingPerMt = workingRate - viabRate;
      return {
        lineId: line.viabilityLineId,
        itemName: line.itemName || '-',
        diaLabel: diaChanged ? `${workingDia} → ${currentDia}` : (currentDia || '-'),
        workingRate,
        viabRate,
        savingPerMt,
        orderedQty,
        totalSaving: diaChanged ? 0 : savingPerMt * orderedQty,
        excluded: diaChanged,
      };
    });
  }

  grandSaving(): number {
    return this.savingsRows()
      .filter(r => !r.excluded)
      .reduce((s, r) => s + r.totalSaving, 0);
  }

  excludedCount(): number {
    return this.savingsRows().filter(r => r.excluded).length;
  }

  isEditable(key: string): boolean {
    return EDITABLE_IN_VIABILITY.has(key);
  }

  isGross(key: string): boolean {
    return key === 'orderedQty' || key === 'totalAmount'
        || key === 'totalGst' || key === 'grossExForPrice';
  }

  displayValue(row: any, col: ColMeta, sno: number): any {
    if (col.key === '_sno') return sno;
    if (col.key === '_gst') {
      const t = Number(row.totRate || 0);
      return t ? (t * 0.18).toFixed(2) : '';
    }
    const v = row[col.key];
    if (v == null || v === '') return '';
    if (col.num) {
      const n = Number(v);
      return isFinite(n) ? n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v;
    }
    return v;
  }

  load(): void {
    if (!this.quotId) return;
    this.loading = true;
    this.api.get<any>(`/quotations/${this.quotId}/viability`).subscribe({
      next: (res) => {
        this.loading = false;
        this.workingSheet = res.workingSheet || [];
        this.sheet = res.viability || null;
        this.hasPoWorkingSheet = !!res.hasPoWorkingSheet;
        this.hydrateTpCostState();
        this.refreshSnapshotList();
      },
      error: (e) => {
        this.loading = false;
        this.notify.error(e?.error?.detail || 'Failed to load viability sheet.');
      },
    });
  }

  /** Re-fetch the approval snapshot list for the current viability
   *  head. Used after load, approve, regenerate, and switch so the
   *  picker stays in sync with the backend. */
  private refreshSnapshotList(): void {
    if (!this.sheet?.viabilityId) {
      this.snapshots = [];
      this.currentSnapshotId = null;
      return;
    }
    this.cycleService.listViabilitySnapshots(this.sheet.viabilityId).subscribe({
      next: (res) => {
        this.snapshots = res?.items || [];
        if (this.currentSnapshotId == null && this.snapshots.length > 0) {
          this.currentSnapshotId = this.snapshots[0].snapshotId;
        }
      },
      error: () => { this.snapshots = []; },
    });
  }

  /** Internal: POST to the generate endpoint with an optional source.
   *  Both first-time generate and re-generate funnel through this so
   *  the success/failure handling stays in one place. */
  private postGenerate(
    sourcedFromFWSSnapshotId: number | null,
    sourcedFromViabilitySnapshotId: number | null = null,
  ): void {
    if (!this.quotId) return;
    this.busy = true;
    const body: Record<string, number> = {};
    if (sourcedFromFWSSnapshotId != null) {
      body['sourcedFromFWSSnapshotId'] = sourcedFromFWSSnapshotId;
    }
    if (sourcedFromViabilitySnapshotId != null) {
      body['sourcedFromViabilitySnapshotId'] = sourcedFromViabilitySnapshotId;
    }
    this.api.post<any>(`/quotations/${this.quotId}/viability`, body).subscribe({
      next: (res) => {
        this.busy = false;
        this.workingSheet = res.workingSheet || [];
        this.sheet = res.viability || null;
        this.hasPoWorkingSheet = !!res.hasPoWorkingSheet;
        this.hydrateTpCostState();
        // New head id → reset the "currently loaded" pointer so the
        // version picker doesn't try to highlight a stale snapshot id.
        this.currentSnapshotId = null;
        this.refreshSnapshotList();
        this.notify.success('Viability sheet generated.');
        this.stageChanged.emit();
      },
      error: (e) => {
        this.busy = false;
        this.notify.error(e?.error?.detail || 'Failed to generate viability sheet.');
      },
    });
  }

  generate(): void {
    // First-time generate: no source picker (no FWS snapshots are
    // likely to exist yet on a quotation that's never had a viability
    // sheet). Backend defaults to live FWS — which is the right
    // behaviour for this path.
    this.postGenerate(null);
  }

  /** Re-generate — opens the source picker dialog so the user can
   *  choose which version (FWS snapshot OR past Viability snapshot)
   *  drives the new viability. Replaces the older confirm-dialog
   *  flow. The picker dialog contains its own affirmation, so no
   *  separate ConfirmDialog is needed. */
  regenerate(): void {
    if (!this.sheet) return;
    const cycleId = (this.sheet as any).quotOrderCycleId as number | undefined;
    if (!cycleId) {
      // Fallback to the legacy confirm-then-generate flow if the
      // sheet predates the cycle model (no cycleId stamped).
      this.legacyRegenerateConfirm();
      return;
    }
    import('./generate-viability-dialog.component').then(({ GenerateViabilityDialogComponent }) => {
      const ref = this.dialog.open(GenerateViabilityDialogComponent, {
        data: {
          quotId: this.quotId,
          cycleId,
          cycleNo: (this.sheet as any).cycleNo ?? 1,
          // Phase B: pass the current viability head id so the dialog
          // can also offer past Viability snapshots as a source.
          viabilityId: this.sheet.viabilityId,
        },
        width: '560px',
      });
      ref.afterClosed().subscribe((result) => {
        if (!result) return;
        this.postGenerate(
          result.sourcedFromFWSSnapshotId,
          result.sourcedFromViabilitySnapshotId,
        );
      });
    });
  }

  private legacyRegenerateConfirm(): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Re-generate viability?',
        message:
          'This archives the current Approved version and creates a fresh ' +
          'Draft v+1 carrying every line forward (including your goal-seek ' +
          'and TP-cost edits). The archived version stays reachable via ' +
          'the version dropdown. Continue?',
        confirmText: 'Re-generate',
        confirmColor: 'primary',
        cancelText: 'Cancel',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.generate();
    });
  }

  /** Pull tpCostMode + tpCostAsOfDate from the freshly-loaded sheet so
   *  the toggle binding reflects what's persisted. Falls back to
   *  'as_of_date' for legacy sheets where the columns are NULL.
   *  Tolerates the pre-rename 'approved_date' string too, mapping it
   *  to 'po_working_sheet' (defence against a stale dev row that
   *  didn't get hit by the rename migration). */
  private hydrateTpCostState(): void {
    if (!this.sheet) return;
    const raw = this.sheet.tpCostMode;
    this.tpCostMode = (raw === 'po_working_sheet' || raw === 'approved_date')
      ? 'po_working_sheet'
      : 'as_of_date';
    const dateRaw = this.sheet.tpCostAsOfDate;
    this.tpCostAsOfDate = dateRaw ? new Date(dateRaw) : null;
    this.missingRateLineIds.clear();
    this.lastRefreshSummary = null;
  }

  onCellChange(row: any, key: string, raw: any): void {
    if (!this.sheet) return;

    // Intercept the special "Specified Length" master entry: open a small
    // text prompt to capture the actual length, then save the typed value
    // (and optionally promote it to the Item Lengths master).
    if (key === 'itemLength' && typeof raw === 'string' && /specif/i.test(raw)) {
      this.openSpecifiedLengthPrompt(row);
      return;
    }

    // CR #1 — when a cost-head value changes, gate the persist behind
    // the bulk-apply modal. Header/identity fields (item, grade, dia,
    // length, orderedQty) skip the modal — those aren't propagatable.
    if (COST_HEADS.includes(key)) {
      const parsed = raw === '' ? null : Number(raw);
      const prev = row[key];
      if (this.valuesEqual(parsed, prev)) return;
      this.promptBulkApply(row, key, prev, parsed);
      return;
    }

    this.persistCellChange(row, key, raw);
  }

  /** Numeric equality tolerant to null/0 confusion. */
  private valuesEqual(a: any, b: any): boolean {
    if (a == null && b == null) return true;
    if (a == null || b == null) return a === b;
    return Number(a) === Number(b);
  }

  /** CR #1 — Show the bulk-apply confirmation modal. If the user
   *  confirms, persist the source row's change first, then fan-out
   *  PUTs to the propagation targets. If cancelled, revert local. */
  private promptBulkApply(row: any, key: string, prev: any, newVal: any): void {
    if (!this.sheet) return;
    const sheet = this.sheet;
    const otherRows = sheet.lines.filter((r: any) => r.viabilityLineId !== row.viabilityLineId);
    const data: BulkApplyDialogData = {
      fieldLabel: HEAD_LABEL[key] || key,
      oldValue: prev,
      newValue: newVal,
      sourceRowLabel: this.rowSummary(row),
      candidateRows: otherRows.map((r: any): BulkApplyCandidateRow => ({
        id: r.viabilityLineId,
        label: this.rowSummary(r),
        currentValue: r[key] ?? null,
      })),
    };
    const ref = this.dialog.open<
      BulkApplyDialogComponent, BulkApplyDialogData, BulkApplyDialogResult
    >(BulkApplyDialogComponent, { width: '640px', data });

    ref.afterClosed().subscribe(result => {
      if (!result || !result.confirmed) {
        // Cancelled — revert the local ngModel so the input snaps back.
        row[key] = prev;
        return;
      }
      // Persist the source row's edit first; if that succeeds, fan-out
      // the propagation targets. Errors on the fan-out are reported
      // per-row but don't roll back the source.
      this.persistCellChange(row, key, newVal, () => {
        this.fanOutBulkApply(sheet.viabilityId, result.applyToRowIds, key, newVal);
      });
    });
  }

  /** One-line summary for the dialog's row list and source-row preface. */
  private rowSummary(row: any): string {
    const parts = [
      row.itemName,
      row.itemGradeName,
      row.itemDia ? `Ø ${row.itemDia}` : '',
      row.itemLength,
      row.orderedQty != null ? `${row.orderedQty} MT` : '',
    ].filter(Boolean);
    return parts.join(' · ');
  }

  /** Apply the bulk change to N other rows. Each PUT is fire-and-forget
   *  here; the server is the source of truth and the response patches
   *  the local row on success. */
  private fanOutBulkApply(
    viabilityId: number,
    targetRowIds: (number | string)[],
    key: string,
    value: any,
  ): void {
    if (!this.sheet || !targetRowIds.length) return;
    const rowsById = new Map<number | string, any>();
    for (const r of this.sheet.lines) rowsById.set(r.viabilityLineId, r);

    let ok = 0;
    let failed = 0;
    const finish = () => {
      if (ok + failed === targetRowIds.length) {
        if (failed === 0) {
          this.notify.success(`Applied to ${ok} additional line${ok === 1 ? '' : 's'}.`);
        } else {
          this.notify.error(`Applied to ${ok}; ${failed} failed.`);
        }
      }
    };

    for (const id of targetRowIds) {
      const row = rowsById.get(id);
      if (!row) { failed++; finish(); continue; }
      const prev = row[key];
      row[key] = value;  // optimistic
      this.api.put<any>(
        `/viability/${viabilityId}/lines/${row.viabilityLineId}`,
        { [key]: value },
      ).subscribe({
        next: (updated) => { Object.assign(row, updated); ok++; finish(); },
        error: () => { row[key] = prev; failed++; finish(); },
      });
    }
  }

  /** Common save path used by the normal cell-change flow and by the
   *  Specified-Length prompt after the user types a value. */
  private persistCellChange(row: any, key: string, raw: any, after?: () => void): void {
    if (!this.sheet) return;
    const parsed = (WORKING_COLS.find(c => c.key === key)?.num)
      ? (raw === '' ? null : Number(raw))
      : raw;
    // Optimistically patch local row so the UI doesn't flicker while waiting.
    const prev = row[key];
    row[key] = parsed;

    this.busy = true;
    const body: any = { [key]: parsed };
    this.api.put<any>(`/viability/${this.sheet.viabilityId}/lines/${row.viabilityLineId}`, body).subscribe({
      next: (updated) => {
        this.busy = false;
        Object.assign(row, updated);
        after?.();
      },
      error: (e) => {
        this.busy = false;
        row[key] = prev;
        this.notify.error(e?.error?.detail || 'Failed to update line.');
      },
    });
  }

  /** Opens a small dialog to capture the typed Specified Length, persists
   *  it to the line, then optionally adds it to the Item Lengths master. */
  private openSpecifiedLengthPrompt(row: any): void {
    const data: TextPromptDialogData = {
      title: 'Specify Length',
      label: 'Length value',
      placeholder: 'e.g. 7.85 MTRS',
      hint: 'Type the actual length. You\'ll be asked whether to save it for reuse.',
      confirmText: 'Apply',
    };
    const ref = this.dialog.open<TextPromptDialogComponent, TextPromptDialogData, string | null>(
      TextPromptDialogComponent,
      { width: '420px', data },
    );
    ref.afterClosed().subscribe(typed => {
      if (!typed) return; // cancelled — leave the existing value untouched
      this.persistCellChange(row, 'itemLength', typed, () => {
        this.maybePromptSaveLengthToMaster(typed, row);
      });
    });
  }

  /** Asks whether to add the typed length to the Item Lengths master so
   *  it shows up in the dropdown next time. Skipped if the value already
   *  exists for the line's item or no itemid is associated with the row. */
  private maybePromptSaveLengthToMaster(typed: string, row: any): void {
    const itemId = row?.itemid;
    if (!itemId) return;
    const exists = this.allLengths.some(
      l => (l.itemLength || '').trim().toLowerCase() === typed.toLowerCase()
        && l.itemId === itemId,
    );
    if (exists) return;

    const ref = this.dialog.open(ConfirmDialogComponent, {
      width: '420px',
      data: {
        title: 'Save length for reuse?',
        message: `Add "${typed}" to the Item Lengths master so you can pick it next time?`,
        confirmText: 'Save to Master',
        cancelText: 'Skip',
        confirmColor: 'primary',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.api.post('/masters/item-lengths', {
        itemId, itemLength: typed,
      }).subscribe({
        next: (created: any) => {
          this.allLengths = [...this.allLengths, created];
          this.notify.success(`"${typed}" added to Item Lengths master.`);
        },
        error: () => this.notify.error('Failed to add to master.'),
      });
    });
  }

  openGoalSeek(row: any): void {
    const ref = this.dialog.open<GoalSeekDialogComponent, GoalSeekDialogData, GoalSeekDialogResult>(
      GoalSeekDialogComponent,
      { data: { line: row }, width: '560px' },
    );
    ref.afterClosed().subscribe(result => {
      if (!result || !this.sheet) return;
      this.busy = true;
      this.api.post<any>(
        `/viability/${this.sheet.viabilityId}/lines/${row.viabilityLineId}/goal-seek`,
        result,
      ).subscribe({
        next: (updated) => {
          this.busy = false;
          Object.assign(row, updated);
          this.notify.success(`Goal seek applied — Total Rs/MT = ${Number(updated.totRate || 0).toFixed(2)}`);
        },
        error: (e) => {
          this.busy = false;
          this.notify.error(e?.error?.detail || 'Goal seek failed.');
        },
      });
    });
  }

  approve(): void {
    if (!this.sheet) return;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Approve Viability Sheet',
        message: 'Once approved, the viability sheet becomes read-only. Continue?',
        confirmText: 'Approve',
        confirmColor: 'primary',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok || !this.sheet) return;
      this.busy = true;
      this.api.put<any>(`/viability/${this.sheet.viabilityId}/approve`, {}).subscribe({
        next: (updated) => {
          this.busy = false;
          this.sheet = { ...this.sheet, ...updated };
          this.notify.success('Viability sheet approved.');
          this.refreshSnapshotList();
          this.stageChanged.emit();
        },
        error: (e) => {
          this.busy = false;
          this.notify.error(e?.error?.detail || 'Approval failed.');
        },
      });
    });
  }

  /** Called when the user picks a row in the inline version picker.
   *  View-only preview — opens the snapshot viewer dialog. Live
   *  editor stays untouched. To resume editing on top of a past
   *  version, use Re-generate. */
  onVersionPicked(pickedId: number): void {
    if (!this.sheet?.viabilityId) return;
    const snap = this.snapshots.find(s => s.snapshotId === pickedId);
    const label = snap ? `V${snap.versionNo}` : `Snapshot #${pickedId}`;
    const viabilityId = this.sheet.viabilityId;
    const sourceText = snap?.sourcedFromPOVersion != null
      ? `from FWS V${snap.sourcedFromPOVersion}`
      : null;
    this.dialog.open(ViabilitySnapshotViewerDialogComponent, {
      data: {
        url: `/viability/${viabilityId}/approval-snapshots/${pickedId}`,
        title: `${label} — Viability Sheet`,
        sourceText,
      },
      maxWidth: '92vw',
    });
  }

  private performVersionSwitch(pickedId: number, action: 'saveAndSwitch' | 'discardAndSwitch'): void {
    if (!this.sheet?.viabilityId) return;
    this.switching = true;
    const viabilityId = this.sheet.viabilityId;
    const doLoad = () => {
      this.cycleService.loadViabilitySnapshot(viabilityId, pickedId).subscribe({
        next: (res) => {
          this.switching = false;
          this.currentSnapshotId = pickedId;
          this.notify.success(`Loaded ${res.restoredFromLabel} into the editor.`);
          this.load();  // re-fetches the bundle + refreshes snapshot list
          this.stageChanged.emit();
        },
        error: (e) => {
          this.switching = false;
          this.notify.error(
            e?.error?.detail || e?.error?.message ||
            'Failed to load the picked version.',
          );
        },
      });
    };
    if (action === 'saveAndSwitch') {
      this.api.put<any>(`/viability/${viabilityId}/approve`, {}).subscribe({
        next: () => doLoad(),
        error: (e) => {
          this.switching = false;
          this.notify.error(
            e?.error?.detail || e?.error?.message ||
            'Failed to save current state before switching. Aborted — your edits are still in the editor.',
          );
        },
      });
    } else {
      doLoad();
    }
  }

  /** Phase 3: viability is stale when its stamped PO version is
   *  older than the current PO head's versionNo. */
  isViabilityStaleVsPo(): boolean {
    if (!this.sheet || this.upstreamPoVersion == null) return false;
    const stamp = this.sheet.sourcedFromPOVersion;
    return stamp != null && stamp < this.upstreamPoVersion;
  }

  viabStaleMessage(): string {
    const stamp = this.sheet?.sourcedFromPOVersion ?? '?';
    const head = this.upstreamPoVersion ?? '?';
    return (
      `Sourced from PO v${stamp}; current PO head is v${head}. ` +
      `Re-source to regenerate the viability sheet from the latest PO Working Sheet.`
    );
  }

  /** Privileged Unlock-and-Edit on the viability sheet. Opens the
   *  shared reason-prompt dialog; on success the audit row is
   *  written and the parent re-fetches so locked-state UI clears. */
  openUnlockDialog(): void {
    if (!this.sheet) return;
    const ref = this.dialog.open(LifecycleUnlockDialogComponent, {
      data: {
        quotationId: this.quotId,
        stage: 'viability',
        stageLabel: 'Viability',
      },
      width: '560px',
      maxWidth: '95vw',
      disableClose: true,
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.stageChanged.emit();
    });
  }

  /** CR #3 — preview modal for the viability sheet. Columns mirror the
   *  visible editable grid; rows are the live (locally mutated) lines so
   *  user-staged edits show through. Hide-blank toggle drops cost-head
   *  columns where every line is empty / zero. */
  // ---- TP-Cost toggle handlers ----

  onTpCostModeChange(mode: 'as_of_date' | 'po_working_sheet'): void {
    if (mode === this.tpCostMode) return;
    if (mode === 'po_working_sheet' && !this.hasPoWorkingSheet) {
      this.notify.error('No PO Final Working Sheet exists for this quotation yet.');
      return;
    }
    this.tpCostMode = mode;
    this.refreshTpCost();
  }

  onTpCostDateChange(value: Date | null): void {
    this.tpCostAsOfDate = value;
    this.refreshTpCost();
  }

  /** Fire the refresh endpoint. If any line's current TPWGST diverges
   *  from the rate-table value at the *previous* mode/date, show a
   *  confirm dialog listing those lines and let the user decide whether
   *  to clobber or skip. Confirmed → second call with overwriteAll=true;
   *  Cancelled → leave staged toggle as-is, no API call. */
  private refreshTpCost(): void {
    // Soft flow: removed the `sheet.status === 'Approved'` short-circuit
    // so TP-cost refresh works post-approval too. Each refresh produces
    // journaled post-approval edits the same way line edits do.
    if (!this.sheet) return;
    this.runRefreshTpCost(false).then(summary => {
      if (!summary) return;
      // First pass with overwriteAll=false. If any lines were skipped,
      // surface the confirm dialog and re-issue with overwrite=true on
      // user OK.
      if (summary.skippedManualCount > 0) {
        this.confirmAndOverwriteManualLines(summary);
      }
    });
  }

  /** Public method bound to a future "Refresh" toolbar button if needed.
   *  Currently called internally on toggle / date change. */
  private runRefreshTpCost(overwriteAll: boolean): Promise<any | null> {
    if (!this.sheet) return Promise.resolve(null);
    this.refreshingTp = true;
    const body = {
      mode: this.tpCostMode,
      asOfDate: this.tpCostAsOfDate ? this.formatDate(this.tpCostAsOfDate) : null,
      overwriteAll,
    };
    return new Promise(resolve => {
      this.api.post<any>(
        `/viability/${this.sheet.viabilityId}/refresh-tp-cost`,
        body,
      ).subscribe({
        next: (res) => {
          this.refreshingTp = false;
          // Patch the local sheet header + per-line values from the
          // server response so the grid re-renders without a re-GET.
          if (res.sheet) {
            this.sheet = { ...this.sheet, ...res.sheet };
          }
          if (Array.isArray(res.sheet?.lines)) {
            this.sheet.lines = res.sheet.lines;
          }
          // Track missing-rate lines for the warning chip render.
          this.missingRateLineIds = new Set(
            (res.perLine || [])
              .filter((p: any) => p.status === 'missing_rate')
              .map((p: any) => p.viabilityLineId),
          );
          this.lastRefreshSummary = {
            updatedCount: res.updatedCount || 0,
            skippedManualCount: res.skippedManualCount || 0,
            missingRateCount: res.missingRateCount || 0,
          };
          resolve(res);
        },
        error: (e) => {
          this.refreshingTp = false;
          this.notify.error(e?.error?.detail || 'Failed to refresh TP Cost.');
          resolve(null);
        },
      });
    });
  }

  private confirmAndOverwriteManualLines(prev: any): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      width: '480px',
      data: {
        title: 'Overwrite manual TP-Cost edits?',
        message:
          `${prev.skippedManualCount} line${prev.skippedManualCount === 1 ? ' has' : 's have'} ` +
          `a hand-edited TP Cost that differs from the rate-table value. ` +
          `They were left unchanged. Overwrite them with the new rate now?`,
        confirmText: 'Overwrite',
        cancelText: 'Keep manual edits',
        confirmColor: 'warn',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.runRefreshTpCost(true);
    });
  }

  /** Hover-tooltip for the post-refresh summary chip. */
  lastRefreshTooltip(): string {
    const s = this.lastRefreshSummary;
    if (!s) return '';
    const parts = [`Updated ${s.updatedCount}`];
    if (s.skippedManualCount) parts.push(`Skipped ${s.skippedManualCount} manually-edited`);
    if (s.missingRateCount) parts.push(`${s.missingRateCount} missing rate`);
    return parts.join(' · ');
  }

  /** yyyy-MM-dd for the JSON body — avoids timezone drift the
   *  ISO toString would introduce. */
  private formatDate(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  openPreview(): void {
    if (!this.sheet) return;
    const visibleCols = this.visibleViabilityCols();
    const previewColumns: SheetPreviewColumn[] = visibleCols
      .filter(c => !c.key.startsWith('_'))
      .map(c => ({
        key: c.key,
        label: c.label,
        format: c.num ? 'number' : 'text',
        cellClass: c.deducted ? 'neg' : (c.neg ? 'neg' : undefined),
      }));
    const data: SheetPreviewDialogData = {
      title: 'Viability Sheet — Preview',
      caption: `${this.sheet.lines.length} line${this.sheet.lines.length === 1 ? '' : 's'}`,
      columns: previewColumns,
      rows: this.sheet.lines,
      hideBlankByDefault: true,
      onExportExcel: () => this.downloadExcel(),
    };
    this.dialog.open(SheetPreviewDialogComponent, {
      width: 'auto',
      maxWidth: '95vw',
      data,
    });
  }

  downloadExcel(): void {
    if (!this.sheet) return;
    const url = `${environment.apiUrl}/viability/${this.sheet.viabilityId}/export`;
    this.http.get(url, { responseType: 'blob', observe: 'response' }).subscribe({
      next: (resp) => {
        const blob = resp.body;
        if (!blob) {
          this.notify.error('Empty file');
          return;
        }
        let filename = `ViabilitySheet-${this.quotId}.xlsx`;
        const cd = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
        if (cd) {
          const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
          if (m && m[1]) filename = decodeURIComponent(m[1]);
        }
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      },
      error: () => this.notify.error('Download failed'),
    });
  }
}
