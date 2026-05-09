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

import { environment } from '../../../../environments/environment';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuService } from '../../../core/services/menu.service';
import { LifecycleUnlockDialogComponent } from '../lifecycle-unlock-dialog/lifecycle-unlock-dialog.component';
import { VersionSelectorComponent } from '../version-selector/version-selector.component';
import { StaleBannerComponent } from '../stale-banner/stale-banner.component';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
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
interface ColMeta { key: string; label: string; width: string; num?: boolean; neg?: boolean; }

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
const NEGATIVE_KEYS = new Set(['CD', 'ShortLnthCharge', 'SplDisc']);

function headCol(key: string): ColMeta {
  return {
    key,
    label: HEAD_LABEL[key] || key,
    width: '90px',
    num: true,
    neg: NEGATIVE_KEYS.has(key),
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
    MatInputModule,
    VersionSelectorComponent,
    StaleBannerComponent,
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
                <app-version-selector
                  [quotId]="quotId"
                  stage="viability"
                  [headVersion]="sheet.versionNo || 1"
                  [canRestore]="canUnlockEditViability"
                  (restored)="stageChanged.emit()">
                </app-version-selector>
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
            <button mat-stroked-button color="primary" (click)="approve()" [disabled]="busy">
              <mat-icon>verified</mat-icon> Approve Viability
            </button>
          }
          @if (sheet && sheet.status === 'Approved' && canUnlockEditViability) {
            <button mat-stroked-button color="warn" (click)="openUnlockDialog()" [disabled]="busy"
              matTooltip="Privileged: unlock this approved viability sheet for in-place edits (audited)">
              <mat-icon>lock_open</mat-icon> Unlock &amp; Edit
            </button>
          }
          @if (sheet) {
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
          (resource)="reSource.emit()">
        </app-stale-banner>
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
                  <tr>
                    @for (c of visibleViabilityCols(); track c.key) {
                      <td [class.num]="c.num" [class.neg]="c.neg"
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
    .viab-table .gross { background: rgba(255, 242, 204, 0.35); }

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
  @Input() readOnly = false;
  // Phase 1 Unlock-and-Edit flag for the Viability stage. Resolved
  // from the menu service in the constructor (privileged users only).
  canUnlockEditViability = false;
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
      },
      error: (e) => {
        this.loading = false;
        this.notify.error(e?.error?.detail || 'Failed to load viability sheet.');
      },
    });
  }

  generate(): void {
    if (!this.quotId) return;
    this.busy = true;
    this.api.post<any>(`/quotations/${this.quotId}/viability`, {}).subscribe({
      next: (res) => {
        this.busy = false;
        this.workingSheet = res.workingSheet || [];
        this.sheet = res.viability || null;
        this.notify.success('Viability sheet generated.');
        this.stageChanged.emit();
      },
      error: (e) => {
        this.busy = false;
        this.notify.error(e?.error?.detail || 'Failed to generate viability sheet.');
      },
    });
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

    this.persistCellChange(row, key, raw);
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
          this.stageChanged.emit();
        },
        error: (e) => {
          this.busy = false;
          this.notify.error(e?.error?.detail || 'Approval failed.');
        },
      });
    });
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
