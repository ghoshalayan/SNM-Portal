import {
  ChangeDetectionStrategy,
  Component,
  HostBinding,
  computed,
  input,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import {
  CHART_PALETTES,
  ChartConfig,
  ChartTheme,
  ChartType,
  ExecutionResult,
} from '../../models/schema.types';
import { AnimatedNumberComponent } from '../animated-number/animated-number.component';
import { ValueFormat, formatValue } from '../../shared/value-format';

interface BarRow { label: string; value: number; pct: number; }
interface LinePoint { x: number; y: number; label: string; }

@Component({
  selector: 'app-kpi-chart-renderer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatTableModule, AnimatedNumberComponent],
  template: `
    <ng-container [ngSwitch]="effectiveType()">
      <!-- Score card — number ramps in via AnimatedNumberComponent
           when the underlying value is numeric; falls back to plain
           string for dates, labels, etc. The format input flows
           through from the BuilderField format the author chose. -->
      <div *ngSwitchCase="'scorecard'" class="scorecard">
        <div class="value">
          <app-animated-number [value]="scorecard().raw"
                               [format]="scorecard().format" />
        </div>
        <div class="label">{{ scorecard().label }}</div>
      </div>

      <!-- Multi-stat group -->
      <div *ngSwitchCase="'stat_group'" class="stat-group">
        <div *ngFor="let s of statGroup(); let i = index"
             class="stat"
             [class.is-text]="s.isText"
             [style.animation-delay.ms]="i * 80">
          <div class="value" [title]="s.isText && s.raw ? s.raw : null">
            <app-animated-number [value]="s.raw" [format]="s.format" />
          </div>
          <div class="label">{{ s.label }}</div>
        </div>
      </div>

      <!-- Bar chart (SVG) -->
      <div *ngSwitchCase="'bar'" class="bar-chart">
        <header class="axis-titles" *ngIf="xLabel() || yLabel()">
          <span class="axis-x-name" *ngIf="xLabel()">{{ xLabel() }}</span>
          <span class="axis-y-name" *ngIf="yLabel()">{{ yLabel() }}</span>
        </header>
        <div *ngFor="let r of barRows(); let i = index" class="bar-row">
          <span class="bar-label" [title]="r.label">{{ r.label }}</span>
          <span class="bar-track">
            <span class="bar-fill"
                  [style.width.%]="r.pct"
                  [style.background]="palette()[i % palette().length]"></span>
          </span>
          <span class="bar-value">{{ formatBarValue(r.value) }}</span>
        </div>
        <p *ngIf="!barRows().length" class="empty">No data.</p>
      </div>

      <!-- Pie chart -->
      <div *ngSwitchCase="'pie'" class="pie-chart">
        <svg viewBox="-1 -1 2 2" class="pie-svg">
          <g [attr.transform]="'rotate(-90)'">
            <path *ngFor="let s of pieSlices(); let i = index"
                  [attr.d]="s.path"
                  [attr.fill]="palette()[i % palette().length]"
                  [attr.stroke]="'var(--snm-bg-card, white)'"
                  stroke-width="0.01"/>
          </g>
        </svg>
        <ul class="legend">
          <li *ngFor="let s of pieSlices(); let i = index">
            <span class="dot" [style.background]="palette()[i % palette().length]"></span>
            {{ s.label }} — {{ formatNumber(s.value) }} ({{ (s.pct * 100) | number: '1.0-1' }}%)
          </li>
        </ul>
      </div>

      <!-- Line chart (SVG) -->
      <div *ngSwitchCase="'line'" class="line-chart">
        <header class="axis-titles" *ngIf="xLabel() || yLabel()">
          <span class="axis-x-name" *ngIf="xLabel()">{{ xLabel() }}</span>
          <span class="axis-y-name" *ngIf="yLabel()">{{ yLabel() }}</span>
        </header>
        <div class="line-body">
          <!-- Y-axis tick column. Tick values are evenly spaced
               between min and max — three ticks read cleanly without
               cluttering tiny cards. -->
          <div class="y-ticks" *ngIf="line().tickValues.length">
            <span *ngFor="let t of line().tickValues">{{ formatBarValue(t) }}</span>
          </div>
          <svg [attr.viewBox]="line().viewBox" preserveAspectRatio="none" class="line-svg">
            <polyline [attr.points]="line().points"
                      fill="none" [attr.stroke]="palette()[0]" stroke-width="1.4"/>
            <circle *ngFor="let p of line().points2"
                    [attr.cx]="p.x" [attr.cy]="p.y" r="1.6"
                    [attr.fill]="palette()[0]"/>
          </svg>
        </div>
        <div class="line-axis">
          <span>{{ line().firstLabel }}</span>
          <span>{{ line().lastLabel }}</span>
        </div>
      </div>

      <!-- Table fallback -->
      <div *ngSwitchDefault class="table-wrap">
        <table mat-table [dataSource]="tableRows()" class="kpi-table">
          <ng-container *ngFor="let col of result()?.columns ?? []" [matColumnDef]="col">
            <th mat-header-cell *matHeaderCellDef>{{ col }}</th>
            <td mat-cell *matCellDef="let row">{{ row[col] }}</td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="result()?.columns ?? []"></tr>
          <tr mat-row *matRowDef="let row; columns: result()?.columns ?? []"></tr>
        </table>
        <p *ngIf="!result() || !result()!.rows.length" class="empty">No rows.</p>
      </div>
    </ng-container>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      width: 100%; height: 100%;
      /* Each chart fills the card cell instead of sitting at content
       * size. Empty space inside a tall card was reading as a "gap
       * between cards"; stretching means the chart uses the height
       * the user dragged it to. Chart wrappers that may overflow
       * (table, bar chart, line, pie legend) get their own scroll so
       * data is never clipped — vertical for tall lists, horizontal
       * for wide tables. */
    }
    .scorecard, .stat-group, .bar-chart, .pie-chart, .line-chart, .table-wrap {
      flex: 1 1 auto;
      min-height: 0;
      width: 100%;
    }
    /* Overflow handling per chart type:
       - bar-chart / line-chart: vertical scroll if many rows / dense */
    .bar-chart {
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2)) transparent;
    }
    /* table-wrap already has overflow: auto (max-height + scroll), but
       inside a flex parent we drop the max-height and let the parent
       constrain so wide tables also scroll horizontally. */
    .table-wrap {
      overflow: auto;
      max-height: none;
      scrollbar-width: thin;
      scrollbar-color: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2)) transparent;
    }
    .bar-chart::-webkit-scrollbar,
    .table-wrap::-webkit-scrollbar { width: 6px; height: 6px; }
    .bar-chart::-webkit-scrollbar-thumb,
    .table-wrap::-webkit-scrollbar-thumb {
      background: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2));
      border-radius: 3px;
    }
    .bar-chart::-webkit-scrollbar-thumb:hover,
    .table-wrap::-webkit-scrollbar-thumb:hover {
      background: var(--snm-scrollbar-thumb-hover, rgba(100, 140, 200, 0.35));
    }
    /* Default theme. Inner surfaces use the portal's accent-subtle +
     * border-divider tokens so they harmonize with header rows,
     * pills, and chips elsewhere in the app — instead of the heavy
     * "glass-on-glass" treatment that read as washed-out grey. */
    :host {
      --kpi-bg: transparent;
      --kpi-bg-soft: var(--snm-accent-subtle, rgba(91, 143, 217, 0.08));
      --kpi-text: var(--snm-text-primary, #222);
      --kpi-text-muted: var(--snm-text-muted, #888);
      --kpi-accent: var(--snm-accent, #4a90e2);
      --kpi-border: var(--snm-border-divider, rgba(26, 58, 92, 0.1));
    }
    /* Dark theme — independent of host theme; flat surfaces, neon accent. */
    :host([data-theme="dark"]) {
      --kpi-bg: #1f2229;
      --kpi-bg-soft: #2a2e36;
      --kpi-text: #eef0f3;
      --kpi-text-muted: #a8aab2;
      --kpi-accent: #4dd0e1;
      --kpi-border: #2d3038;
      color: var(--kpi-text);
      background: var(--kpi-bg);
      border-radius: 6px;
      padding: 4px;
    }
    /* Vibrant — saturated accent + bigger value typography. */
    :host([data-theme="vibrant"]) {
      --kpi-accent: #ff6b6b;
      --kpi-bg-soft: #fff5f5;
    }
    :host([data-theme="vibrant"]) .scorecard .value { font-size: 2.8rem; font-weight: 800; }
    :host([data-theme="vibrant"]) .stat-group .value { font-size: 1.5rem; }
    /* Minimal — monochrome, thinner lines. */
    :host([data-theme="minimal"]) {
      --kpi-accent: #555;
      --kpi-bg-soft: #fafafa;
    }
    :host([data-theme="minimal"]) .scorecard .value { font-weight: 500; }
    :host([data-theme="minimal"]) .bar-track { background: #eeeeee; }

    /* Animations — applied only when [data-anim="on"]. CSS-only so the
       bundle stays light; element-by-element delays make the load feel
       choreographed rather than a single fade-in. */
    @keyframes kpi-fade-in {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: none; }
    }
    @keyframes kpi-bar-grow {
      from { transform: scaleX(0); }
      to { transform: scaleX(1); }
    }
    @keyframes kpi-pop {
      0%   { transform: scale(0.9); opacity: 0; }
      60%  { transform: scale(1.04); opacity: 1; }
      100% { transform: scale(1); }
    }
    @keyframes kpi-pie-spin-in {
      from { transform: rotate(-90deg) scale(0.6); opacity: 0; }
      to   { transform: rotate(0deg)   scale(1);   opacity: 1; }
    }
    @keyframes kpi-line-draw {
      from { stroke-dashoffset: 1000; }
      to   { stroke-dashoffset: 0; }
    }
    @keyframes kpi-line-pop {
      from { transform: scale(0); opacity: 0; }
      to   { transform: scale(1); opacity: 1; }
    }
    :host([data-anim="on"]) .scorecard,
    :host([data-anim="on"]) .pie-chart,
    :host([data-anim="on"]) .line-chart,
    :host([data-anim="on"]) .table-wrap {
      animation: kpi-fade-in 360ms ease both;
    }
    :host([data-anim="on"]) .scorecard .value {
      animation: kpi-pop 520ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
    }
    /* Stat group — staggered fade so each stat lands a beat after the
       previous, like a sequenced reveal. inline-style sets per-stat delay. */
    :host([data-anim="on"]) .stat-group .stat {
      animation: kpi-fade-in 320ms ease both;
    }
    /* Bar chart — each row drops in from above, then the fill grows.
       Stagger via nth-child so multi-bar charts cascade. */
    :host([data-anim="on"]) .bar-row {
      animation: kpi-fade-in 280ms ease both;
    }
    :host([data-anim="on"]) .bar-row:nth-child(1)  { animation-delay: 0ms; }
    :host([data-anim="on"]) .bar-row:nth-child(2)  { animation-delay: 60ms; }
    :host([data-anim="on"]) .bar-row:nth-child(3)  { animation-delay: 120ms; }
    :host([data-anim="on"]) .bar-row:nth-child(4)  { animation-delay: 180ms; }
    :host([data-anim="on"]) .bar-row:nth-child(5)  { animation-delay: 240ms; }
    :host([data-anim="on"]) .bar-row:nth-child(6)  { animation-delay: 300ms; }
    :host([data-anim="on"]) .bar-row:nth-child(7)  { animation-delay: 360ms; }
    :host([data-anim="on"]) .bar-row:nth-child(8)  { animation-delay: 420ms; }
    :host([data-anim="on"]) .bar-row:nth-child(n+9) { animation-delay: 480ms; }

    :host([data-anim="on"]) .bar-fill {
      transform-origin: left center;
      animation: kpi-bar-grow 700ms cubic-bezier(0.4, 0, 0.2, 1) both;
      animation-delay: 220ms;
    }
    /* Pie — spins in from a smaller scale, slices stagger so the wheel
       feels like it's assembling. */
    :host([data-anim="on"]) .pie-svg {
      animation: kpi-pie-spin-in 600ms cubic-bezier(0.2, 0, 0, 1) both;
    }
    :host([data-anim="on"]) .pie-chart .legend li {
      animation: kpi-fade-in 280ms ease both;
    }
    :host([data-anim="on"]) .pie-chart .legend li:nth-child(1) { animation-delay: 200ms; }
    :host([data-anim="on"]) .pie-chart .legend li:nth-child(2) { animation-delay: 260ms; }
    :host([data-anim="on"]) .pie-chart .legend li:nth-child(3) { animation-delay: 320ms; }
    :host([data-anim="on"]) .pie-chart .legend li:nth-child(4) { animation-delay: 380ms; }
    :host([data-anim="on"]) .pie-chart .legend li:nth-child(n+5) { animation-delay: 440ms; }

    /* Line chart — polyline draws in from left, points pop after. */
    :host([data-anim="on"]) .line-svg polyline {
      stroke-dasharray: 1000;
      animation: kpi-line-draw 900ms cubic-bezier(0.4, 0, 0.2, 1) both;
    }
    :host([data-anim="on"]) .line-svg circle {
      transform-box: fill-box;
      transform-origin: center;
      animation: kpi-line-pop 320ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
      animation-delay: 700ms;
    }

    .empty { color: var(--kpi-text-muted); font-style: italic; padding: 12px; }

    /* Scorecard — value gets a subtle accent gradient so the headline
       number reads as the focal point even at small card sizes. */
    .scorecard {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 16px 24px; min-height: 120px;
      width: 100%;
      .value {
        font-size: 2.6rem; font-weight: 700; line-height: 1.1;
        background: linear-gradient(135deg,
          var(--kpi-accent) 0%,
          color-mix(in srgb, var(--kpi-accent) 70%, var(--snm-text-primary)) 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
      }
      .label {
        color: var(--kpi-text-muted); margin-top: 8px;
        font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em;
      }
    }

    .stat-group {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px; padding: 4px;
      width: 100%;
      .stat {
        background: var(--kpi-bg-soft);
        border: 1px solid var(--kpi-border);
        padding: 14px 12px; border-radius: 10px; text-align: center;
        // Allow the tile to shrink past its intrinsic content width
        // so a long string value can be ellipsised instead of forcing
        // the grid column to grow and break the layout.
        min-width: 0;
        overflow: hidden;
        transition:
          transform 200ms cubic-bezier(0.2, 0, 0, 1),
          border-color 200ms ease,
          background 200ms ease;
        &:hover {
          transform: translateY(-1px);
          border-color: var(--kpi-accent);
          background: color-mix(in srgb, var(--kpi-accent) 12%, var(--kpi-bg-soft));
        }
      }
      .value {
        font-size: 1.4rem; font-weight: 700;
        color: var(--kpi-text);
        letter-spacing: -0.01em;
        // Generic safety: long numeric formats shouldn't blow the tile
        // either — keep them on one line with mid-word break if they do.
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
      }
      // Non-numeric stat values (e.g. a username column accidentally
      // rendered in a stat-group) shouldn't use the giant numeric
      // typography — drop to a normal-readable size, allow up to two
      // lines, then truncate with ellipsis. The native title attr
      // shows the full value on hover.
      .stat.is-text .value {
        font-size: 0.95rem;
        font-weight: 600;
        line-height: 1.25;
        white-space: normal;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        line-clamp: 2;
        -webkit-box-orient: vertical;
        word-break: break-word;
      }
      .label {
        color: var(--kpi-text-muted); font-size: 0.72rem;
        margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    /* Axis titles — header strip above bar / line charts. The y-name
       sits on the right so it visually anchors the value column. */
    .axis-titles {
      display: flex; justify-content: space-between; align-items: baseline;
      padding: 0 4px 4px;
      font-size: 0.7rem; color: var(--kpi-text-muted);
      text-transform: uppercase; letter-spacing: 0.06em;
      border-bottom: 1px solid var(--snm-border-divider, rgba(0, 0, 0, 0.08));
      margin-bottom: 6px;
      flex: 0 0 auto;
    }
    .axis-x-name, .axis-y-name { font-weight: 600; }

    /* Bar chart.
       The value column is auto-sized (not fixed-width) and the row has
       min-width:0 on the track so the layout never overflows the card
       body's overflow:hidden boundary. A 6px right padding keeps full
       values clear of the right edge. */
    .bar-chart {
      padding: 8px 6px 8px 4px;
      display: flex; flex-direction: column; gap: 8px;
      width: 100%; box-sizing: border-box;
      min-width: 0;
    }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(60px, 120px) minmax(40px, 1fr) auto;
      align-items: center;
      gap: 10px; font-size: 0.85rem;
      min-width: 0;
    }
    .bar-label {
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      color: var(--kpi-text-muted);
      font-size: 0.78rem;
      min-width: 0;
    }
    .bar-track {
      height: 16px; background: var(--kpi-bg-soft);
      border: 1px solid var(--snm-glass-border-light, rgba(255, 255, 255, 0.3));
      border-radius: 8px;
      overflow: hidden; position: relative;
      min-width: 0;
    }
    .bar-fill {
      display: block; height: 100%;
      border-radius: 7px;
      box-shadow: 0 0 8px color-mix(in srgb, var(--kpi-accent) 35%, transparent);
      transition: width 200ms ease;
    }
    .bar-value {
      text-align: right; color: var(--kpi-text);
      font-variant-numeric: tabular-nums;
      font-weight: 600; font-size: 0.82rem;
      padding-left: 4px;
      white-space: nowrap;
      min-width: 28px;
    }

    /* Pie chart.
       Two-column grid: fixed-width SVG on the left, scrollable legend
       on the right. The host-level :host gives us a height; we forward
       that to the grid via min-height:0 + overflow:hidden so a long
       legend can't push the SVG out of the card. The legend itself
       owns its overflow with overflow-y:auto — that's what keeps
       high-cardinality categories (e.g. dia-wise breakdowns with 15+
       slices) readable instead of bursting the chart. */
    .pie-chart {
      display: grid; grid-template-columns: minmax(0, 200px) minmax(0, 1fr);
      gap: 20px; padding: 8px;
      align-items: stretch; width: 100%;
      min-height: 0;
      overflow: hidden;
    }
    .pie-svg {
      width: 100%; max-width: 200px; height: auto; aspect-ratio: 1;
      align-self: center;
      filter: drop-shadow(0 4px 12px var(--snm-glass-shadow-light, rgba(0, 0, 0, 0.08)));
    }
    .legend {
      list-style: none; padding: 0 4px 0 0; margin: 0; font-size: 0.82rem;
      display: flex; flex-direction: column; gap: 6px;
      color: var(--kpi-text);
      overflow-y: auto;
      min-height: 0;
      max-height: 100%;
      align-self: stretch;
      scrollbar-width: thin;
      scrollbar-color: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2)) transparent;
    }
    .legend::-webkit-scrollbar { width: 6px; }
    .legend::-webkit-scrollbar-thumb {
      background: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2));
      border-radius: 3px;
    }
    .legend::-webkit-scrollbar-thumb:hover {
      background: var(--snm-scrollbar-thumb-hover, rgba(100, 140, 200, 0.35));
    }
    .legend li {
      display: flex; align-items: center;
      padding: 4px 8px; border-radius: 6px;
      transition: background 160ms ease;
      flex: 0 0 auto;
      &:hover { background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.08)); }
    }
    .legend .dot {
      display: inline-block; width: 10px; height: 10px;
      border-radius: 50%; margin-right: 8px; vertical-align: middle;
      flex: 0 0 auto;
      box-shadow: 0 0 6px currentColor;
    }

    /* Line chart — y-tick column floats to the left of the SVG so
       readers can scan the value scale (Power BI–style). */
    .line-chart {
      padding: 8px; width: 100%;
      display: flex; flex-direction: column;
    }
    .line-body {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 8px;
      flex: 1; min-height: 0;
    }
    .y-ticks {
      display: flex; flex-direction: column; justify-content: space-between;
      font-size: 0.68rem; color: var(--kpi-text-muted);
      font-variant-numeric: tabular-nums;
      padding: 2px 0;
      min-width: 32px;
      text-align: right;
    }
    .line-svg {
      width: 100%; height: 100%; min-height: 140px; display: block;
      background: var(--kpi-bg-soft);
      border: 1px solid var(--snm-glass-border-light, rgba(255, 255, 255, 0.3));
      border-radius: 8px;
    }
    .line-axis {
      display: flex; justify-content: space-between;
      font-size: 0.72rem; color: var(--kpi-text-muted); margin-top: 6px;
      text-transform: uppercase; letter-spacing: 0.05em;
      padding-left: 40px; /* line up under the SVG, past the y-ticks */
    }

    /* Table — overflow: auto + max-height: none set higher up so the
       table scrolls inside the card cell (no fixed pixel max). */
    .table-wrap {
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--snm-glass-border-light, rgba(255, 255, 255, 0.3));
    }
    .kpi-table { width: 100%; background: transparent !important; }
    .kpi-table th {
      background: var(--snm-bg-header-row, rgba(100, 140, 200, 0.08)) !important;
      color: var(--kpi-text) !important;
      font-weight: 600; font-size: 0.78rem;
      text-transform: uppercase; letter-spacing: 0.05em;
    }
    .kpi-table td {
      color: var(--kpi-text) !important;
      font-size: 0.85rem;
    }
    .kpi-table tr:hover td {
      background: var(--snm-bg-row-hover, rgba(100, 140, 200, 0.06)) !important;
    }
  `],
})
export class ChartRendererComponent {
  readonly result = input<ExecutionResult | null>(null);
  readonly chartConfig = input<ChartConfig | null>(null);

