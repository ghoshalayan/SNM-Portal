# SNM Portal - Frontend

## Overview
Multi-tenant B2B portal frontend for managing customers, enquiries, quotations, and costing with role-based menus, company switching, and dark/light theming.

**Stack:** Angular 21 | Angular Material 21 | RxJS 7.8 | TypeScript 5.9 | Standalone Components (no NgModules)

## Quick Start
```bash
cd frontend
npm install
npm start          # Serves at http://localhost:4200, proxies /api to localhost:8000
npm run build      # Production build
```

## Project Structure
```
frontend/src/app/
├── core/
│   ├── auth/
│   │   ├── auth.service.ts        # Login/logout, company selection, token management
│   │   ├── auth.guard.ts          # Route guard (functional CanActivateFn)
│   │   ├── auth.interceptor.ts    # JWT header injection, 401 handling
│   │   └── token.service.ts       # localStorage token storage
│   └── services/
│       ├── api.service.ts          # Generic HTTP wrapper (get/post/put/delete)
│       ├── menu.service.ts         # Dynamic menu tree + permission map
│       ├── notification.service.ts # MatSnackBar wrapper (success/error/info)
│       ├── theme.service.ts        # Dark/light mode toggle (signals + localStorage)
│       └── company-context.service.ts  # Company switching orchestration
├── shared/
│   ├── components/
│   │   ├── dynamic-menu/           # Recursive sidebar menu (3 levels)
│   │   ├── company-switcher/       # Header company dropdown
│   │   ├── confirm-dialog/         # Reusable confirmation modal
│   │   ├── profile-menu/           # Profile + change password dialog
│   │   └── skeleton-loader/        # Loading placeholders (table/menu/toolbar/text)
│   ├── directives/
│   │   └── has-permission.directive.ts  # *appHasPermission="'MenuName:canEdit'"
│   └── pipes/                      # (empty - no custom pipes yet)
├── layout/
│   └── main-layout/                # Sidenav + toolbar + router-outlet wrapper
├── features/
│   ├── auth/login/                 # Login page with company picker
│   ├── dashboard/                  # Dashboard
│   ├── company/                    # Company CRUD (super admin)
│   ├── users/                      # User CRUD + role mapping dialog
│   ├── roles/                      # Role CRUD + role-menu-mapping tree
│   ├── org-tree/                   # Org hierarchy canvas (dagre layout, drag-drop)
│   ├── masters/                    # 14 master data modules (consistent CRUD pattern)
│   ├── customers/                  # Customer list + form + contacts + sites (tabbed)
│   ├── enquiries/                  # Enquiry list + form + details + costing
│   ├── quotations/                 # Quotation list + form + details + TNC + print + versioning
│   └── assets/                     # File upload (Azure Blob)
├── app.routes.ts                   # All routes (lazy loaded, standalone)
├── app.config.ts                   # App providers (HTTP, animations, router)
└── app.ts                          # Root component
```

## Architecture Patterns

### Component Pattern
- **ALL components are standalone** (no NgModules anywhere)
- Most use **inline templates** and **inline styles** (except complex ones like org-tree, main-layout)
- Feature components follow **list + dialog** or **list + form** pattern

### Standard List Component
```typescript
@Component({ standalone: true, imports: [...], template: `...`, styles: [`...`] })
export class FeatureListComponent implements OnInit {
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;
  dataSource = new MatTableDataSource<T>();
  isLoading = false;
  // load() → api.get() → assign to dataSource → wire paginator/sort
}
```
- Default page size: 25, options: [10, 25, 50, 100]
- Artificial 500ms min loading delay for UX smoothing
- `debounceTime(400)` on search inputs

### Authentication Flow
1. User enters credentials → `authService.login()` → returns temp token + company list
2. Single company → auto-select; Multiple → show company picker
3. `authService.selectCompany()` → exchanges temp token for JWT (access + refresh)
4. Tokens stored in localStorage: `snm_access_token`, `snm_refresh_token`, `snm_user_data`
5. `auth.interceptor.ts` injects `Authorization: Bearer` header on all requests

### Multi-Tenancy / Company Switching
- `CompanySwitcherComponent` in header toolbar (visible if user has >1 company)
- `CompanyContextService.switchCompany()` → gets new JWT → reloads menu → emits `companyChanged$`
- Components can subscribe to `companyChanged$` to refresh data on switch

### Menu & Permissions
- `MenuService.loadUserMenu()` fetches role-based menu tree from `/menus/user-tree`
- Permission map: `{ menuName: { canAdd, canRead, canEdit, canDelete } }`
- `HasPermissionDirective`: `*appHasPermission="'Customers:canAdd'"` shows/hides UI elements
- `DynamicMenuComponent` renders recursive 3-level sidebar menu

