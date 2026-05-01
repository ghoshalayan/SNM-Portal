import { Routes } from '@angular/router';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./layout/main-layout/main-layout.component').then(m => m.MainLayoutComponent),
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
      },
      {
        path: 'companies',
        loadComponent: () =>
          import('./features/company/company-list.component').then(m => m.CompanyListComponent),
      },
      {
        path: 'users',
        loadComponent: () =>
          import('./features/users/user-list.component').then(m => m.UserListComponent),
      },
      {
        path: 'roles',
        loadComponent: () =>
          import('./features/roles/role-list.component').then(m => m.RoleListComponent),
      },
      {
        path: 'roles/:roleId/menu-mapping',
        loadComponent: () =>
          import('./features/roles/role-menu-mapping/role-menu-mapping.component').then(m => m.RoleMenuMappingComponent),
      },
      {
        // v2 — new UI, lives alongside the classic page so users can opt in.
        path: 'roles/:roleId/permissions-v2',
        loadComponent: () =>
          import('./features/roles/role-menu-mapping-v2/role-menu-mapping-v2.component')
            .then(m => m.RoleMenuMappingV2Component),
      },
      {
        // Side-by-side role comparison. Accessible via ?a=…&b=… query params.
        path: 'roles/compare',
        loadComponent: () =>
          import('./features/roles/role-compare/role-compare.component')
            .then(m => m.RoleCompareComponent),
      },
      {
        path: 'masters',
        children: [
          { path: 'item-grades', loadComponent: () => import('./features/masters/item-grade/item-grade-list.component').then(m => m.ItemGradeListComponent) },
          { path: 'item-names', loadComponent: () => import('./features/masters/item-name/item-name-list.component').then(m => m.ItemNameListComponent) },
          { path: 'item-lengths', loadComponent: () => import('./features/masters/item-length/item-length-list.component').then(m => m.ItemLengthListComponent) },
          { path: 'item-sizes', loadComponent: () => import('./features/masters/item-size/item-size-list.component').then(m => m.ItemSizeListComponent) },
          { path: 'delivery-terms', loadComponent: () => import('./features/masters/delivery-term/delivery-term-list.component').then(m => m.DeliveryTermListComponent) },
          { path: 'delivery-modes', loadComponent: () => import('./features/masters/delivery-mode/delivery-mode-list.component').then(m => m.DeliveryModeListComponent) },
          { path: 'contact-types', loadComponent: () => import('./features/masters/contact-type/contact-type-list.component').then(m => m.ContactTypeListComponent) },
          { path: 'customer-classifications', loadComponent: () => import('./features/masters/customer-classification/customer-classification-list.component').then(m => m.CustomerClassificationListComponent) },
          { path: 'cost-points', loadComponent: () => import('./features/masters/cost-point/cost-point-list.component').then(m => m.CostPointListComponent) },
          { path: 'terms-conditions', loadComponent: () => import('./features/masters/terms-condition/terms-condition-list.component').then(m => m.TermsConditionListComponent) },
          { path: 'raw-material-costs', loadComponent: () => import('./features/masters/raw-material-cost/raw-material-cost-list.component').then(m => m.RawMaterialCostListComponent) },
          { path: 'countries', loadComponent: () => import('./features/masters/country/country-list.component').then(m => m.CountryListComponent) },
          { path: 'states', loadComponent: () => import('./features/masters/state/state-list.component').then(m => m.StateListComponent) },
          { path: 'districts', loadComponent: () => import('./features/masters/district/district-list.component').then(m => m.DistrictListComponent) },
          { path: 'dia-masters', loadComponent: () => import('./features/masters/dia-master/dia-master-list.component').then(m => m.DiaMasterListComponent) },
          { path: 'enq-statuses', loadComponent: () => import('./features/masters/enq-status/enq-status-list.component').then(m => m.EnqStatusListComponent) },
          { path: 'quot-statuses', loadComponent: () => import('./features/masters/quot-status/quot-status-list.component').then(m => m.QuotStatusListComponent) },
          { path: 'communication-modes', loadComponent: () => import('./features/masters/communication-mode/communication-mode-list.component').then(m => m.CommunicationModeListComponent) },
          { path: 'financial-years', loadComponent: () => import('./features/masters/financial-year/financial-year-list.component').then(m => m.FinancialYearListComponent) },
        ],
      },
      {
        path: 'customers',
        children: [
          { path: '', loadComponent: () => import('./features/customers/customer-list/customer-list.component').then(m => m.CustomerListComponent) },
          { path: 'new', loadComponent: () => import('./features/customers/customer-form/customer-form.component').then(m => m.CustomerFormComponent) },
          { path: ':id/edit', loadComponent: () => import('./features/customers/customer-form/customer-form.component').then(m => m.CustomerFormComponent) },
        ],
      },
      {
        path: 'enquiries',
        children: [
          { path: '', loadComponent: () => import('./features/enquiries/enquiry-list/enquiry-list.component').then(m => m.EnquiryListComponent) },
          { path: 'new', loadComponent: () => import('./features/enquiries/enquiry-form/enquiry-form.component').then(m => m.EnquiryFormComponent) },
          { path: ':id/edit', loadComponent: () => import('./features/enquiries/enquiry-form/enquiry-form.component').then(m => m.EnquiryFormComponent) },
        ],
      },
      {
        path: 'quotations',
        children: [
          { path: '', loadComponent: () => import('./features/quotations/quotation-list/quotation-list.component').then(m => m.QuotationListComponent) },
          { path: 'new', loadComponent: () => import('./features/quotations/quotation-form/quotation-form.component').then(m => m.QuotationFormComponent) },
          { path: ':id/edit', loadComponent: () => import('./features/quotations/quotation-form/quotation-form.component').then(m => m.QuotationFormComponent) },
          { path: ':id/print', loadComponent: () => import('./features/quotations/quotation-print/quotation-print.component').then(m => m.QuotationPrintComponent) },
          { path: ':id/annexure-print', loadComponent: () => import('./features/quotations/quotation-annexure-print/quotation-annexure-print.component').then(m => m.QuotationAnnexurePrintComponent) },
        ],
      },
      {
        path: 'assets',
        children: [
          { path: 'quotation-formats', loadComponent: () => import('./features/assets/quotation-format/quotation-format-list.component').then(m => m.QuotationFormatListComponent) },
          { path: '', redirectTo: 'quotation-formats', pathMatch: 'full' },
        ],
      },
      {
        path: 'communication-logs',
        loadComponent: () =>
          import('./features/communication-logs/communication-log-list.component').then(m => m.CommunicationLogListComponent),
      },
      {
        path: 'user-location-mapping',
        loadComponent: () =>
          import('./features/users/user-location-list.component').then(m => m.UserLocationListComponent),
      },
      {
        path: 'org-tree',
        loadComponent: () =>
          import('./features/org-tree/org-tree.component').then(m => m.OrgTreeComponent),
      },
      {
        // SuperAdmin-only destructive utility. Route is reachable but the
        // component itself re-checks the flag and bounces on a mismatch.
        path: 'settings/data-purge',
        loadComponent: () =>
          import('./features/settings/data-purge/data-purge.component').then(m => m.DataPurgeComponent),
      },
      {
        // KPI Studio — pluggable analytics module. Phase 1 ships the
        // schema explorer; Phases 2-5 add KPIs, dashboards, NL→SQL.
        path: 'kpi-studio',
        loadChildren: () =>
          import('./features/kpi-studio/kpi-studio.routes').then(m => m.KPI_STUDIO_ROUTES),
      },
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    ],
  },
  // Unknown paths land on dashboard for logged-in users instead of bouncing
  // to /login. If the token is missing, the main layout's auth guard (or the
  // interceptor's 401 flow) will redirect to /login naturally.
  { path: '**', redirectTo: 'dashboard' },
];
