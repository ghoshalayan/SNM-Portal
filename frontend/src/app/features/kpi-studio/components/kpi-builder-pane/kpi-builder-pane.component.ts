import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CdkDrag, CdkDragDrop, CdkDropList } from '@angular/cdk/drag-drop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiSchemaService } from '../../services/kpi-schema.service';
import {
  AggregateFilter,
  BuilderAggregation,
  BuilderChartType,
  BuilderField,
  BuilderFilter,
  BuilderFilterOp,
  BuilderFormat,
  BuilderSpec,
  ColumnInfo,
  DerivedColumn,
  TableInfo,
  TableRelationship,
} from '../../models/schema.types';

interface WellDef {
  id: string;          // wells[<id>] in the spec
  label: string;
  helper?: string;
  /** When true, fields in this well must carry an aggregation. */
  aggregated: boolean;
  maxFields: number;
}

const CHART_TYPES: { value: BuilderChartType; label: string; icon: string }[] = [
  { value: 'scorecard',  label: 'Score card', icon: 'looks_one' },
  { value: 'stat_group', label: 'Stat group', icon: 'leaderboard' },
  { value: 'bar',        label: 'Bar',        icon: 'bar_chart' },
  { value: 'pie',        label: 'Pie',        icon: 'pie_chart' },
  { value: 'line',       label: 'Line',       icon: 'show_chart' },
  { value: 'table',      label: 'Table',      icon: 'table_chart' },
];

const AGGREGATIONS: { value: BuilderAggregation; label: string }[] = [
  { value: 'SUM',            label: 'Sum' },
  { value: 'AVG',            label: 'Average' },
  { value: 'COUNT',          label: 'Count' },
  { value: 'COUNT_DISTINCT', label: 'Count (distinct)' },
  { value: 'MIN',            label: 'Min' },
  { value: 'MAX',            label: 'Max' },
];

/** Phase E — display format choices. ``null`` = "Number (locale)" so
 * the user can clear a previously-chosen format. */
const FORMATS: { value: BuilderFormat | null; label: string; icon: string }[] = [
  { value: null,       label: 'Number (default)', icon: 'tag' },
  { value: 'currency', label: 'Currency',         icon: 'currency_rupee' },
  { value: 'percent',  label: 'Percent',          icon: 'percent' },
  { value: 'short',    label: 'Short (K, M, B)',  icon: 'compress' },
  { value: 'date',     label: 'Date',             icon: 'event' },
  { value: 'text',     label: 'Text',             icon: 'abc' },
];

const FILTER_OPS: { value: BuilderFilterOp; label: string }[] = [
  { value: '=',           label: '=' },
  { value: '!=',          label: '≠' },
  { value: '>',           label: '>' },
  { value: '>=',          label: '≥' },
  { value: '<',           label: '<' },
  { value: '<=',          label: '≤' },
  { value: 'in',          label: 'in (csv)' },
  { value: 'not_in',      label: 'not in (csv)' },
  { value: 'like',        label: 'like' },
  { value: 'not_like',    label: 'not like' },
  { value: 'is_null',     label: 'is null' },
  { value: 'is_not_null', label: 'is not null' },
  { value: 'between',     label: 'between (a,b)' },
];

/** Wells per chart type — kept in sync with the backend compiler's
 *  `_WELL_RULES`. The component validates the same shape locally so
 *  empty/over-stuffed wells disable the preview button before a
 *  pointless round-trip. */
const WELLS_BY_CHART: Record<BuilderChartType, WellDef[]> = {
  scorecard: [
    { id: 'value',  label: 'Value',  helper: 'one numeric column with aggregation', aggregated: true, maxFields: 1 },
  ],
  stat_group: [
    { id: 'values', label: 'Values', helper: 'one or more aggregated columns', aggregated: true, maxFields: 12 },
  ],
  bar: [
    { id: 'axis',   label: 'Axis',   helper: 'one categorical column',            aggregated: false, maxFields: 1 },
    { id: 'values', label: 'Values', helper: 'one numeric column with aggregation', aggregated: true,  maxFields: 1 },
    { id: 'legend', label: 'Legend', helper: 'optional second category for series', aggregated: false, maxFields: 1 },
  ],
  pie: [
    { id: 'axis',   label: 'Axis',   helper: 'one categorical column',            aggregated: false, maxFields: 1 },
    { id: 'values', label: 'Values', helper: 'one numeric column with aggregation', aggregated: true,  maxFields: 1 },
  ],
  line: [
    { id: 'axis',   label: 'Axis',   helper: 'date or ordinal column',            aggregated: false, maxFields: 1 },
    { id: 'values', label: 'Values', helper: 'numeric column with aggregation',  aggregated: true,  maxFields: 1 },
    { id: 'legend', label: 'Legend', helper: 'optional series column',           aggregated: false, maxFields: 1 },
  ],
  table: [
    { id: 'columns', label: 'Columns', helper: 'columns to display (no aggregation)', aggregated: false, maxFields: 50 },
  ],
};

/** Initial empty spec with sensible defaults. */
function emptySpec(chart: BuilderChartType = 'bar'): BuilderSpec {
  return {
    chart_type: chart,
    source: { name: '' },
    wells: {},
    filters: [],
    top_n: null,
    time_column: null,
  };
}