  /** Active theme — read by the host bindings + palette computation. */
  readonly theme = computed<ChartTheme>(
    () => (this.chartConfig()?.style?.theme as ChartTheme) || 'default',
  );

  /** Animation toggle — drives the [data-anim] host binding. */
  readonly animationsOn = computed(
    () => this.chartConfig()?.style?.animations !== false,
  );

  /** Palette resolved from theme; pie / line / multi-bar charts cycle through. */
  readonly palette = computed<string[]>(
    () => CHART_PALETTES[this.theme()] ?? CHART_PALETTES.default,
  );

  // Host bindings — Angular sticks ``data-theme`` and ``data-anim`` on
  // the component element, which the styles above target via attribute
  // selectors. No lifecycle hook needed; they recompute via the signals.
  @HostBinding('attr.data-theme')
  get themeAttr(): string {
    return this.theme();
  }

  @HostBinding('attr.data-anim')
  get animAttr(): string {
    return this.animationsOn() ? 'on' : 'off';
  }

  /** The chart type to actually render (config override → suggestion → table). */
  readonly effectiveType = computed<ChartType>(() => {
    const cfg = this.chartConfig();
    if (cfg?.type) return cfg.type;
    return this.result()?.suggestion?.type ?? 'table';
  });

  private readonly cfg = computed<Record<string, any>>(() => {
    return this.chartConfig()?.config ?? this.result()?.suggestion?.config ?? {};
  });

