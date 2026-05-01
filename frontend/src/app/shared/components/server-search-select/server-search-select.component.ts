import {
  Component, EventEmitter, Input, OnDestroy, OnInit, Output,
  ViewChild, forwardRef, ChangeDetectorRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonModule } from '@angular/material/button';
import { ScrollingModule, CdkVirtualScrollViewport } from '@angular/cdk/scrolling';
import { A11yModule } from '@angular/cdk/a11y';
// OverlayModule kept in imports — virtual-scroll viewport pulls some of its
// types via the cdk transitive dep. Removing it does no harm but adds risk
// of subtle peer-dep mismatch; leaving it is a no-op at runtime.
import { OverlayModule } from '@angular/cdk/overlay';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, takeUntil } from 'rxjs/operators';

import { ApiService } from '../../../core/services/api.service';

export interface SearchItem {
  id: number;
  label: string;
  sub?: string | null;
  [k: string]: any;   // allow extra fields from specific endpoints
}

interface SearchResponse {
  items: SearchItem[];
  nextCursor: string | null;
  hasMore: boolean;
}

/**
 * Server-side search dropdown with infinite scroll + virtual scrolling.
 *
 * Scales to unlimited rows because:
 * - Queries backend on every keystroke (debounced 300ms)
 * - Cursor-pagination: fetches 50 items at a time as user scrolls
 * - Virtual scroll: renders only visible DOM nodes
 * - switchMap cancels stale requests
 *
 * Usage:
 *   <app-server-search-select
 *     endpoint="/customers/search"
 *     placeholder="Search customers..."
 *     [(ngModel)]="selectedId"
 *     (selectionChange)="onCustomerChange($event)">
 *   </app-server-search-select>
 */