@Component({
  selector: 'app-kpi-builder-pane',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    CdkDropList, CdkDrag,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatAutocompleteModule, MatMenuModule, MatTooltipModule, MatProgressBarModule,
    MatChipsModule, MatDividerModule,
  ],
  template: `
    <div class="builder-pane">
      <!-- LEFT: Schema browser -->
      <aside class="schema-browser">
        <header>
          <strong>Data source</strong>
          <button mat-icon-button matTooltip="Refresh schema"
                  (click)="refreshSchema()" [disabled]="schemaLoading()">
            <mat-icon>refresh</mat-icon>
          </button>
        </header>

        <!-- Searchable table picker. Type any part of the table or
             schema name; matching tables filter live. The chosen
             table's label stays in the input after select. -->
        <mat-form-field appearance="outline" class="full">
          <mat-label>Table</mat-label>
          <input matInput
                 [matAutocomplete]="tableAuto"
                 [ngModel]="tableSearch()"
                 (ngModelChange)="onTableSearchChange($event)"
                 (focus)="onTableSearchFocus()"
                 placeholder="Type to search...">
          <mat-icon matSuffix>search</mat-icon>
          <mat-autocomplete #tableAuto="matAutocomplete"
                            (optionSelected)="onTableAutocompleteSelected($event)">
            <mat-option *ngFor="let t of filteredTablesForPicker(); trackBy: trackTable"
                        [value]="tableKey(t)">
              {{ tableLabel(t) }}
            </mat-option>
            <mat-option *ngIf="!filteredTablesForPicker().length" disabled>
              No matching table
            </mat-option>
          </mat-autocomplete>
        </mat-form-field>
        <mat-progress-bar *ngIf="schemaLoading()" mode="indeterminate"></mat-progress-bar>

        <div class="columns-list"
             cdkDropList
             [cdkDropListData]="currentColumns()"
             [cdkDropListConnectedTo]="connectedDropIds()"
             [cdkDropListSortingDisabled]="true"
             id="schema-columns">
          <div *ngFor="let c of currentColumns(); trackBy: trackColumn"
               class="column-chip"
               cdkDrag
               [cdkDragData]="c"
               [matTooltip]="c.type"
               matTooltipPosition="right">
            <mat-icon class="col-icon">{{ columnIcon(c) }}</mat-icon>
            <span class="col-name">{{ c.name }}</span>
            <span class="col-type">{{ c.type }}</span>
          </div>
          <p *ngIf="!currentColumns().length" class="hint-empty">
            Pick a table to see its columns.
          </p>
        </div>

        <!-- Phase F — Related tables (auto-detected from FK metadata
             via /schema/relationships). Each related table is an
             expandable section; its columns are draggable just like
             the source columns, and dragging one in sets the
             BuilderField.table so the compiler auto-emits the join. -->
        <details *ngIf="relatedTables().length" class="related-tables">
          <summary>
            <mat-icon class="rel-icon">link</mat-icon>
            Related tables ({{ relatedTables().length }})
          </summary>
          <div *ngFor="let rt of relatedTables(); trackBy: trackRelatedTable"
               class="related-table">
            <div class="rt-head" (click)="toggleExpandedRelated(rt.name)">
              <mat-icon class="rt-arrow"
                        [class.expanded]="isRelatedExpanded(rt.name)">
                chevron_right
              </mat-icon>
              <span class="rt-name">{{ rt.name }}</span>
              <span class="rt-via">via {{ rt.via }}</span>
            </div>
            <div *ngIf="isRelatedExpanded(rt.name)"
                 class="columns-list rt-columns"
                 cdkDropList
                 [cdkDropListData]="rt.columns"
                 [cdkDropListConnectedTo]="connectedDropIds()"
                 [cdkDropListSortingDisabled]="true"
                 [id]="relatedDropId(rt.name)">
              <div *ngFor="let c of rt.columns; trackBy: trackColumn"
                   class="column-chip rt-col"
                   cdkDrag
                   [cdkDragData]="{ column: c, table: rt.name, schema: rt.schema }"
                   [matTooltip]="c.type"
                   matTooltipPosition="right">
                <mat-icon class="col-icon">{{ columnIcon(c) }}</mat-icon>
                <span class="col-name">{{ c.name }}</span>
                <span class="col-type">{{ c.type }}</span>
              </div>
            </div>
          </div>
        </details>
      </aside>

      <!-- RIGHT: Wells + filters + knobs -->
      <section class="wells-pane">
        <!-- Inline manual — collapsible so it doesn't eat space once
             the user knows their way around. Persisted in
             localStorage so the open/closed state survives reloads. -->
        <details class="builder-help" [open]="helpOpen()" (toggle)="onHelpToggle($event)">
          <summary>
            <mat-icon class="help-icon">help_outline</mat-icon>
            How does this builder work?
          </summary>
          <div class="help-body">
            <ol class="help-steps">
              <li>
                <strong>Pick a data source</strong> on the left — the
                table whose rows feed every chart on this card.
              </li>
              <li>
                <strong>Choose a chart type</strong> — the available
                wells (drop zones) below adapt to it.
              </li>
              <li>
                <strong>Drag columns into wells.</strong> Each well
                expects a specific kind of column — see the table
                below. You can also drag from the
                <em>Related tables</em> tree (auto-emits a JOIN) or
                from the <em>Calculations</em> panel.
              </li>
              <li>
                Optionally narrow the data with <strong>Filters</strong>,
                limit rows with <strong>Top N</strong>, define
                computed fields in <strong>Calculations</strong>, then
                click <strong>Run preview</strong> in the editor's
                header.
              </li>
            </ol>

            <table class="help-wells">
              <thead>
                <tr><th>Well</th><th>What goes here</th><th>Example</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Axis</strong> (bar, pie, line)</td>
                  <td>One categorical column — what each bar / slice / point represents.</td>
                  <td><code>region</code>, <code>status</code>, <code>created_at</code></td>
                </tr>
                <tr>
                  <td><strong>Values</strong></td>
                  <td>One or more numeric columns with an aggregation (SUM / AVG / COUNT…).</td>
                  <td><code>SUM(amount)</code>, <code>COUNT_DISTINCT(customer_id)</code></td>
                </tr>
                <tr>
                  <td><strong>Legend</strong> (bar, line — optional)</td>
                  <td>A second categorical column to split each axis point into series.</td>
                  <td><code>status</code> (split sales by status)</td>
                </tr>
                <tr>
                  <td><strong>Value</strong> (scorecard)</td>
                  <td>One aggregated number — the headline figure.</td>
                  <td><code>SUM(amount)</code></td>
                </tr>
                <tr>
                  <td><strong>Columns</strong> (table)</td>
                  <td>Any number of raw columns, no aggregation.</td>
                  <td><code>enquiry_no</code>, <code>customer_name</code>, <code>amount</code></td>
                </tr>
              </tbody>
            </table>

            <div class="help-block">
              <strong>Calculations</strong> let you define a computed
              column once and use it everywhere. Type a T-SQL
              expression — references to other columns just work:
              <ul>
                <li><code>amount * 1.18</code> — arithmetic</li>
                <li><code>CASE WHEN status = 'Open' THEN 1 ELSE 0 END</code> — conditional</li>
                <li><code>DATEDIFF(day, created_at, GETDATE())</code> — date math</li>
                <li><code>ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC)</code> —
                  rank within group; combine with a <em>≤ 5</em>
                  filter for "top 5 per region"
                </li>
              </ul>
            </div>

            <div class="help-block">
              <strong>Format</strong> (the icon next to each value's
              aggregation menu): pick how the number renders —
              <em>currency</em>, <em>percent</em>, <em>short</em>
              (1.2K / 4.5M), <em>date</em>, or plain number. This
              flows into the chart at render time, no SQL change.
            </div>
          </div>
        </details>

        <div class="chart-picker">
          <mat-form-field appearance="outline">
            <mat-label>Chart type</mat-label>
            <mat-select [value]="chartType()" (valueChange)="onChartTypeChange($event)">
              <mat-option *ngFor="let c of chartTypeOptions" [value]="c.value">
                <mat-icon class="opt-icon">{{ c.icon }}</mat-icon>
                {{ c.label }}
              </mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" *ngIf="!isAggregateOnly()">
            <mat-label>Top N (optional)</mat-label>
            <input matInput type="number" min="1" max="10000"
                   [ngModel]="topN()" (ngModelChange)="setTopN($event)">
          </mat-form-field>
        </div>

        <!-- Wells — one drop list per well; column chips drag in from the left. -->
        <div class="wells">
          <div *ngFor="let w of wells(); trackBy: trackWell"
               class="well"
               cdkDropList
               [id]="wellDropId(w.id)"
               [cdkDropListData]="getWellFields(w.id)"
               [cdkDropListConnectedTo]="['schema-columns', otherWellDropIds(w.id)]"
               (cdkDropListDropped)="onDrop(w, $event)">
            <header>
              <strong>{{ w.label }}</strong>
              <span class="well-helper" *ngIf="w.helper">— {{ w.helper }}</span>
            </header>
            <div class="well-body">
              <div *ngFor="let f of getWellFields(w.id); let i = index; trackBy: trackField"
                   class="well-chip"
                   cdkDrag
                   [cdkDragData]="f">
                <mat-icon class="chip-grip" cdkDragHandle>drag_indicator</mat-icon>
                <span class="chip-label"
                      [matTooltip]="f.table ? f.table + '.' + f.column : f.column">
                  <span *ngIf="f.table" class="chip-table">{{ f.table }}.</span>{{ f.column }}
                </span>

                <button mat-button class="agg-btn"
                        *ngIf="w.aggregated"
                        [matMenuTriggerFor]="aggMenu">
                  {{ aggLabel(f.agg) }}
                  <mat-icon>arrow_drop_down</mat-icon>
                </button>
                <mat-menu #aggMenu="matMenu">
                  <button mat-menu-item *ngFor="let a of aggregations"
                          (click)="setFieldAgg(w.id, i, a.value)">
                    <mat-icon *ngIf="f.agg === a.value">check</mat-icon>
                    <span>{{ a.label }}</span>
                  </button>
                </mat-menu>

                <!-- Phase E — value format dropdown. Only meaningful
                     for fields whose values render in the chart
                     (aggregated wells, scorecard values, bar values).
                     Unset = number with locale defaults. -->
                <button mat-button class="fmt-btn"
                        *ngIf="w.aggregated"
                        [matMenuTriggerFor]="fmtMenu"
                        matTooltip="Display format">
                  <mat-icon class="fmt-icon">{{ formatIcon(f.format) }}</mat-icon>
                </button>
                <mat-menu #fmtMenu="matMenu">
                  <button mat-menu-item *ngFor="let fmt of formats"
                          (click)="setFieldFormat(w.id, i, fmt.value)">
                    <mat-icon *ngIf="f.format === fmt.value || (!f.format && !fmt.value)">check</mat-icon>
                    <mat-icon class="fmt-row-icon">{{ fmt.icon }}</mat-icon>
                    <span>{{ fmt.label }}</span>
                  </button>
                </mat-menu>

                <button mat-icon-button matTooltip="Remove" class="chip-x"
                        (click)="removeField(w.id, i)">
                  <mat-icon>close</mat-icon>
                </button>
              </div>
              <p *ngIf="!getWellFields(w.id).length" class="hint-drop">
                Drop a column here
              </p>
            </div>
          </div>
        </div>

        <!-- Filters block -->
        <div class="filters">
          <header>
            <strong>Filters</strong>
            <button mat-stroked-button (click)="addFilter()">
              <mat-icon>add</mat-icon> Add filter
            </button>
          </header>
          <div *ngFor="let f of filters(); let i = index; trackBy: trackFilter"
               class="filter-row">
            <mat-form-field appearance="outline" class="filter-col">
              <mat-label>Column</mat-label>
              <mat-select [value]="f.column" (valueChange)="setFilterColumn(i, $event)">
                <mat-option *ngFor="let c of currentColumns()" [value]="c.name">
                  {{ c.name }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="filter-op">
              <mat-label>Op</mat-label>
              <mat-select [value]="f.op" (valueChange)="setFilterOp(i, $event)">
                <mat-option *ngFor="let o of filterOps" [value]="o.value">
                  {{ o.label }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="filter-val"
                            *ngIf="needsFilterValue(f.op)">
              <mat-label>Value</mat-label>
              <input matInput [ngModel]="filterValueDisplay(f)"
                     (ngModelChange)="setFilterValueRaw(i, $event)"
                     [readonly]="filterValueIsParam(f)"
                     [class.param-input]="filterValueIsParam(f)">
              <mat-icon matSuffix class="param-suffix"
                        *ngIf="filterValueIsParam(f)">flash_on</mat-icon>
            </mat-form-field>
            <!-- Phase I — runtime param shortcut. Replaces the Value
                 with a bind marker (:company_id / :user_id) so the
                 same KPI auto-slices per caller. -->
            <button mat-icon-button class="param-btn"
                    *ngIf="needsFilterValue(f.op)"
                    [matMenuTriggerFor]="paramMenu"
                    matTooltip="Use a runtime parameter">
              <mat-icon>flash_on</mat-icon>
            </button>
            <mat-menu #paramMenu="matMenu">
              <button mat-menu-item (click)="setFilterParamRef(i, 'company_id')">
                <mat-icon>business</mat-icon>
                <span>Current company</span>
              </button>
              <button mat-menu-item (click)="setFilterParamRef(i, 'user_id')">
                <mat-icon>person</mat-icon>
                <span>Current user</span>
              </button>
              <button mat-menu-item (click)="clearFilterParamRef(i)"
                      *ngIf="filterValueIsParam(f)">
                <mat-icon>close</mat-icon>
                <span>Clear (use literal)</span>
              </button>
            </mat-menu>
            <button mat-icon-button (click)="removeFilter(i)" matTooltip="Remove filter">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
          <p *ngIf="!filters().length" class="hint-empty">
            No filters. Click <em>Add filter</em> to scope the query.
            Tip: use the <mat-icon class="inline-flash">flash_on</mat-icon>
            button to bind <code>:company_id</code> or <code>:user_id</code>
            so the same KPI shows each user their own slice.
          </p>
        </div>

        <!-- Phase G.2 — Aggregate filters (HAVING). Predicate on the
             *result* of an aggregation, e.g. SUM(amount) > 100000.
             Emitted as a HAVING clause after GROUP BY. -->
        <div class="filters">
          <header>
            <strong>Aggregate filters</strong>
            <span class="header-hint">Filter on totals (HAVING)</span>
            <button mat-stroked-button (click)="addAggregateFilter()">
              <mat-icon>add</mat-icon> Add aggregate filter
            </button>
          </header>
          <div *ngFor="let af of aggregateFilters(); let i = index; trackBy: trackAggFilter"
               class="agg-filter-row">
            <mat-form-field appearance="outline" class="filter-op">
              <mat-label>Function</mat-label>
              <mat-select [value]="af.agg" (valueChange)="setAggFilterAgg(i, $event)">
                <mat-option *ngFor="let a of aggregations" [value]="a.value">
                  {{ a.label }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="filter-col">
              <mat-label>Column</mat-label>
              <mat-select [value]="af.column" (valueChange)="setAggFilterColumn(i, $event)">
                <mat-option *ngFor="let c of currentColumns()" [value]="c.name">
                  {{ c.name }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="filter-op">
              <mat-label>Op</mat-label>
              <mat-select [value]="af.op" (valueChange)="setAggFilterOp(i, $event)">
                <mat-option *ngFor="let o of filterOps" [value]="o.value">
                  {{ o.label }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="filter-val"
                            *ngIf="needsFilterValue(af.op)">
              <mat-label>Value</mat-label>
              <input matInput [ngModel]="aggFilterValueDisplay(af)"
                     (ngModelChange)="setAggFilterValueRaw(i, $event)">
            </mat-form-field>
            <button mat-icon-button (click)="removeAggregateFilter(i)"
                    matTooltip="Remove">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
          <p *ngIf="!aggregateFilters().length" class="hint-empty">
            No aggregate filters. Use these to keep only categories
            whose total / count meets a threshold (e.g.
            <code>SUM(amount) > 100000</code>).
          </p>
        </div>

        <!-- Phase G — Calculations (derived columns). Each one is a
             T-SQL expression evaluated once per row in a CTE; the
             alias becomes draggable on the left as if it were a real
             column, and is referenceable in any well or filter. -->
        <div class="derived">
          <header>
            <strong>Calculations</strong>
            <button mat-stroked-button (click)="addDerivedColumn()">
              <mat-icon>functions</mat-icon> Add calculation
            </button>
          </header>
          <div *ngFor="let d of derivedColumns(); let i = index; trackBy: trackDerived"
               class="derived-row">
            <mat-form-field appearance="outline" class="derived-alias">
              <mat-label>Name</mat-label>
              <input matInput maxlength="128"
                     [ngModel]="d.alias"
                     (ngModelChange)="setDerivedAlias(i, $event)"
                     placeholder="profit_margin">
            </mat-form-field>
            <mat-form-field appearance="outline" class="derived-expr">
              <mat-label>Expression (T-SQL)</mat-label>
              <input matInput maxlength="4000"
                     spellcheck="false"
                     [ngModel]="d.expression"
                     (ngModelChange)="setDerivedExpression(i, $event)"
                     placeholder="amount * 1.18">
              <mat-hint>e.g. amount * 1.18, CASE WHEN status = 'Open' THEN 1 ELSE 0 END</mat-hint>
            </mat-form-field>
            <button mat-button class="fmt-btn"
                    [matMenuTriggerFor]="dFmtMenu"
                    matTooltip="Display format">
              <mat-icon class="fmt-icon">{{ formatIcon(d.format) }}</mat-icon>
            </button>
            <mat-menu #dFmtMenu="matMenu">
              <button mat-menu-item *ngFor="let fmt of formats"
                      (click)="setDerivedFormat(i, fmt.value)">
                <mat-icon *ngIf="d.format === fmt.value || (!d.format && !fmt.value)">check</mat-icon>
                <mat-icon class="fmt-row-icon">{{ fmt.icon }}</mat-icon>
                <span>{{ fmt.label }}</span>
              </button>
            </mat-menu>
            <button mat-icon-button (click)="removeDerivedColumn(i)" matTooltip="Remove calculation">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
          <p *ngIf="!derivedColumns().length" class="hint-empty">
            No calculations. Click <em>Add calculation</em> to define a
            computed column (e.g. <code>amount * 1.18</code>).
          </p>
        </div>

        <!-- Spec preview (read-only, collapsible) -->
        <details class="spec-debug">
          <summary>Spec JSON (debug)</summary>
          <pre>{{ specJson() }}</pre>
        </details>

        <div *ngIf="validationMessage() as msg" class="warn">
          <mat-icon>warning</mat-icon>
          <span>{{ msg }}</span>
        </div>
      </section>
    </div>
  `,
  styles: [`
    :host { display: block; height: 100%; }
    .builder-pane {
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 12px;
      height: 100%; min-height: 0;
    }

    .schema-browser, .wells-pane {
      display: flex; flex-direction: column; gap: 10px;
      min-height: 0;
      background: var(--snm-bg-panel, #fafafa);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px;
      padding: 12px;
      /* Both panes own their own scroll so the inner sections can
         stack arbitrarily long without pushing the page out of the
         viewport. Each scrollbar is thin + portal-tinted. */
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2)) transparent;
    }
    .schema-browser::-webkit-scrollbar,
    .wells-pane::-webkit-scrollbar { width: 8px; }
    .schema-browser::-webkit-scrollbar-thumb,
    .wells-pane::-webkit-scrollbar-thumb {
      background: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2));
      border-radius: 4px;
    }
    .schema-browser::-webkit-scrollbar-thumb:hover,
    .wells-pane::-webkit-scrollbar-thumb:hover {
      background: var(--snm-scrollbar-thumb-hover, rgba(100, 140, 200, 0.35));
    }
    .full { width: 100%; }
    header {
      display: flex; align-items: center; gap: 6px;
      strong { color: var(--snm-text-primary); font-size: 0.9rem; }
    }

    /* Schema browser. The columns list used to scroll independently;
       the schema-browser parent now owns the scroll for both columns
       and the related-tables tree, so this just lays them out. */
    .columns-list {
      display: flex; flex-direction: column; gap: 4px;
      padding: 4px 0;
    }
    .column-chip {
      display: flex; align-items: center; gap: 6px;
      padding: 6px 8px;
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 4px;
      font-size: 0.82rem;
      cursor: grab;
      transition: border-color 120ms ease, transform 120ms ease;
      &:hover { border-color: var(--snm-accent, #4a90e2); transform: translateX(2px); }
      &:active { cursor: grabbing; }
      .col-icon { font-size: 14px; width: 14px; height: 14px; color: var(--snm-text-muted); }
      .col-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .col-type {
        font-size: 0.7rem; color: var(--snm-text-muted);
        font-family: ui-monospace, Consolas, monospace;
      }
    }
    .hint-empty {
      margin: 8px 0; color: var(--snm-text-muted);
      font-size: 0.8rem; font-style: italic; text-align: center;
    }

    /* Phase F — Related tables tree, expandable per-table. */
    .related-tables {
      border-top: 1px solid var(--snm-border-divider);
      padding-top: 8px;
      summary {
        display: flex; align-items: center; gap: 6px;
        cursor: pointer; font-size: 0.82rem;
        color: var(--snm-text-secondary); font-weight: 500;
        padding: 4px 0;
        list-style: none;
        &::-webkit-details-marker { display: none; }
        .rel-icon {
          font-size: 16px; width: 16px; height: 16px;
          color: var(--snm-accent);
        }
      }
    }
    .related-table { margin: 4px 0; }
    .rt-head {
      display: flex; align-items: center; gap: 4px;
      padding: 4px 6px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.78rem;
      color: var(--snm-text-secondary);
      transition: background 120ms ease;
      &:hover { background: var(--snm-accent-subtle); }
      .rt-arrow {
        font-size: 14px; width: 14px; height: 14px;
        transition: transform 120ms ease;
        &.expanded { transform: rotate(90deg); }
      }
      .rt-name { font-weight: 500; color: var(--snm-text-primary); }
      .rt-via {
        margin-left: auto;
        font-family: ui-monospace, Consolas, monospace;
        font-size: 0.7rem;
        color: var(--snm-text-muted);
      }
    }
    .rt-columns {
      padding-left: 18px;
      /* No own scroll — the schema-browser parent owns one. The
         related-table column lists just expand inline. */
      .rt-col { background: var(--snm-bg-panel); }
    }

    /* Joined-field prefix on the well chip */
    .chip-table {
      color: var(--snm-accent);
      font-weight: 500;
    }

    /* Inline manual — collapsed by default after first close. */
    .builder-help {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-accent-shadow, rgba(91, 143, 217, 0.25));
      border-left: 3px solid var(--snm-accent, #4a90e2);
      border-radius: 6px;
      padding: 10px 14px;
      summary {
        list-style: none;
        cursor: pointer;
        display: flex; align-items: center; gap: 8px;
        font-weight: 600; font-size: 0.92rem;
        color: var(--snm-text-primary);
        &::-webkit-details-marker { display: none; }
        .help-icon { color: var(--snm-accent); }
      }
      &[open] summary { margin-bottom: 8px; padding-bottom: 8px;
                        border-bottom: 1px solid var(--snm-border-divider); }
    }
    .help-body {
      font-size: 0.85rem; color: var(--snm-text-secondary);
      line-height: 1.5;
    }
    .help-steps {
      margin: 0 0 12px; padding-left: 20px;
      li { margin: 4px 0; }
      strong { color: var(--snm-text-primary); }
    }
    .help-wells {
      width: 100%; border-collapse: collapse;
      font-size: 0.82rem;
      margin: 8px 0 12px;
      th, td {
        text-align: left; padding: 6px 8px;
        border-bottom: 1px solid var(--snm-border-divider);
        vertical-align: top;
      }
      th {
        background: var(--snm-bg-header-row, rgba(100, 140, 200, 0.06));
        font-weight: 600; font-size: 0.74rem;
        text-transform: uppercase; letter-spacing: 0.05em;
        color: var(--snm-text-muted);
      }
      td:nth-child(1) { width: 26%; }
      td:nth-child(3) { width: 32%; }
      code {
        font-size: 0.78rem;
        background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.08));
        color: var(--snm-accent);
        padding: 1px 5px; border-radius: 3px;
        font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      }
    }
    .help-block {
      margin: 8px 0;
      strong { color: var(--snm-text-primary); }
      ul { margin: 4px 0 0; padding-left: 20px; }
      li { margin: 3px 0; }
      code {
        font-size: 0.78rem;
        background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.08));
        color: var(--snm-accent);
        padding: 1px 5px; border-radius: 3px;
        font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      }
    }

    /* Wells pane */
    /* Chart Type + Top N share one row inside the builder. Each
       shrinks to fit so they never wrap below ~280px combined. */
    .chart-picker {
      display: flex; gap: 8px; flex-wrap: nowrap;
      align-items: flex-start;
    }
    .chart-picker mat-form-field { flex: 1 1 0; min-width: 0; }
    .opt-icon { font-size: 16px; width: 16px; height: 16px; vertical-align: middle; margin-right: 4px; }

    .wells {
      display: flex; flex-direction: column; gap: 8px;
    }
    .well {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 6px;
      padding: 8px 10px;
      transition: border-color 140ms ease, background 140ms ease;
      &.cdk-drop-list-dragging,
      &:has(.cdk-drag-preview) {
        border-color: var(--snm-accent, #4a90e2);
        background: rgba(74, 144, 226, 0.06);
      }
      header { gap: 4px; }
      .well-helper { color: var(--snm-text-muted); font-size: 0.75rem; }
    }
    .well-body {
      display: flex; flex-direction: column; gap: 6px; margin-top: 6px;
      min-height: 36px;
    }
    .well-chip {
      display: flex; align-items: center; gap: 4px;
      padding: 4px 6px;
      background: var(--snm-bg-panel, #f7f8fa);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 4px;
      font-size: 0.82rem;
      .chip-grip { font-size: 14px; width: 14px; height: 14px;
                   color: var(--snm-text-muted); cursor: grab; }
      .chip-label { flex: 1; min-width: 0;
                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .agg-btn {
        font-size: 0.75rem; min-width: 0; padding: 0 4px;
        line-height: 1.5;
        mat-icon { font-size: 14px; width: 14px; height: 14px; }
      }
      .fmt-btn {
        min-width: 0; padding: 0 4px; line-height: 1.5;
        color: var(--snm-text-muted);
        .fmt-icon { font-size: 16px; width: 16px; height: 16px; margin: 0; }
      }
      .chip-x mat-icon { font-size: 16px; width: 16px; height: 16px; }
    }
    /* Format menu — small icon next to each row so the user can
       associate the icon with the chosen format on the chip. */
    ::ng-deep .mat-mdc-menu-item .fmt-row-icon {
      font-size: 16px; width: 16px; height: 16px; margin-right: 4px;
      color: var(--snm-text-muted);
    }
    .hint-drop {
      margin: 0; color: var(--snm-text-muted); font-size: 0.78rem;
      font-style: italic; padding: 6px 4px;
    }

    /* Filters */
    .filters {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 6px; padding: 8px 10px;
    }
    .filters header { justify-content: space-between; }
    .filter-row {
      display: grid;
      grid-template-columns: 1.4fr 0.8fr 1.4fr auto auto;
      gap: 6px; align-items: center; margin-top: 6px;
    }
    .filter-row mat-form-field { font-size: 0.8rem; }
    /* HAVING row gets one extra column for the aggregation function. */
    .agg-filter-row {
      display: grid;
      grid-template-columns: 0.9fr 1.2fr 0.8fr 1.4fr auto;
      gap: 6px; align-items: center; margin-top: 6px;
    }
    .agg-filter-row mat-form-field { font-size: 0.8rem; }
    .header-hint {
      font-size: 0.75rem; color: var(--snm-text-muted);
      font-weight: 400; margin-left: 8px;
    }
    /* Phase I — runtime-param visual hint. The value field gets an
       accent-tinted background + flash icon so the user can tell at
       a glance that this filter binds a per-caller parameter. */
    .param-input { color: var(--snm-accent) !important; font-weight: 500; }
    .param-suffix { color: var(--snm-accent); font-size: 18px; width: 18px; height: 18px; }
    .param-btn {
      width: 28px; height: 28px; line-height: 28px;
      mat-icon { font-size: 16px; width: 16px; height: 16px; color: var(--snm-text-muted); }
      &:hover mat-icon { color: var(--snm-accent); }
    }
    .inline-flash {
      font-size: 14px; width: 14px; height: 14px;
      vertical-align: text-bottom; color: var(--snm-accent);
    }

    /* Phase G — Calculations panel. Mirrors the Filters panel's shell
       so the two read as a coherent pair. */
    .derived {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 6px; padding: 8px 10px;
    }
    .derived header {
      justify-content: space-between;
      mat-icon { color: var(--snm-accent, #4a90e2); }
    }
    .derived-row {
      display: grid;
      grid-template-columns: minmax(110px, 0.8fr) minmax(180px, 1.6fr) auto auto;
      gap: 6px; align-items: center; margin-top: 6px;
    }
    .derived-row mat-form-field { font-size: 0.8rem; }
    .derived-row .derived-expr input {
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
    }

    /* Spec debug */
    .spec-debug {
      font-size: 0.78rem;
      summary { cursor: pointer; color: var(--snm-text-muted); }
      pre {
        margin: 6px 0 0; padding: 8px; background: var(--snm-bg-panel, #f7f8fa);
        border-radius: 4px; max-height: 200px; overflow: auto;
        font-family: ui-monospace, Consolas, monospace; font-size: 0.72rem;
      }
    }

    .warn {
      display: flex; align-items: center; gap: 6px;
      padding: 6px 8px; border-radius: 4px;
      background: rgba(245, 124, 0, 0.08);
      color: #c66600; font-size: 0.82rem;
      mat-icon { font-size: 18px; width: 18px; height: 18px; }
    }

    /* CDK drag preview / placeholder polish */
    ::ng-deep .cdk-drag-preview {
      box-shadow: 0 6px 16px rgba(0,0,0,0.16);
      border-radius: 4px;
    }
    ::ng-deep .cdk-drag-placeholder { opacity: 0.3; }
  `],
})
export class KpiBuilderPaneComponent implements OnInit {
  private readonly schemaApi = inject(KpiSchemaService);
  private readonly destroyRef = inject(DestroyRef);

