import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';

@Component({
  selector: 'app-company-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatTabsModule,
  ],
  templateUrl: './company-dialog.component.html',
  styleUrl: './company-dialog.component.scss',
})
export class CompanyDialogComponent implements OnInit {
  form: FormGroup;
  isEdit: boolean;
  countries: any[] = [];
  states: any[] = [];

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    public dialogRef: MatDialogRef<CompanyDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {
    this.isEdit = !!data;
    this.form = this.fb.group({
      companyName: [data?.companyName || '', Validators.required],
      companyCode: [data?.companyCode || ''],
      address: [data?.address || ''],
      city: [data?.city || ''],
      state: [data?.state || ''],
      country: [data?.country || ''],
      pinCode: [data?.pinCode || ''],
      phone: [data?.phone || ''],
      email: [data?.email || ''],
      website: [data?.website || ''],
      GSTN: [data?.GSTN || ''],
      PAN: [data?.PAN || ''],
      // SMTP settings (optional)
      MailFrom: [data?.MailFrom || ''],
      MailPassword: [data?.MailPassword || ''],
      SMTP: [data?.SMTP || ''],
      PortNo: [data?.PortNo || ''],
    });
  }

  ngOnInit(): void {
    this.loadCountries();
    if (this.form.get('country')?.value) {
      this.loadStates(this.form.get('country')!.value);
    }
  }

  loadCountries(): void {
    this.api.get<any[]>('/masters/countries').subscribe({
      next: (data) => (this.countries = data),
    });
  }

  loadStates(countryName: string): void {
    if (!countryName) {
      this.states = [];
      return;
    }
    this.api.get<any[]>('/masters/states', { country: countryName }).subscribe({
      next: (data) => (this.states = data),
    });
  }

  onCountryChange(countryName: string): void {
    this.form.get('state')?.setValue('');
    this.loadStates(countryName);
  }

  save(): void {
    if (!this.form.valid) return;

    const payload = this.form.value;

    if (this.isEdit) {
      this.api.put(`/companies/${this.data.companyId}`, payload).subscribe({
        next: () => {
          this.notify.success('Company updated');
          this.dialogRef.close(true);
        },
        error: () => this.notify.error('Failed to update company'),
      });
    } else {
      this.api.post('/companies', payload).subscribe({
        next: () => {
          this.notify.success('Company created');
          this.dialogRef.close(true);
        },
        error: () => this.notify.error('Failed to create company'),
      });
    }
  }
}