@Component({
  selector: 'app-server-search-select',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatFormFieldModule, MatInputModule, MatIconModule,
    MatProgressSpinnerModule, MatButtonModule,
    ScrollingModule, A11yModule, OverlayModule,
  ],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => ServerSearchSelectComponent),
      multi: true,
    },
  ],
  template: `
    <div class="sss-root" [class.disabled]="disabled" [class.is-open]="isOpen">
      <mat-form-field appearance="outline" class="sss-field">
        <mat-label>{{ label || placeholder }}</mat-label>

        <!-- Display field — shows selected item's label or search input -->
        <input
          matInput
          type="text"
          [value]="isOpen ? searchText : (displayLabel || '')"
          [placeholder]="placeholder"
          [disabled]="disabled"
          (focus)="onFocus()"
          (input)="onInput($event)"
          (keydown)="onKeyDown($event)"
          autocomplete="off"
          #inputEl />

        <!-- Clear button -->
        <button mat-icon-button matSuffix
          *ngIf="selectedItem && !disabled && !required && !isOpen"
          (click)="clearSelection($event)"
          type="button"
          matTooltip="Clear"
          aria-label="Clear selection">
          <mat-icon>close</mat-icon>
        </button>

        <mat-icon matSuffix *ngIf="!selectedItem || isOpen">search</mat-icon>

        <mat-hint *ngIf="hint">{{ hint }}</mat-hint>
      </mat-form-field>

      <!-- Dropdown panel — absolutely positioned beneath the input.
           Visibility relies on global CSS (styles.scss) forcing
           overflow:visible on any mat-card containing app-server-search-select,
           plus this host's z-index lift while open. -->
      <div class="sss-panel" *ngIf="isOpen" (mousedown)="$event.preventDefault()">
        <div class="sss-state" *ngIf="loading && items.length === 0">
          <mat-spinner diameter="20"></mat-spinner>
          <span>Searching...</span>
        </div>

        <div class="sss-state" *ngIf="!loading && items.length === 0 && searchText.length >= minSearchLength">
          <mat-icon>search_off</mat-icon>
          <span>No results for "{{ searchText }}"</span>
        </div>

        <div class="sss-state hint" *ngIf="!loading && items.length === 0 && searchText.length < minSearchLength">
          <mat-icon>keyboard</mat-icon>
          <span>Type at least {{ minSearchLength }} character{{ minSearchLength > 1 ? 's' : '' }} to search</span>
        </div>

        <cdk-virtual-scroll-viewport
          *ngIf="items.length > 0"
          itemSize="52"
          class="sss-viewport"
          (scrolledIndexChange)="onScrollIndexChange($event)">
          <div
            *cdkVirtualFor="let item of items; let i = index"
            class="sss-item"
            [class.active]="i === activeIndex"
            [class.selected]="item.id === value"
            (click)="select(item)"
            (mouseenter)="activeIndex = i">
            <div class="sss-label">{{ item.label }}</div>
            <div class="sss-sub" *ngIf="item.sub">{{ item.sub }}</div>
          </div>
        </cdk-virtual-scroll-viewport>

        <div class="sss-loading-more" *ngIf="loading && items.length > 0">
          <mat-spinner diameter="16"></mat-spinner>
          <span>Loading more...</span>
        </div>
      </div>

      <!-- Backdrop to close on outside click -->
      <div class="sss-backdrop" *ngIf="isOpen" (click)="close()"></div>
    </div>
  `,
  styles: [`
    :host { display: block; position: relative; }
    /* Lift the host's stacking context while the dropdown is open so the
       absolutely-positioned panel sits above any sibling card on the page.
       Reverts to the natural document order when closed. */
    :host(.is-open),
    :host:has(.sss-root.is-open) { z-index: 1100; }
    .sss-root { position: relative; }
    .sss-root.is-open { z-index: 1100; }
    .sss-field { width: 100%; }

    .sss-backdrop {
      position: fixed; inset: 0; z-index: 1000; background: transparent;
    }

    .sss-panel {
      position: absolute; top: 100%; left: 0; right: 0;
      z-index: 1101;
      background: var(--snm-glass-bg-solid, #fff);
      border: 1px solid var(--snm-border-divider, rgba(0,0,0,.12));
      border-radius: 6px;
      box-shadow: 0 8px 32px rgba(0,0,0,.15);
      max-height: 320px; overflow: hidden;
      display: flex; flex-direction: column;
      margin-top: -18px;  /* overlap hint row */
    }

    .sss-state {
      display: flex; align-items: center; gap: 10px;
      padding: 20px 16px; color: var(--snm-text-muted, rgba(0,0,0,.6));
      font-size: 13px;
      &.hint { color: var(--snm-text-muted, rgba(0,0,0,.5)); font-style: italic; }
      mat-icon { font-size: 20px; width: 20px; height: 20px; opacity: .7; }
    }

    .sss-viewport {
      flex: 1; min-height: 260px;
    }

    .sss-item {
      padding: 8px 14px;
      cursor: pointer;
      border-bottom: 1px solid var(--snm-border-divider, rgba(0,0,0,.06));
      transition: background 0.1s;
      &:hover, &.active { background: var(--snm-accent-hover, rgba(0,0,0,.04)); }
      &.selected {
        background: var(--snm-accent-active, rgba(25,118,210,.1));
        font-weight: 500;
      }
    }

    .sss-label { font-size: 13px; color: var(--snm-text-primary, inherit); line-height: 1.3; }
    .sss-sub { font-size: 11px; color: var(--snm-text-muted, rgba(0,0,0,.55)); margin-top: 2px; }

    .sss-loading-more {
      display: flex; align-items: center; justify-content: center;
      gap: 8px; padding: 8px; font-size: 12px;
      color: var(--snm-text-muted, rgba(0,0,0,.55));
      border-top: 1px solid var(--snm-border-divider, rgba(0,0,0,.06));
    }

    .disabled { opacity: .6; pointer-events: none; }

    .sss-state {
      display: flex; align-items: center; gap: 10px;
      padding: 20px 16px; color: var(--snm-text-muted, rgba(0,0,0,.6));
      font-size: 13px;
      &.hint { color: var(--snm-text-muted, rgba(0,0,0,.5)); font-style: italic; }
      mat-icon { font-size: 20px; width: 20px; height: 20px; opacity: .7; }
    }

    .sss-viewport {
      flex: 1; min-height: 260px;
    }

    .sss-item {
      padding: 8px 14px;
      cursor: pointer;
      border-bottom: 1px solid var(--snm-border-divider, rgba(0,0,0,.06));
      transition: background 0.1s;
      &:hover, &.active { background: var(--snm-accent-hover, rgba(0,0,0,.04)); }
      &.selected {
        background: var(--snm-accent-active, rgba(25,118,210,.1));
        font-weight: 500;
      }
    }

    .sss-label { font-size: 13px; color: var(--snm-text-primary, inherit); line-height: 1.3; }
    .sss-sub { font-size: 11px; color: var(--snm-text-muted, rgba(0,0,0,.55)); margin-top: 2px; }

    .sss-loading-more {
      display: flex; align-items: center; justify-content: center;
      gap: 8px; padding: 8px; font-size: 12px;
      color: var(--snm-text-muted, rgba(0,0,0,.55));
      border-top: 1px solid var(--snm-border-divider, rgba(0,0,0,.06));
    }

    .disabled { opacity: .6; pointer-events: none; }
  `],
})
export class ServerSearchSelectComponent implements OnInit, OnDestroy, ControlValueAccessor {
  /** API endpoint returning {items, nextCursor, hasMore}. E.g. "/customers/search" */
  @Input() endpoint!: string;
  /** Placeholder text inside input */
  @Input() placeholder = 'Search...';
  /** Optional label above input (for mat-form-field) */
  @Input() label = '';
  /** Optional hint below input */
  @Input() hint = '';
  /** Minimum chars before triggering search (default 0 = show first page immediately) */
  @Input() minSearchLength = 0;
  /** Page size per request (backend caps at 200) */
  @Input() pageLimit = 50;
  /** Disabled state */
  @Input() disabled = false;
  /** Required (hides clear button) */
  @Input() required = false;
  /** Extra query params forwarded to backend (static) */
  @Input() extraParams: Record<string, string | number> = {};
  /** Custom display formatter when an item is selected (default: item.label) */
  @Input() displayFn: (item: SearchItem) => string = (item) => item.label;