  /** Two-way binding — host owns the spec; we mutate it through
   * ``model().set()`` so external code can also patch (e.g. when
   * loading an existing KPI). */
  readonly spec = model<BuilderSpec>(emptySpec());

  /** Emitted alongside the model when anything changes — gives the
   * host a single place to react (re-run preview etc.). */
  readonly specChange = output<BuilderSpec>();

  readonly chartTypeOptions = CHART_TYPES;
  readonly aggregations = AGGREGATIONS;
  readonly formats = FORMATS;
  readonly filterOps = FILTER_OPS;

  readonly tables = signal<TableInfo[]>([]);
  readonly schemaLoading = signal(false);
  /** Free-text input bound to the searchable Table autocomplete. */
  readonly tableSearch = signal('');
  /** Persistable open state for the inline manual at the top of the
   * wells pane. Defaults to *open* on first visit so new users see
   * the guide; collapses (and stays collapsed across sessions) once
   * the user closes it. */
  readonly helpOpen = signal(this.readHelpOpen());
  /** Phase F — relationship graph loaded from /schema/relationships.
   * Drives the "Related tables" tree under the schema browser. */
  readonly relationships = signal<TableRelationship[]>([]);
  /** Tracks which related tables are expanded in the tree. */
  private readonly expandedRelated = signal<Set<string>>(new Set());

