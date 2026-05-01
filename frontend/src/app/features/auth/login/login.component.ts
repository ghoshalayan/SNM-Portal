import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AuthService, CompanyInfo } from '../../../core/auth/auth.service';
import { ThemeService } from '../../../core/services/theme.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatTooltipModule,
  ],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  loginForm: FormGroup;
  companies: CompanyInfo[] = [];
  showCompanyPicker = false;
  loading = false;
  error = '';
  hidePassword = true;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    public themeService: ThemeService,
  ) {
    this.loginForm = this.fb.group({
      userLogin: ['', Validators.required],
      password: ['', Validators.required],
      companyId: [null],
    });
  }

  onLogin(): void {
    if (!this.loginForm.get('userLogin')?.valid || !this.loginForm.get('password')?.valid) {
      return;
    }

    this.loading = true;
    this.error = '';

    const { userLogin, password } = this.loginForm.value;

    this.authService.login(userLogin, password).subscribe({
      next: (response) => {
        this.companies = response.companies;

        if (this.companies.length === 1) {
          this.selectCompany(this.companies[0].companyId);
        } else {
          this.showCompanyPicker = true;
          this.loading = false;
          const defaultCompany = this.companies.find(c => c.isDefault);
          if (defaultCompany) {
            this.loginForm.patchValue({ companyId: defaultCompany.companyId });
          }
        }
      },
      error: (err) => {
        this.error = err.error?.detail || 'Login failed';
        this.loading = false;
      },
    });
  }

  onSelectCompany(): void {
    const companyId = this.loginForm.get('companyId')?.value;
    if (!companyId) return;
    this.selectCompany(companyId);
  }

  private selectCompany(companyId: number): void {
    this.loading = true;
    this.authService.selectCompany(companyId).subscribe({
      next: () => {
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.error = err.error?.detail || 'Company selection failed';
        this.loading = false;
      },
    });
  }
}
