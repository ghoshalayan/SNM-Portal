import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { AuthService } from '../../core/auth/auth.service';
import { SearchFilterPipe } from '../../shared/pipes/search-filter.pipe';
import { ServerSearchSelectComponent } from '../../shared/components/server-search-select/server-search-select.component';

interface CompanyOption { companyId: number; companyName: string; }
interface RoleOption { roleId: number; roleName: string; }

@Component({
  selector: 'app-user-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatButtonModule,
    MatSelectModule, MatCheckboxModule, MatIconModule,
    MatDividerModule, SearchFilterPipe, ServerSearchSelectComponent,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} User</h2>
    <mat-dialog-content>
      <form [formGroup]="form">
        <div class="form-grid">
          <mat-form-field appearance="outline">
            <mat-label>Name *</mat-label>
            <input matInput formControlName="userName" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Code</mat-label>
            <input matInput formControlName="userCode" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Email</mat-label>
            <input matInput formControlName="userEmail" type="email" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Phone</mat-label>
            <input matInput formControlName="userPhone" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Designation</mat-label>
            <input matInput formControlName="userDesignation" />
          </mat-form-field>
          @if (!isEdit) {
            <mat-form-field appearance="outline">
              <mat-label>Login *</mat-label>
              <input matInput formControlName="userLogin" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Password *</mat-label>
              <input matInput formControlName="userPassword" type="password" />
            </mat-form-field>
          }
        </div>

        <mat-divider></mat-divider>

        <div class="section-header">
          <h3>Company, Role & Reporting</h3>
          <button mat-button type="button" color="primary" (click)="addMapping()">
            <mat-icon>add</mat-icon> Add
          </button>
        </div>

        <div formArrayName="roleMappings">
          @for (mapping of roleMappingsArray.controls; track $index) {
            <div [formGroupName]="$index" class="mapping-row">
              <mat-form-field appearance="outline" class="mapping-company">
                <mat-label>Company *</mat-label>
                <mat-select formControlName="companyId"
                  (selectionChange)="onMappingCompanyChange($index)"
                  (openedChange)="searchState[$index] = searchState[$index] || {}; searchState[$index].company = ''">
                  <div class="select-search" (click)="$event.stopPropagation()">
                    <input placeholder="Search..." [(ngModel)]="searchState[$index].company"
                      [ngModelOptions]="{standalone: true}" (keydown)="$event.stopPropagation()">
                  </div>
                  @for (c of companies | searchFilter:(searchState[$index]?.company || ''):'companyName'; track c.companyId) {
                    <mat-option [value]="c.companyId">{{ c.companyName }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>

              <mat-form-field appearance="outline" class="mapping-role">
                <mat-label>Role *</mat-label>
                <mat-select formControlName="roleId"
                  (openedChange)="searchState[$index] = searchState[$index] || {}; searchState[$index].role = ''">
                  <div class="select-search" (click)="$event.stopPropagation()">
                    <input placeholder="Search..." [(ngModel)]="searchState[$index].role"
                      [ngModelOptions]="{standalone: true}" (keydown)="$event.stopPropagation()">
                  </div>
                  @for (r of (rolesMap[$index] || []) | searchFilter:(searchState[$index]?.role || ''):'roleName'; track r.roleId) {
                    <mat-option [value]="r.roleId">{{ r.roleName }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>

              <div class="mapping-report">
                <app-server-search-select
                  endpoint="/users/search"
                  label="Reports To"
                  placeholder="Search user..."
                  formControlName="reportTo"
                  [extraParams]="{ companyId: mapping.get('companyId')?.value || 0 }">
                </app-server-search-select>
              </div>

              <mat-checkbox formControlName="isDefault" class="mapping-default">Default</mat-checkbox>

              <button mat-icon-button type="button" color="warn" (click)="removeMapping($index)"
                [disabled]="roleMappingsArray.length <= 1">
                <mat-icon>remove_circle_outline</mat-icon>
              </button>
            </div>
          }
        </div>

        @if (roleMappingsArray.length === 0) {
          <p class="no-mappings">No company-role assignments. Click "Add" to assign.</p>
        }
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="!form.valid || saving">
        {{ isEdit ? 'Update' : 'Create' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .form-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0 1rem;
      padding: 1rem 0;
      mat-form-field { width: 100%; }
    }
    mat-divider { margin: 0.5rem 0; }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 0.5rem 0;
      h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--snm-text-primary); }
    }
    .mapping-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.25rem;
    }
    .mapping-company { flex: 2; min-width: 0; }
    .mapping-role { flex: 2; min-width: 0; }
    .mapping-report { flex: 3; min-width: 0; }
    .mapping-default { flex-shrink: 0; white-space: nowrap; font-size: 13px; }
    .no-mappings {
      text-align: center;
      color: var(--snm-text-muted);
      font-size: 13px;
      padding: 0.5rem 0;
    }
    .select-search {
      padding: 8px 16px 4px;
      position: sticky;
      top: 0;
      background: var(--mat-sys-surface, #fff);
      z-index: 1;
    }
    .select-search input {
      width: 100%;
      padding: 6px 8px;
      border: 1px solid #ccc;
      border-radius: 4px;
      font-size: 14px;
      outline: none;
    }
  `],
})
export class UserDialogComponent implements OnInit {
  form: FormGroup;
  isEdit: boolean;
  saving = false;
  companies: CompanyOption[] = [];
  rolesMap: { [index: number]: RoleOption[] } = {};
  searchState: { [index: number]: { company?: string; role?: string } } = {};

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private authService: AuthService,
    public dialogRef: MatDialogRef<UserDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {
    this.isEdit = !!data;
    this.form = this.fb.group({
      userName: [data?.userName || '', Validators.required],
      userCode: [data?.userCode || ''],
      userEmail: [data?.userEmail || ''],
      userPhone: [data?.userPhone || ''],
      userDesignation: [data?.userDesignation || ''],
      userLogin: [{ value: data?.userLogin || '', disabled: this.isEdit }, Validators.required],
      userPassword: ['', this.isEdit ? [] : [Validators.required]],
      roleMappings: this.fb.array([]),
    });
  }

  get roleMappingsArray(): FormArray {
    return this.form.get('roleMappings') as FormArray;
  }

  ngOnInit(): void {
    // Load companies
    this.api.get<CompanyOption[]>('/companies').subscribe({
      next: (data) => { this.companies = data; },
      error: () => {
        const currentUser = this.authService.getCurrentUser();
        if (currentUser) {
          this.companies = [{ companyId: currentUser.companyId, companyName: currentUser.companyName }];
        }
      },
    });

    if (this.isEdit) {
      this.api.get<{ companyId: number; roleId: number; isDefault: boolean; reportTo?: number }[]>(
        `/users/${this.data.userId}/role-mappings`
      ).subscribe({
        next: (mappings) => {
          mappings.forEach(m => this.addMapping(m.companyId, m.roleId, m.isDefault, m.reportTo));
        },
      });
    } else {
      const currentUser = this.authService.getCurrentUser();
      this.addMapping(currentUser?.companyId || 0);
    }
  }

  addMapping(companyId?: number, roleId?: number, isDefault = false, reportTo?: number | null): void {
    const index = this.roleMappingsArray.length;
    this.searchState[index] = {};
    this.roleMappingsArray.push(this.fb.group({
      companyId: [companyId || null, Validators.required],
      roleId: [roleId || null, Validators.required],
      isDefault: [isDefault],
      reportTo: [reportTo ?? null],
    }));
    if (companyId) {
      this.loadRolesForMapping(index, companyId);
      // reportTo dropdown fetches users on-demand via server-search component
    }
  }

  removeMapping(index: number): void {
    this.roleMappingsArray.removeAt(index);
    const newRoles: { [i: number]: RoleOption[] } = {};
    const newSearch: { [i: number]: any } = {};
    for (let i = 0; i < this.roleMappingsArray.length; i++) {
      const oldIndex = i >= index ? i + 1 : i;
      if (this.rolesMap[oldIndex]) newRoles[i] = this.rolesMap[oldIndex];
      newSearch[i] = {};
    }
    this.rolesMap = newRoles;
    this.searchState = newSearch;
  }

  onMappingCompanyChange(index: number): void {
    const mapping = this.roleMappingsArray.at(index);
    mapping.patchValue({ roleId: null, reportTo: null });
    const companyId = mapping.get('companyId')?.value;
    if (companyId) {
      this.loadRolesForMapping(index, companyId);
    } else {
      this.rolesMap[index] = [];
    }
  }

  private loadRolesForMapping(index: number, companyId: number): void {
    this.api.get<RoleOption[]>('/roles', { companyId: companyId.toString() }).subscribe({
      next: (data) => { this.rolesMap[index] = data; },
    });
  }

  save(): void {
    if (!this.form.valid) return;
    this.saving = true;
    const raw = this.form.getRawValue();
    const mappings = raw.roleMappings;

    if (this.isEdit) {
      const { userLogin, userPassword, roleMappings, ...updateData } = raw;
      this.api.put(`/users/${this.data.userId}`, updateData).subscribe({
        next: () => {
          this.api.post(`/users/${this.data.userId}/role-mappings`, mappings).subscribe({
            next: () => { this.notify.success('User updated'); this.dialogRef.close(true); },
            error: () => { this.notify.error('User saved but role mappings failed'); this.saving = false; },
          });
        },
        error: () => { this.notify.error('Failed to update user'); this.saving = false; },
      });
    } else {
      const payload = {
        userName: raw.userName,
        userCode: raw.userCode,
        userEmail: raw.userEmail,
        userPhone: raw.userPhone,
        userDesignation: raw.userDesignation,
        userLogin: raw.userLogin,
        userPassword: raw.userPassword,
        reportTo: mappings[0]?.reportTo || null,
        companyId: mappings[0]?.companyId || 0,
        roleMappings: mappings,
      };
      this.api.post('/users', payload).subscribe({
        next: () => { this.notify.success('User created'); this.dialogRef.close(true); },
        error: (err) => { this.notify.error(err.error?.detail || 'Failed'); this.saving = false; },
      });
    }
  }
}