  // ---- spec accessors --------------------------------------------------
  readonly chartType = computed(() => this.spec().chart_type);
  readonly wells = computed(() => WELLS_BY_CHART[this.chartType()]);
  readonly topN = computed(() => this.spec().top_n ?? null);
  readonly filters = computed(() => this.spec().filters ?? []);
  /** Phase G — calculated columns. Surfaced both in the dedicated
   * "Calculations" panel and (via ``currentColumns``) in the
   * draggable column list so they can be dropped into any well. */
  readonly derivedColumns = computed(() => this.spec().derived_columns ?? []);
  /** Phase G.2 — HAVING-style filters on aggregated values. */
  readonly aggregateFilters = computed(() => this.spec().aggregate_filters ?? []);
  /** ``schema.table`` style identifier — matches against the spec
   * source so the dropdown reflects the current selection. */
  readonly sourceTableKey = computed(() => {
    const s = this.spec().source;
    if (!s?.name) return null;
    return s.schema ? `${s.schema}.${s.name}` : s.name;
  });

  /** Columns of the currently-selected table (for drag source + filter
   * column dropdowns). Phase G — derived columns are appended so
   * they appear in the draggable column list and the filter dropdown
   * with a ``[calc]`` type tag. */
  readonly currentColumns = computed<ColumnInfo[]>(() => {
    const key = this.sourceTableKey();
    const baseCols = (() => {
      if (!key) return [] as ColumnInfo[];
      const t = this.tables().find(x => this.tableKey(x) === key);
      return t?.columns ?? [];
    })();
    const derivedAsCols: ColumnInfo[] = this.derivedColumns()
      .filter(d => d.alias)
      .map(d => ({
        // ColumnInfo has just name + type + nullability; we shoehorn
        // derived columns in by labelling their type as ``calc`` so
        // ``columnIcon`` can render them with a distinct icon.
        name: d.alias,
        type: 'calc',
        nullable: true,
        primary_key: false,
      } as ColumnInfo));
    return [...baseCols, ...derivedAsCols];
  });