  @Output() selectionChange = new EventEmitter<SearchItem | null>();

  @ViewChild(CdkVirtualScrollViewport) viewport?: CdkVirtualScrollViewport;

  items: SearchItem[] = [];
  loading = false;
  isOpen = false;
  searchText = '';
  activeIndex = 0;
  value: number | null = null;
  selectedItem: SearchItem | null = null;
  displayLabel = '';


  private nextCursor: string | null = null;
  private hasMore = false;
  private searchSubject = new Subject<string>();
  private destroy$ = new Subject<void>();
  private requestToken = 0;   // generation counter for cancellation

  // ControlValueAccessor callbacks
  private onChange: (value: number | null) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private api: ApiService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    // Debounced search driver
    this.searchSubject.pipe(
      debounceTime(300),
      distinctUntilChanged(),
      takeUntil(this.destroy$),
    ).subscribe(() => this.loadFirstPage());
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // --- ControlValueAccessor ---

  writeValue(value: number | null): void {
    this.value = value;
    if (value == null) {
      this.selectedItem = null;
      this.displayLabel = '';
      this.cdr.markForCheck();
      return;
    }
    // If we don't yet know the label for this id, fetch it
    if (!this.selectedItem || this.selectedItem.id !== value) {
      this.resolveIdToLabel(value);
    }
  }

