import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { ValueFormat, formatValue } from '../../shared/value-format';

/**
 * Counts up to a target numeric value with an ease-out ramp — like the
 * scorecard widgets in finance dashboards. Renders a plain string so it
 * drops into any layout. When the input is non-numeric (a string label,
 * a date, etc.) the component falls back to displaying it directly.
 *
 * Usage:
 *   <app-animated-number [value]="123456" />
 *   <app-animated-number [value]="rate" [decimals]="2" suffix="%" />
 */
@Component({
  selector: 'app-animated-number',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `{{ display() }}`,
  styles: [`:host { display: inline; font-variant-numeric: tabular-nums; }`],
})
export class AnimatedNumberComponent {
  private readonly destroyRef = inject(DestroyRef);

  readonly value = input<number | string | null | undefined>(null);
  /** Animation length in ms. 0 disables animation entirely. */
  readonly durationMs = input(900);
  /** Decimal places. Auto-detected from the target when omitted. */
  readonly decimals = input<number | null>(null);
  /** Optional prefix (e.g. ``$``) and suffix (e.g. ``%``). Rendered
   * verbatim around the animated number. */
  readonly prefix = input('');
  readonly suffix = input('');
  /** Phase E — value format. When set, ``formatValue`` is used instead
   * of the locale-default toLocaleString, so currency / percent /
   * short (K/M/B) all flow through the same path. */
  readonly format = input<ValueFormat | null>(null);

  /** The currently-displayed numeric value during the ramp. */
  private readonly current = signal<number>(0);

  /** Snapshot of the last-rendered numeric target — drives the effect's
   * "did the input change?" check. Without this, the effect would
   * re-trigger on every parent change-detection. */
  private lastTarget: number | null = null;
  private animationId: number | null = null;

  /** ``effectiveDecimals`` resolves the explicit input or sniffs the
   * target — integers render with 0, floats with up to 2. */
  private readonly effectiveDecimals = computed(() => {
    const explicit = this.decimals();
    if (explicit != null) return explicit;
    const v = this.value();
    return typeof v === 'number' && !Number.isInteger(v) ? 2 : 0;
  });

  readonly display = computed(() => {
    const raw = this.value();
    if (raw == null || raw === '') return '—';
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return String(raw);
    const v = this.current();
    const fmtKind = this.format();
    if (fmtKind) {
      // formatValue handles its own currency/percent/K-M-B logic;
      // skip the prefix/suffix wrap (those are for unformatted use).
      return formatValue(v, fmtKind, { decimals: this.decimals() ?? undefined });
    }
    const fmt = v.toLocaleString(undefined, {
      minimumFractionDigits: this.effectiveDecimals(),
      maximumFractionDigits: this.effectiveDecimals(),
    });
    return `${this.prefix()}${fmt}${this.suffix()}`;
  });

  constructor() {
    // Animate whenever the numeric input changes. Strings / nulls don't
    // animate — they just pass through ``display``.
    effect(() => {
      const v = this.value();
      const target = typeof v === 'number' && Number.isFinite(v) ? v : null;
      if (target === null) {
        this.cancelAnimation();
        this.lastTarget = null;
        return;
      }
      if (target === this.lastTarget) return;
      const from = this.lastTarget ?? 0;
      this.lastTarget = target;
      this.runAnimation(from, target);
    });

    // Cancel in-flight RAF when the component dies — leaking RAFs in
    // a hot dashboard adds up surprisingly fast.
    this.destroyRef.onDestroy(() => this.cancelAnimation());
  }

  private runAnimation(from: number, to: number): void {
    this.cancelAnimation();
    const dur = this.durationMs();
    if (dur <= 0 || from === to) {
      this.current.set(to);
      return;
    }
    const start = performance.now();
    const step = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / dur);
      // ease-out cubic — fast then settles, feels like a counter
      // landing rather than a linear sweep.
      const eased = 1 - Math.pow(1 - t, 3);
      this.current.set(from + (to - from) * eased);
      if (t < 1) {
        this.animationId = requestAnimationFrame(step);
      } else {
        this.animationId = null;
      }
    };
    this.animationId = requestAnimationFrame(step);
  }

  private cancelAnimation(): void {
    if (this.animationId != null) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  }
}