  /** Drop list ids the schema browser is connected to, plus all wells —
   * lets a chip be dragged from any well to any other and back.
   * Includes the per-related-table lists so columns from those can
   * also be dragged into the wells. */
  readonly connectedDropIds = computed(() => [
    ...this.wells().map(w => this.wellDropId(w.id)),
    ...this.relatedTables().map(rt => this.relatedDropId(rt.name)),
  ]);

  /** Phase F — for the current source table, walk the relationship
   * graph one hop and collect the related tables + their columns.
   * The ``via`` label tells the user how the join lands (e.g.
   * ``customer_id → id``). */
  readonly relatedTables = computed<Array<{
    name: string; schema: string | null; via: string; columns: ColumnInfo[];
  }>>(() => {
    const src = this.spec().source;
    if (!src?.name) return [];
    const rels = this.relationships();
    const all = this.tables();
    const tableByKey = new Map<string, TableInfo>();
    for (const t of all) {
      const key = t.schema ? `${t.schema}.${t.name}` : t.name;
      tableByKey.set(key, t);
    }
    const out: Array<{ name: string; schema: string | null; via: string; columns: ColumnInfo[] }> = [];
    const seen = new Set<string>();
    for (const r of rels) {
      if (!r.is_active) continue;
      // Match either direction — source can be on the FK side or the
      // referenced side; both produce a useful related table.
      const matchesFrom = (r.from_table === src.name) &&
        ((r.from_schema || null) === (src.schema || null));
      const matchesTo = (r.to_table === src.name) &&
        ((r.to_schema || null) === (src.schema || null));
      if (!matchesFrom && !matchesTo) continue;
      const otherName = matchesFrom ? r.to_table : r.from_table;
      const otherSchema = matchesFrom ? r.to_schema : r.from_schema;
      const otherKey = otherSchema ? `${otherSchema}.${otherName}` : otherName;
      if (seen.has(otherKey)) continue;
      seen.add(otherKey);
      const t = tableByKey.get(otherKey);
      if (!t) continue;
      const via = matchesFrom
        ? `${r.from_column} → ${r.to_column}`
        : `${r.to_column} ← ${r.from_column}`;
      out.push({ name: otherName, schema: otherSchema, via, columns: t.columns });
    }
    return out;
  });