  registerOnChange(fn: (value: number | null) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(isDisabled: boolean): void { this.disabled = isDisabled; }

  // --- Input handlers ---

  onFocus(): void {
    if (this.disabled) return;
    this.isOpen = true;
    this.activeIndex = 0;
    if (this.items.length === 0 && this.searchText.length >= this.minSearchLength) {
      this.loadFirstPage();
    }
  }

  onInput(e: Event): void {
    const val = (e.target as HTMLInputElement).value;
    this.searchText = val;
    this.isOpen = true;
    if (val.length >= this.minSearchLength) {
      this.searchSubject.next(val);
    } else {
      this.items = [];
      this.nextCursor = null;
      this.hasMore = false;
    }
  }

  onKeyDown(e: KeyboardEvent): void {
    if (!this.isOpen) return;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        this.activeIndex = Math.min(this.activeIndex + 1, this.items.length - 1);
        this.viewport?.scrollToIndex(this.activeIndex);
        break;
      case 'ArrowUp':
        e.preventDefault();
        this.activeIndex = Math.max(this.activeIndex - 1, 0);
        this.viewport?.scrollToIndex(this.activeIndex);
        break;
      case 'Enter':
        e.preventDefault();
        if (this.items[this.activeIndex]) this.select(this.items[this.activeIndex]);
        break;
      case 'Escape':
        e.preventDefault();
        this.close();
        break;
    }
  }

  // --- Selection ---

  select(item: SearchItem): void {
    this.selectedItem = item;
    this.value = item.id;
    this.displayLabel = this.displayFn(item);
    this.onChange(item.id);
    this.onTouched();
    this.selectionChange.emit(item);
    this.close();
  }

  clearSelection(e: Event): void {
    e.preventDefault();
    e.stopPropagation();
    this.selectedItem = null;
    this.value = null;
    this.displayLabel = '';
    this.searchText = '';
    this.items = [];
    this.onChange(null);
    this.onTouched();
    this.selectionChange.emit(null);
  }

  close(): void {
    this.isOpen = false;
    this.searchText = '';
    this.activeIndex = 0;
  }

  // --- Data loading ---

  private loadFirstPage(): void {
    const token = ++this.requestToken;
    this.loading = true;
    this.items = [];
    this.nextCursor = null;

    this.api.get<SearchResponse>(this.endpoint, {
      q: this.searchText,
      limit: String(this.pageLimit),
      ...this.extraParams,
    }).subscribe({
      next: (res) => {
        if (token !== this.requestToken) return;  // stale response
        this.items = res.items || [];
        this.nextCursor = res.nextCursor;
        this.hasMore = res.hasMore;
        this.activeIndex = 0;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        if (token !== this.requestToken) return;
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  onScrollIndexChange(index: number): void {
    // Load more when within 5 items of the end
    const end = this.items.length;
    if (this.hasMore && !this.loading && index >= end - 5 && end > 0) {
      this.loadMore();
    }
  }

  private loadMore(): void {
    if (!this.nextCursor || this.loading) return;
    const token = this.requestToken;  // don't increment — keep same search context
    this.loading = true;

    this.api.get<SearchResponse>(this.endpoint, {
      q: this.searchText,
      limit: String(this.pageLimit),
      after: this.nextCursor,
      ...this.extraParams,
    }).subscribe({
      next: (res) => {
        if (token !== this.requestToken) return;
        this.items = [...this.items, ...(res.items || [])];
        this.nextCursor = res.nextCursor;
        this.hasMore = res.hasMore;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        if (token !== this.requestToken) return;
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  /** Given an id, fetch its label for initial display (edit mode). */
  private resolveIdToLabel(id: number): void {
    this.api.get<SearchResponse>(this.endpoint, { ids: String(id), limit: '1' })
      .subscribe({
        next: (res) => {
          const match = res.items?.find(i => i.id === id);
          if (match) {
            this.selectedItem = match;
            this.displayLabel = this.displayFn(match);
            this.cdr.markForCheck();
          }
        },
      });
  }
}
