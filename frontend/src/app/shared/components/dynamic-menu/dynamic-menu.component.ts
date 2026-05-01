import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { forkJoin, Subscription } from 'rxjs';
import { MenuService, MenuNode } from '../../../core/services/menu.service';
import { TokenService } from '../../../core/auth/token.service';
import { SkeletonLoaderComponent } from '../skeleton-loader/skeleton-loader.component';

@Component({
  selector: 'app-dynamic-menu',
  standalone: true,
  imports: [CommonModule, RouterModule, MatIconModule, SkeletonLoaderComponent],
  template: `
    <nav class="sidebar-nav">
      @if (loading) {
        <app-skeleton-loader type="menu" [rows]="8"></app-skeleton-loader>
      }
      @for (node of menuTree; track node.menuId) {
        @if (node.children.length > 0) {
          <div class="menu-group">
            <button class="menu-header" (click)="toggle(node.menuId)">
              @if (node.menuIcon) { <mat-icon class="menu-icon">{{ node.menuIcon }}</mat-icon> }
              <span class="menu-label">{{ node.menuName }}</span>
              <mat-icon class="expand-icon" [class.expanded]="isExpanded(node.menuId)">expand_more</mat-icon>
            </button>
            <div class="submenu" [class.open]="isExpanded(node.menuId)">
              @for (child of node.children; track child.menuId) {
                @if (child.children.length > 0) {
                  <button class="submenu-header" (click)="toggle(child.menuId); $event.stopPropagation()">
                    <span class="menu-label">{{ child.menuName }}</span>
                    <mat-icon class="expand-icon" [class.expanded]="isExpanded(child.menuId)">expand_more</mat-icon>
                  </button>
                  <div class="submenu nested" [class.open]="isExpanded(child.menuId)">
                    @for (subChild of child.children; track subChild.menuId) {
                      <a class="menu-item nested-item" [routerLink]="subChild.menuUrl" routerLinkActive="active">
                        <span class="menu-label">{{ subChild.menuName }}</span>
                      </a>
                    }
                  </div>
                } @else {
                  <a class="menu-item" [routerLink]="child.menuUrl" routerLinkActive="active">
                    @if (child.menuIcon) { <mat-icon class="menu-icon small">{{ child.menuIcon }}</mat-icon> }
                    <span class="menu-label">{{ child.menuName }}</span>
                  </a>
                }
              }
            </div>
          </div>
        } @else {
          <a class="menu-item top-level" [routerLink]="node.menuUrl" routerLinkActive="active">
            @if (node.menuIcon) { <mat-icon class="menu-icon">{{ node.menuIcon }}</mat-icon> }
            <span class="menu-label">{{ node.menuName }}</span>
          </a>
        }
      }

      <!-- SuperAdmin-only utilities. Not in the DB-driven menu tree because
           these are maintenance actions rather than business functions. -->
      @if (isSuperAdmin) {
        <div class="menu-separator">Admin</div>
        <a class="menu-item top-level super-admin-item" routerLink="/settings/data-purge" routerLinkActive="active">
          <mat-icon class="menu-icon">delete_forever</mat-icon>
          <span class="menu-label">Data Purge</span>
        </a>
      }
    </nav>
  `,
  styles: [`
    :host { display: block; padding: 0.5rem 0; }

    .sidebar-nav {
      display: flex;
      flex-direction: column;
    }

    /* Top-level menu items (no children) */
    .menu-item.top-level {
      display: flex;
      align-items: center;
      padding: 10px 20px;
      color: var(--snm-text-primary);
      text-decoration: none;
      cursor: pointer;
      transition: background 0.25s ease, color 0.25s ease, border-left 0.25s ease;
      border-left: 3px solid transparent;
      font-size: 14px;
    }

    /* Parent menu header (expandable) */
    .menu-header {
      display: flex;
      align-items: center;
      width: 100%;
      padding: 10px 20px;
      border: none;
      background: none;
      color: var(--snm-text-primary);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.25s ease, color 0.25s ease;
      border-left: 3px solid transparent;
      text-align: left;
    }

    /* Submenu child header (nested expandable) */
    .submenu-header {
      display: flex;
      align-items: center;
      width: 100%;
      padding: 9px 20px 9px 48px;
      border: none;
      background: none;
      color: var(--snm-text-secondary);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.25s ease, color 0.25s ease;
      border-left: 3px solid transparent;
      text-align: left;
    }

    /* Submenu child items */
    .menu-item {
      display: flex;
      align-items: center;
      padding: 9px 20px 9px 48px;
      color: var(--snm-text-secondary);
      text-decoration: none;
      cursor: pointer;
      transition: background 0.25s ease, color 0.25s ease, border-left 0.25s ease;
      border-left: 3px solid transparent;
      font-size: 13px;
    }

    /* Deeper nested items */
    .menu-item.nested-item {
      padding-left: 64px;
    }

    /* Hover for all clickable elements */
    .menu-header:hover,
    .submenu-header:hover,
    .menu-item:hover {
      background: var(--snm-accent-hover);
      color: var(--snm-text-primary);
    }

    /* Active state */
    .active {
      background: var(--snm-accent-active) !important;
      border-left-color: var(--snm-accent) !important;
      color: var(--snm-text-primary) !important;
      font-weight: 500;
    }

    /* Icons */
    .menu-icon {
      font-size: 20px;
      width: 20px;
      height: 20px;
      margin-right: 12px;
      color: var(--snm-accent);
      flex-shrink: 0;
      line-height: 20px;
    }
    .menu-icon.small {
      font-size: 18px;
      width: 18px;
      height: 18px;
      margin-right: 10px;
      line-height: 18px;
    }

    /* Expand/collapse chevron */
    .expand-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
      margin-left: auto;
      color: var(--snm-text-faint);
      transition: transform 0.3s ease;
      flex-shrink: 0;
      line-height: 18px;
    }
    .expand-icon.expanded {
      transform: rotate(180deg);
    }

    /* Menu label */
    .menu-label {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Submenu collapsible container */
    .submenu {
      overflow: hidden;
      max-height: 0;
      transition: max-height 0.35s ease;
    }
    .submenu.open {
      max-height: 800px;
    }

    /* Divider between menu groups */
    .menu-group + .menu-group {
      border-top: 1px solid var(--snm-border-menu-sep);
    }
    .menu-item.top-level + .menu-group,
    .menu-group + .menu-item.top-level {
      border-top: 1px solid var(--snm-border-menu-sep);
    }

    /* SuperAdmin-only utilities — visually separated with a thin label. */
    .menu-separator {
      margin-top: 16px;
      padding: 8px 20px 4px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--snm-text-faint);
      border-top: 1px solid var(--snm-border-menu-sep);
    }
    .super-admin-item .menu-icon {
      color: var(--snm-error);
    }
  `],
})
export class DynamicMenuComponent implements OnInit, OnDestroy {
  menuTree: MenuNode[] = [];
  loading = true;
  private sub?: Subscription;
  private expandedIds = new Set<number>();

  constructor(private menuService: MenuService, private tokenService: TokenService) {}

  toggle(menuId: number): void {
    if (this.expandedIds.has(menuId)) {
      this.expandedIds.delete(menuId);
    } else {
      this.expandedIds.add(menuId);
    }
  }

  isExpanded(menuId: number): boolean {
    return this.expandedIds.has(menuId);
  }

  isSuperAdmin = false;

  ngOnInit(): void {
    this.sub = this.menuService.menuTree$.subscribe(tree => {
      this.menuTree = tree;
      // Show skeleton when menu is cleared (company switch) or while loading
      this.loading = tree.length === 0;
    });
    // Load menu tree + permissions in parallel on init
    const userData = this.tokenService.getUserData();
    const roleId = userData?.roleId;
    this.isSuperAdmin = userData?.isSuperAdmin || false;

    forkJoin([
      this.menuService.loadUserMenu(),
      this.menuService.loadPermissions(roleId, this.isSuperAdmin),
    ]).subscribe({
      error: () => this.loading = false,
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