  /** Phase E — axis-name accessors. Builder-mode KPIs ship the
   * underlying column name through ``x_label`` / ``y_label``;
   * raw-SQL KPIs may set them by hand or leave them blank. We fall
   * back to a humanised version of the underlying column name so
   * even uncurated KPIs read sensibly instead of showing a blank
   * axis title. */
  readonly xLabel = computed<string>(() => {
    const explicit = this.cfg()['x_label'];
    if (explicit) return explicit;
    const r = this.result();
    const cfg = this.cfg();
    const col = cfg['category_column'] ?? r?.columns?.[0];
    return col ? this.humanizeLabel(col) : '';
  });
  readonly yLabel = computed<string>(() => {
    const explicit = this.cfg()['y_label'];
    if (explicit) return explicit;
    const r = this.result();
    const cfg = this.cfg();
    const col = cfg['value_column']
      ?? (r?.columns ?? []).find((_, i) => i !== (r?.columns ?? []).indexOf(cfg['category_column'] ?? r?.columns?.[0]))
      ?? r?.columns?.[1];
    return col ? this.humanizeLabel(col) : '';
  });
  readonly valueFormat = computed<ValueFormat>(
    () => (this.cfg()['value_format'] as ValueFormat) || 'number',
  );

  /** Format a bar / line value through the user-chosen format,
   * defaulting to short (K/M/B) for numeric so wide values don't
   * push the value column off-card. */
  formatBarValue(v: any): string {
    const fmt = this.valueFormat();
    // Default to ``short`` when the author didn't specify, since bar
    // value columns are tight on space.
    return formatValue(v, fmt === 'number' ? 'short' : fmt);
  }