  isRelatedExpanded(tableName: string): boolean {
    return this.expandedRelated().has(tableName);
  }

  toggleExpandedRelated(tableName: string): void {
    const set = new Set(this.expandedRelated());
    if (set.has(tableName)) set.delete(tableName);
    else set.add(tableName);
    this.expandedRelated.set(set);
  }

  /** Per-table drop list id so cdkDropListConnectedTo can wire each
   * related-table list into the wells too. */
  relatedDropId(tableName: string): string {
    return `related-${tableName}`;
  }

  trackRelatedTable = (_: number, rt: { name: string }) => rt.name;

  readonly specJson = computed(() => JSON.stringify(this.spec(), null, 2));

  /** Cheap local mirror of compiler validation — keeps the editor
   * honest before paying for a network round-trip. */
  readonly validationMessage = computed<string | null>(() => {
    const s = this.spec();
    if (!s.source.name) return 'Pick a data source table.';
    for (const w of this.wells()) {
      const fields = s.wells[w.id] ?? [];
      if (w.id === 'value' || w.id === 'values' || w.id === 'columns') {
        if (!fields.length && (w.id !== 'columns' ? true : false)) {
          // 'columns' for table allows 0 only when fully empty —
          // backend rules say 1+. So we still warn:
        }
      }
    }
    // Required wells per chart.
    const required: Record<BuilderChartType, string[]> = {
      scorecard:  ['value'],
      stat_group: ['values'],
      bar:        ['axis', 'values'],
      pie:        ['axis', 'values'],
      line:       ['axis', 'values'],
      table:      ['columns'],
    };
    for (const r of required[s.chart_type] ?? []) {
      if (!(s.wells[r] ?? []).length) {
        return `Drop a column into the "${r}" well.`;
      }
    }
    // Aggregated wells must have agg.
    const aggWells: Record<BuilderChartType, string[]> = {
      scorecard:  ['value'],
      stat_group: ['values'],
      bar:        ['values'],
      pie:        ['values'],
      line:       ['values'],
      table:      [],
    };
    for (const w of aggWells[s.chart_type] ?? []) {
      const bad = (s.wells[w] ?? []).find(f => !f.agg);
      if (bad) return `Field "${bad.column}" needs an aggregation.`;
    }
    return null;
  });

  isAggregateOnly(): boolean {
    return this.chartType() === 'scorecard' || this.chartType() === 'stat_group';
  }

  ngOnInit(): void {
    this.refreshSchema();
    this.loadRelationships();
  }