### Theming
- **CSS custom properties** defined in `styles.scss` on `:root` (light) and `body.dark-theme` (dark)
- `ThemeService` uses Angular **signals** for reactive state, persists to `localStorage('snm-theme')`
- Toggle button in main-layout header between company-switcher and profile avatar
- **40+ CSS variables** covering: text, accent, glass surfaces, backgrounds, borders, scrollbar, status
- Light mode: `bg.png` background; Dark mode: `bg1.png` background with glassmorphism
- Login page always uses `bg1.png` regardless of theme

### API Communication
- `ApiService` wraps `HttpClient` with typed generic methods
- Base URL from `environment.apiUrl` (`http://localhost:8000/api/v1`)
- Dev proxy: `proxy.conf.json` forwards `/api` to `localhost:8000`
- All params auto-filtered (null/undefined removed)

## Key Files
| Purpose | File |
|---------|------|
| Routes | `app.routes.ts` |
| App bootstrap | `app.config.ts` |
| Theme variables | `src/styles.scss` (lines 1-120) |
| Auth service | `core/auth/auth.service.ts` |
| API wrapper | `core/services/api.service.ts` |
| Menu loading | `core/services/menu.service.ts` |
| Permission directive | `shared/directives/has-permission.directive.ts` |
| Sidebar menu | `shared/components/dynamic-menu/dynamic-menu.component.ts` |
| Layout shell | `layout/main-layout/main-layout.component.ts` |

## Styling Conventions
- **All colors via CSS variables** - never hardcode colors in component styles
- Variable prefix: `--snm-*` (e.g., `--snm-text-primary`, `--snm-accent`, `--snm-glass-bg`)
- Glass morphism: `backdrop-filter: blur()` + semi-transparent backgrounds
- Material component overrides in `styles.scss` (global scope)
- Component-scoped styles use SCSS with variable references

### Key CSS Variables
```scss
// Text
--snm-text-primary, --snm-text-secondary, --snm-text-muted, --snm-text-faint
// Accent
--snm-accent, --snm-accent-dark, --snm-accent-hover, --snm-accent-shadow
// Surfaces
--snm-glass-bg, --snm-bg-card, --snm-bg-panel, --snm-bg-node, --snm-bg-header-row
// Borders
--snm-border-field, --snm-border-divider, --snm-glass-border
// Status
--snm-error, --snm-super-admin
```

## Known Loopholes & Issues

### Security
1. **Auth guard not applied to routes** - `authGuard` exists in `auth.guard.ts` but is NOT wired into `app.routes.ts`. All "protected" routes rely only on token presence in interceptor; direct URL navigation bypasses guard.
2. **No automatic token refresh** - `refreshToken()` exists but 401 response triggers logout instead of refresh attempt. Sessions expire after 30 min requiring re-login.
3. **Tokens in localStorage** - vulnerable to XSS. No HttpOnly cookie alternative.

### Data & UX
4. **Hardcoded company info in quotation print** - GSTIN `27XXXXX1234Z1`, address `123 Industrial Area, Sector 5, Mumbai`, phone/email are placeholder values in `quotation-print.component.ts` (~line 91). Should come from company API.
5. **Hardcoded country 'India'** - customer contacts form calls `/masters/states` with `{ country: 'India' }` instead of dynamically selecting country.
6. **Background image path typo** - `styles.scss` uses `/assests/bg.png` and `/assests/bg1.png` (misspelled "assests" instead of "assets"). Works because actual folder is also misspelled as `public/assests/`.
7. **No 404 page** - wildcard route redirects to `/login` instead of showing a proper "not found" page.

### Code Quality
8. **No tests** - `tsconfig.spec.json` exists but no spec files written
9. **No state management** - relies on service + BehaviorSubject/signals; complex flows (company switch + menu reload + data refresh) can have timing issues
10. **No error boundary** - unhandled errors in components crash silently; no global error handler
11. **Empty pipes directory** - no custom pipes implemented
12. **No loading interceptor** - each component manages its own loading state independently
13. **Inline templates for complex components** - some feature components have 200+ line inline templates making them hard to maintain (e.g., user-dialog, enquiry-form)

### Performance
14. **No lazy loading for Material modules** - every component imports its own Material modules (tree-shaking helps but bundle could be smaller)
15. **No virtual scrolling** - long lists render all items in DOM
16. **No caching strategy** - menu/master data refetched on every navigation