  readonly tableRows = computed(() => {
    const r = this.result();
    if (!r) return [];
    return r.rows.map(row => Object.fromEntries(r.columns.map((c, i) => [c, row[i]])));
  });

  readonly scorecard = computed(() => {
    const r = this.result();
    const cfg = this.cfg();
    if (!r || !r.rows.length) {
      return { raw: null as number | string | null, label: '', format: null as ValueFormat | null };
    }
    const valueCol = cfg['value_column'] ?? r.columns[0];
    const labelCol = cfg['label_column'] ?? cfg['value_label'];
    const idx = r.columns.indexOf(valueCol);
    const raw = idx >= 0 ? r.rows[0][idx] : r.rows[0][0];
    return {
      // Pass numbers through verbatim so AnimatedNumberComponent can
      // ramp them in; non-numeric values render as plain text.
      raw: this.coerceForAnimation(raw),
      label: this.humanizeLabel(labelCol ?? valueCol ?? ''),
      format: (cfg['value_format'] as ValueFormat | null) ?? null,
    };
  });

  readonly statGroup = computed(() => {
    const r = this.result();
    const cfg = this.cfg();
    if (!r || !r.rows.length) return [] as Array<{ label: string; raw: any; format: ValueFormat | null; isText: boolean }>;
    const cols: string[] = cfg['value_columns'] ?? r.columns;
    const formats: Record<string, ValueFormat> = cfg['value_formats'] ?? {};
    const labels: Record<string, string> = cfg['value_labels'] ?? {};
    return cols.map(c => {
      const idx = r.columns.indexOf(c);
      const raw = idx >= 0 ? r.rows[0][idx] : null;
      const coerced = this.coerceForAnimation(raw);
      return {
        label: labels[c] ?? this.humanizeLabel(c),
        raw: coerced,
        format: (formats[c] as ValueFormat | null) ?? null,
        // ``isText`` lets the template drop the giant-numeric typography
        // for string values (e.g. usernames) which otherwise wrap and
        // burst the tile when stat-group is misused with non-numeric
        // columns.
        isText: typeof coerced === 'string',
      };
    });
  });