  /** Load the relationship graph so the "Related tables" tree can
   * render. Silent on error — the builder still works in single-table
   * mode without it. */
  private loadRelationships(): void {
    this.schemaApi.listRelationships()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => this.relationships.set(res.items ?? []),
        error: () => this.relationships.set([]),
      });
  }

  // ---- schema --------------------------------------------------------

  refreshSchema(): void {
    this.schemaLoading.set(true);
    this.schemaApi.getTables()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.tables.set(res.tables ?? []);
          this.schemaLoading.set(false);
          // Once tables are loaded, mirror the current source's
          // label into the search box so the user sees what's
          // selected. Only set if empty (don't clobber typing).
          if (!this.tableSearch()) {
            const key = this.sourceTableKey();
            if (key) {
              const t = res.tables?.find(x => this.tableKey(x) === key);
              if (t) this.tableSearch.set(this.tableLabel(t));
            }
          }
        },
        error: () => {
          this.tables.set([]);
          this.schemaLoading.set(false);
        },
      });
  }

  tableKey(t: TableInfo): string {
    return t.schema ? `${t.schema}.${t.name}` : t.name;
  }
  tableLabel(t: TableInfo): string {
    return this.tableKey(t) + (t.row_count_estimate ? ` (~${t.row_count_estimate})` : '');
  }

  onTableChange(key: string): void {
    const [schema, name] = key.includes('.') ? key.split('.', 2) : [null, key];
    this.patch(s => ({
      ...s,
      source: { kind: 'table', schema: schema || null, name },
      // Switching tables wipes wells + filters — column refs would be
      // stale. Same UX as Power BI when you replace the data source.
      wells: {},
      filters: [],
    }));
    // Sync the search box label with the selected table.
    const t = this.tables().find(x => this.tableKey(x) === key);
    this.tableSearch.set(t ? this.tableLabel(t) : key);
  }

  /** Tables filtered by the search box. Empty input shows everything;
   * otherwise case-insensitive substring match against the schema-
   * qualified label. */
  filteredTablesForPicker(): TableInfo[] {
    const q = this.tableSearch().trim().toLowerCase();
    const all = this.tables();
    if (!q) return all;
    return all.filter(t => this.tableLabel(t).toLowerCase().includes(q)
                       || t.name.toLowerCase().includes(q));
  }

  onTableSearchChange(value: string): void {
    this.tableSearch.set(value);
  }

  onTableSearchFocus(): void {
    // Clear the displayed label so the user sees the full list when
    // they refocus to switch tables.
    this.tableSearch.set('');
  }

  onTableAutocompleteSelected(ev: MatAutocompleteSelectedEvent): void {
    this.onTableChange(ev.option.value as string);
  }

  // ---- chart-type + top_n ------------------------------------------

  onChartTypeChange(t: BuilderChartType): void {
    this.patch(s => {
      // Trim wells that don't apply to the new chart type. Power BI
      // moves matching wells across when possible — we keep it simple
      // and reset wells that don't exist on the new visual.
      const allowed = new Set(WELLS_BY_CHART[t].map(w => w.id));
      const next: Record<string, BuilderField[]> = {};
      for (const [k, v] of Object.entries(s.wells)) {
        if (allowed.has(k)) next[k] = v;
      }
      return { ...s, chart_type: t, wells: next };
    });
  }

  setTopN(v: number | string | null): void {
    const n = v == null || v === '' ? null : Number(v);
    this.patch(s => ({ ...s, top_n: Number.isFinite(n) && (n as number) > 0 ? (n as number) : null }));
  }

  // ---- wells: drop / agg / remove ----------------------------------

  getWellFields(wellId: string): BuilderField[] {
    return this.spec().wells[wellId] ?? [];
  }

  wellDropId(wellId: string): string {
    return `well-${wellId}`;
  }

  /** All other well drop ids — used as ``cdkDropListConnectedTo`` so a
   * chip can be moved between wells of the same chart. */
  otherWellDropIds(currentId: string): string {
    return this.wells()
      .map(w => this.wellDropId(w.id))
      .filter(id => id !== this.wellDropId(currentId))
      .join(',');
  }

  onDrop(well: WellDef, ev: CdkDragDrop<BuilderField[]>): void {
    const data: ColumnInfo | BuilderField | undefined = ev.item.data;
    if (!data) return;
    this.patch(s => {
      const next = { ...s.wells };
      const list = [...(next[well.id] ?? [])];

      // Reorder within the same well.
      if (ev.previousContainer === ev.container) {
        const [item] = list.splice(ev.previousIndex, 1);
        list.splice(ev.currentIndex, 0, item);
        next[well.id] = list.slice(0, well.maxFields);
        return { ...s, wells: next };
      }

      // Move from another well — find and remove from source.
      const isFromOtherWell = ev.previousContainer.id.startsWith('well-');
      if (isFromOtherWell) {
        const fromWellId = ev.previousContainer.id.replace(/^well-/, '');
        const src = [...(next[fromWellId] ?? [])];
        src.splice(ev.previousIndex, 1);
        next[fromWellId] = src;
      }

      // Field shape — convert into a BuilderField. Three shapes can
      // arrive here:
      //   1. ColumnInfo from the source-table list (just {name, type})
      //   2. { column, table, schema } from a related-table drag —
      //      Phase F path; sets BuilderField.table so the spec
      //      compiler auto-emits the LEFT JOIN
      //   3. An existing BuilderField from another well (move/reorder)
      const anyData = data as any;
      let f: BuilderField;
      if ('column' in anyData && typeof anyData.column !== 'string' && anyData.column?.name) {
        // Shape 2 — wrapped { column: ColumnInfo, table, schema }
        f = {
          column: anyData.column.name,
          table: anyData.table ?? null,
          schema: anyData.schema ?? null,
        };
      } else if ('column' in anyData && typeof anyData.column === 'string') {
        // Shape 3 — existing BuilderField (from another well)
        f = anyData as BuilderField;
      } else {
        // Shape 1 — bare ColumnInfo from the source columns list
        f = { column: (anyData as ColumnInfo).name };
      }
      if (well.aggregated && !f.agg) {
        f.agg = this.guessDefaultAgg(f.column);
      } else if (!well.aggregated) {
        f.agg = null;
      }
      list.splice(ev.currentIndex, 0, f);
      next[well.id] = list.slice(0, well.maxFields);
      return { ...s, wells: next };
    });
  }

  setFieldAgg(wellId: string, index: number, agg: BuilderAggregation): void {
    this.patch(s => {
      const next = { ...s.wells };
      const list = [...(next[wellId] ?? [])];
      list[index] = { ...list[index], agg };
      next[wellId] = list;
      return { ...s, wells: next };
    });
  }

  /** Phase E — display format per field. Stored on BuilderField.format
   * and propagated by spec_compiler into chart_config.value_format
   * (or value_formats per-column on stat groups). */
  setFieldFormat(wellId: string, index: number, format: BuilderFormat | null): void {
    this.patch(s => {
      const next = { ...s.wells };
      const list = [...(next[wellId] ?? [])];
      list[index] = { ...list[index], format };
      next[wellId] = list;
      return { ...s, wells: next };
    });
  }

  /** Material icon name for a given format — used as the inline icon
   * on the format button so the user can read the current choice at
   * a glance without opening the menu. */
  formatIcon(f: BuilderFormat | null | undefined): string {
    return FORMATS.find(x => x.value === (f ?? null))?.icon ?? 'tag';
  }

  removeField(wellId: string, index: number): void {
    this.patch(s => {
      const next = { ...s.wells };
      const list = [...(next[wellId] ?? [])];
      list.splice(index, 1);
      next[wellId] = list;
      return { ...s, wells: next };
    });
  }

  aggLabel(a: BuilderAggregation | null | undefined): string {
    if (!a) return 'Sum';
    return AGGREGATIONS.find(x => x.value === a)?.label ?? a;
  }

  /** Pick an aggregation default by column name — ``id`` columns lean
   * to COUNT, everything else to SUM. Cheap heuristic, easily
   * overridable via the per-chip menu. */
  private guessDefaultAgg(column: string): BuilderAggregation {
    const c = column.toLowerCase();
    if (c.endsWith('id') || c === 'id') return 'COUNT';
    return 'SUM';
  }

  // ---- filters ------------------------------------------------------

  addFilter(): void {
    const firstCol = this.currentColumns()[0]?.name ?? '';
    this.patch(s => ({
      ...s,
      filters: [...(s.filters ?? []), { column: firstCol, op: '=' as BuilderFilterOp, value: '' }],
    }));
  }

  removeFilter(index: number): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      next.splice(index, 1);
      return { ...s, filters: next };
    });
  }

  setFilterColumn(index: number, column: string): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      next[index] = { ...next[index], column };
      return { ...s, filters: next };
    });
  }

  setFilterOp(index: number, op: BuilderFilterOp): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      next[index] = { ...next[index], op };
      // Reset value when op shape changes (scalar → list etc.).
      if (op === 'is_null' || op === 'is_not_null') next[index].value = null;
      else if (op === 'in' || op === 'not_in') next[index].value = '';
      else if (op === 'between') next[index].value = '';
      return { ...s, filters: next };
    });
  }

  /** Convert the typed UI value into the shape the backend expects:
   *   scalar ops → string/number passes through
   *   in / not_in → comma-split into a list
   *   between    → "a,b" → [a, b]
   *
   * For numeric-looking inputs we cast to Number so the compiler emits
   * unquoted SQL literals. */
  setFilterValueRaw(index: number, raw: string): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      const op = next[index].op;
      let value: any = raw;
      if (op === 'in' || op === 'not_in') {
        value = raw.split(',').map(v => coerce(v.trim())).filter(v => v !== '');
      } else if (op === 'between') {
        const parts = raw.split(',').map(v => coerce(v.trim()));
        value = parts.length === 2 ? parts : raw;
      } else if (op !== 'is_null' && op !== 'is_not_null') {
        value = coerce(raw);
      }
      next[index] = { ...next[index], value };
      return { ...s, filters: next };
    });
  }

  needsFilterValue(op: BuilderFilterOp): boolean {
    return op !== 'is_null' && op !== 'is_not_null';
  }

  filterValueDisplay(f: BuilderFilter): string {
    if (this.filterValueIsParam(f)) {
      return `:${(f.value as any).$param}`;
    }
    if (Array.isArray(f.value)) {
      return f.value.map(v => this.formatValueForDisplay(v)).join(',');
    }
    if (f.value == null) return '';
    return String(f.value);
  }

  /** True when the filter's value is a ``{ $param: name }`` runtime
   * reference. Drives the readonly + flash-icon styling. */
  filterValueIsParam(f: BuilderFilter): boolean {
    return f.value != null && typeof f.value === 'object'
      && !Array.isArray(f.value) && '$param' in f.value;
  }

  /** Replace the literal value with a runtime parameter reference. */
  setFilterParamRef(index: number, name: 'company_id' | 'user_id'): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      next[index] = { ...next[index], value: { $param: name } };
      return { ...s, filters: next };
    });
  }

  clearFilterParamRef(index: number): void {
    this.patch(s => {
      const next = [...(s.filters ?? [])];
      next[index] = { ...next[index], value: '' };
      return { ...s, filters: next };
    });
  }

  private formatValueForDisplay(v: any): string {
    if (v != null && typeof v === 'object' && '$param' in v) return `:${v.$param}`;
    return String(v);
  }

  // ---- helpers -----------------------------------------------------

  columnIcon(c: ColumnInfo): string {
    const t = (c.type || '').toLowerCase();
    // Phase G — derived columns surface with a calculator icon so
    // users can tell them apart from physical columns at a glance.
    if (t === 'calc') return 'functions';
    if (/(int|numeric|decimal|float|double|money|real|bigint|smallint)/.test(t)) return '123';
    if (/(date|time|timestamp)/.test(t)) return 'event';
    if (/(bit|bool)/.test(t)) return 'toggle_on';
    return 'abc';
  }

  // ---- Phase G.2 — aggregate filters (HAVING) -----------------------

  addAggregateFilter(): void {
    const firstCol = this.currentColumns()[0]?.name ?? '';
    this.patch(s => ({
      ...s,
      aggregate_filters: [
        ...(s.aggregate_filters ?? []),
        { column: firstCol, agg: 'SUM' as BuilderAggregation, op: '>' as BuilderFilterOp, value: 0 },
      ],
    }));
  }

  removeAggregateFilter(index: number): void {
    this.patch(s => {
      const next = [...(s.aggregate_filters ?? [])];
      next.splice(index, 1);
      return { ...s, aggregate_filters: next };
    });
  }

  setAggFilterColumn(index: number, column: string): void {
    this.patch(s => {
      const next = [...(s.aggregate_filters ?? [])];
      next[index] = { ...next[index], column };
      return { ...s, aggregate_filters: next };
    });
  }

  setAggFilterAgg(index: number, agg: BuilderAggregation): void {
    this.patch(s => {
      const next = [...(s.aggregate_filters ?? [])];
      next[index] = { ...next[index], agg };
      return { ...s, aggregate_filters: next };
    });
  }

  setAggFilterOp(index: number, op: BuilderFilterOp): void {
    this.patch(s => {
      const next = [...(s.aggregate_filters ?? [])];
      next[index] = { ...next[index], op };
      // Same op-shape reset rules as BuilderFilter.
      if (op === 'is_null' || op === 'is_not_null') next[index].value = null;
      else if (op === 'in' || op === 'not_in') next[index].value = '';
      else if (op === 'between') next[index].value = '';
      return { ...s, aggregate_filters: next };
    });
  }

  setAggFilterValueRaw(index: number, raw: string): void {
    this.patch(s => {
      const next = [...(s.aggregate_filters ?? [])];
      const op = next[index].op;
      let value: any = raw;
      if (op === 'in' || op === 'not_in') {
        value = raw.split(',').map(v => coerce(v.trim())).filter(v => v !== '');
      } else if (op === 'between') {
        const parts = raw.split(',').map(v => coerce(v.trim()));
        value = parts.length === 2 ? parts : raw;
      } else if (op !== 'is_null' && op !== 'is_not_null') {
        value = coerce(raw);
      }
      next[index] = { ...next[index], value };
      return { ...s, aggregate_filters: next };
    });
  }

  aggFilterValueDisplay(af: AggregateFilter): string {
    if (Array.isArray(af.value)) return af.value.join(',');
    if (af.value == null) return '';
    return String(af.value);
  }

  trackAggFilter = (i: number, _af: AggregateFilter) => i;

  // ---- Phase G — derived columns ------------------------------------

  addDerivedColumn(): void {
    this.patch(s => ({
      ...s,
      derived_columns: [...(s.derived_columns ?? []), { alias: '', expression: '' }],
    }));
  }

  removeDerivedColumn(index: number): void {
    this.patch(s => {
      const next = [...(s.derived_columns ?? [])];
      next.splice(index, 1);
      return { ...s, derived_columns: next };
    });
  }

  setDerivedAlias(index: number, alias: string): void {
    this.patch(s => {
      const next = [...(s.derived_columns ?? [])];
      // Strip whitespace + invalid identifier chars optimistically;
      // the backend's ``_ident`` is the source of truth so we don't
      // hard-fail here, just guide the user.
      next[index] = { ...next[index], alias: alias.replace(/[^A-Za-z0-9_]/g, '_') };
      return { ...s, derived_columns: next };
    });
  }

  setDerivedExpression(index: number, expression: string): void {
    this.patch(s => {
      const next = [...(s.derived_columns ?? [])];
      next[index] = { ...next[index], expression };
      return { ...s, derived_columns: next };
    });
  }

  setDerivedFormat(index: number, format: BuilderFormat | null): void {
    this.patch(s => {
      const next = [...(s.derived_columns ?? [])];
      next[index] = { ...next[index], format };
      return { ...s, derived_columns: next };
    });
  }

  trackDerived = (i: number, _d: DerivedColumn) => i;

  // ---- Help panel persistence -------------------------------------

  private static readonly HELP_KEY = 'snm.kpi.builder.help_open';

  private readHelpOpen(): boolean {
    try {
      const v = localStorage.getItem(KpiBuilderPaneComponent.HELP_KEY);
      return v == null ? true : v === '1';
    } catch {
      return true;
    }
  }

  onHelpToggle(ev: Event): void {
    const open = (ev.target as HTMLDetailsElement).open;
    this.helpOpen.set(open);
    try {
      localStorage.setItem(KpiBuilderPaneComponent.HELP_KEY, open ? '1' : '0');
    } catch { /* ignore — private mode etc. */ }
  }

  trackTable = (_: number, t: TableInfo) => this.tableKey(t);
  trackColumn = (_: number, c: ColumnInfo) => c.name;
  trackWell = (_: number, w: WellDef) => w.id;
  trackField = (_: number, f: BuilderField) => f.column + ':' + (f.agg ?? '');
  trackFilter = (i: number, _f: BuilderFilter) => i;

  /** Mutate the spec via a pure update fn and emit the change. */
  private patch(updater: (s: BuilderSpec) => BuilderSpec): void {
    const next = updater(this.spec());
    this.spec.set(next);
    this.specChange.emit(next);
  }
}

/** Coerce a typed input into a number when it looks like one, else
 * leave as the trimmed string. Empty string passes through so the
 * compiler can flag truly missing values. */
function coerce(raw: string): any {
  if (raw === '') return raw;
  if (/^-?\d+(\.\d+)?$/.test(raw)) return Number(raw);
  return raw;
}