  /**
   * Cryptic column names like ``enqid_count``, ``enquiriesconvertedtoquotations``,
   * or ``username`` are common when an LLM-generated KPI doesn't supply
   * an explicit ``value_label``. This converts them into something
   * readable: snake_case / kebab-case / camelCase split into words,
   * Title-Cased, with a small allowlist of acronyms left ALL-CAPS so
   * domain terms (ID, GST, PAN, FY, PO, KPI, SQL, MM, MT, KG, NOS,
   * IGST, CGST, SGST, GSTN, MOU, TPW, SWE, OHD, IFC, CRS, CD, JC)
   * survive un-mangled.
   */
  humanizeLabel(raw: string): string {
    if (!raw) return '';
    const s = String(raw).trim();
    if (!s) return '';
    // 1. Insert spaces between snake_case / kebab-case / camelCase boundaries.
    const spaced = s
      .replace(/[_-]+/g, ' ')
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
      .trim();
    if (!spaced) return s;
    // 2. Title-case each word, but keep known abbreviations capitalised.
    const ACRONYMS = new Set([
      'ID', 'IDS', 'GST', 'PAN', 'FY', 'PO', 'KPI', 'KPIS', 'SQL', 'API',
      'URL', 'UI', 'UX', 'NOS', 'MM', 'MT', 'KG', 'IGST', 'CGST', 'SGST',
      'GSTN', 'MOU', 'TPW', 'SWE', 'OHD', 'IFC', 'CRS', 'CD', 'JC', 'TOD',
      'HOD', 'KRO', 'TNC', 'YTD', 'MTD', 'QTD', 'COGS', 'GRR', 'NRR',
    ]);
    return spaced
      .split(/\s+/)
      .map(word => {
        const upper = word.toUpperCase();
        if (ACRONYMS.has(upper)) return upper;
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
      })
      .join(' ');
  }

  /** Convert "looks numeric" strings (e.g. ``"42"``) into actual
   * numbers so the count-up animation kicks in. Anything else passes
   * through unchanged for the fallback text path. */
  private coerceForAnimation(v: any): number | string | null {
    if (v == null || v === '') return null;
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
      const n = Number(v);
      if (Number.isFinite(n) && v.trim() !== '') return n;
    }
    return String(v);
  }

  readonly barRows = computed<BarRow[]>(() => {
    const r = this.result();
    const cfg = this.cfg();
    if (!r) return [];
    const catCol = cfg['category_column'] ?? r.columns[0];
    const valCol = cfg['value_column'] ?? r.columns.find((_, i) => i !== r.columns.indexOf(catCol)) ?? r.columns[1];
    const ci = r.columns.indexOf(catCol);
    const vi = r.columns.indexOf(valCol);
    if (ci < 0 || vi < 0) return [];
    const rows = r.rows.map(row => ({
      label: String(row[ci] ?? ''),
      value: Number(row[vi] ?? 0),
    }));
    const max = rows.reduce((m, r) => Math.max(m, Math.abs(r.value)), 0) || 1;
    return rows.map(r => ({ ...r, pct: (Math.abs(r.value) / max) * 100 }));
  });

  readonly pieSlices = computed(() => {
    const r = this.result();
    const cfg = this.cfg();
    if (!r) return [];
    const catCol = cfg['category_column'] ?? r.columns[0];
    const valCol = cfg['value_column'] ?? r.columns[1];
    const ci = r.columns.indexOf(catCol);
    const vi = r.columns.indexOf(valCol);
    if (ci < 0 || vi < 0) return [];
    const data = r.rows.map(row => ({
      label: String(row[ci] ?? ''),
      value: Math.max(0, Number(row[vi] ?? 0)),
    }));
    const total = data.reduce((s, d) => s + d.value, 0) || 1;
    let cumulative = 0;
    return data.map(d => {
      const pct = d.value / total;
      const start = cumulative * Math.PI * 2;
      cumulative += pct;
      const end = cumulative * Math.PI * 2;
      const large = pct > 0.5 ? 1 : 0;
      const x1 = Math.cos(start), y1 = Math.sin(start);
      const x2 = Math.cos(end), y2 = Math.sin(end);
      const path = `M 0 0 L ${x1} ${y1} A 1 1 0 ${large} 1 ${x2} ${y2} Z`;
      return { ...d, pct, path };
    });
  });

  readonly line = computed(() => {
    const r = this.result();
    const cfg = this.cfg();
    if (!r || r.rows.length < 2) {
      return { viewBox: '0 0 100 50', points: '', points2: [] as LinePoint[],
               firstLabel: '', lastLabel: '', tickValues: [] as number[] };
    }
    const xCol = cfg['x_column'] ?? r.columns[0];
    const yCol = cfg['y_column'] ?? r.columns[1];
    const xi = r.columns.indexOf(xCol);
    const yi = r.columns.indexOf(yCol);
    const ys = r.rows.map(row => Number(row[yi] ?? 0));
    const min = Math.min(...ys), max = Math.max(...ys);
    const range = max - min || 1;
    const w = 100, h = 50;
    const stepX = w / (r.rows.length - 1);
    const points2 = r.rows.map((row, i) => ({
      x: i * stepX,
      y: h - ((Number(row[yi] ?? 0) - min) / range) * h,
      label: String(row[xi] ?? ''),
    }));
    // Three evenly-spaced y-ticks: max at top, min at bottom, midpoint
    // between. Reads as a Power BI–style mini scale.
    const tickValues = [max, (max + min) / 2, min];
    return {
      viewBox: `0 0 ${w} ${h}`,
      points: points2.map(p => `${p.x},${p.y}`).join(' '),
      points2,
      firstLabel: points2[0]?.label ?? '',
      lastLabel: points2[points2.length - 1]?.label ?? '',
      tickValues,
    };
  });

  formatNumber(v: any): string {
    if (v == null) return '—';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return v.toLocaleString();
      return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return String(v);
  }
}
