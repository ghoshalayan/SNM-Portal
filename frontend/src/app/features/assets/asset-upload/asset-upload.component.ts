import { Component, EventEmitter, Input, OnInit, OnChanges, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { environment } from '../../../../environments/environment';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ApiService } from '../../../core/services/api.service';
import { ImageCompressionService } from '../../../core/services/image-compression.service';

const DEFAULT_ALLOWED_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg'];

interface Asset {
  assetId: number;
  assetName?: string;
  fileName: string;
  fileType: string;
  fileSize: number;
  fileUrl: string;
  category?: string;
}

@Component({
  selector: 'app-asset-upload',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatTableModule, MatButtonModule, MatIconModule,
    MatCardModule, MatProgressBarModule, MatDialogModule, MatFormFieldModule, MatInputModule,
  ],
  template: `
    <mat-card>
      <mat-card-header>
        <mat-card-title>{{ title }}</mat-card-title>
      </mat-card-header>
      <mat-card-content>

        <!-- Asset name input -->
        <mat-form-field appearance="outline" class="asset-name-field">
          <mat-label>Asset Name / Description</mat-label>
          <input matInput [(ngModel)]="assetName" [placeholder]="namePlaceholder" [disabled]="disabled" />
        </mat-form-field>

        <div class="upload-area"
          [class.dragover]="isDragOver"
          [class.disabled]="disabled"
          (dragover)="onDragOver($event)"
          (dragleave)="isDragOver = false"
          (drop)="onDrop($event)">
          <mat-icon>cloud_upload</mat-icon>
          <p>Drag & drop files here or</p>
          <button mat-raised-button color="primary" (click)="fileInput.click()" [disabled]="disabled">Browse Files</button>
          <input #fileInput type="file" [multiple]="multiple" hidden
            [accept]="acceptString"
            (change)="onFilesSelected($event)" />
          <p class="allowed-hint">{{ hintText }}</p>
        </div>

        @if (uploading) {
          <mat-progress-bar mode="indeterminate"></mat-progress-bar>
        }

        @if (assets.length > 0) {
          <table mat-table [dataSource]="assets" class="full-width">
            <ng-container matColumnDef="assetName">
              <th mat-header-cell *matHeaderCellDef>Name</th>
              <td mat-cell *matCellDef="let row">{{ row.assetName || '-' }}</td>
            </ng-container>
            <ng-container matColumnDef="fileName">
              <th mat-header-cell *matHeaderCellDef>File</th>
              <td mat-cell *matCellDef="let row">{{ row.fileName }}</td>
            </ng-container>
            <ng-container matColumnDef="fileType">
              <th mat-header-cell *matHeaderCellDef>Type</th>
              <td mat-cell *matCellDef="let row">{{ formatType(row.fileType) }}</td>
            </ng-container>
            <ng-container matColumnDef="fileSize">
              <th mat-header-cell *matHeaderCellDef>Size</th>
              <td mat-cell *matCellDef="let row">{{ formatSize(row.fileSize) }}</td>
            </ng-container>
            <ng-container matColumnDef="actions">
              <th mat-header-cell *matHeaderCellDef>Actions</th>
              <td mat-cell *matCellDef="let row">
                <button mat-icon-button color="primary" (click)="download(row)" matTooltip="Download">
                  <mat-icon>download</mat-icon>
                </button>
                <button mat-icon-button color="warn" (click)="deleteAsset(row)" matTooltip="Delete">
                  <mat-icon>delete</mat-icon>
                </button>
              </td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          </table>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .asset-name-field {
      width: 100%;
      margin-bottom: 8px;
    }
    .upload-area {
      border: 2px dashed #ccc; border-radius: 8px; padding: 2rem; text-align: center;
      margin-bottom: 1rem; cursor: pointer; transition: all 0.2s;
      mat-icon { font-size: 48px; width: 48px; height: 48px; color: #999; }
      p { color: #666; margin: 8px 0; }
    }
    .upload-area.dragover { border-color: #1a478a; background: #f0f4ff; }
    .upload-area.disabled { opacity: 0.5; pointer-events: none; }
    .allowed-hint { font-size: 11px; color: #999; margin-top: 8px !important; }
    .full-width { width: 100%; margin-top: 1rem; }
  `],
})
export class AssetUploadComponent implements OnInit, OnChanges {
  @Input() enqid?: number;
  @Input() quotId?: number;

  /** Asset category stored on each row + used as list filter. */
  @Input() category?: string;

  /** Optional mat-card title (default "Attachments"). */
  @Input() title = 'Attachments';

  /** Placeholder for the Asset Name field. */
  @Input() namePlaceholder = 'e.g. Purchase Order, Drawing, Spec Sheet';

  /** Override allowed extensions (lowercase, no dots). */
  @Input() allowedExtensions: string[] = DEFAULT_ALLOWED_EXTENSIONS;

  /** Max size in MB per file (after image compression). 0 = no client-side cap. */
  @Input() maxSizeMb = 0;

  /** If true, images are canvas-compressed before upload. */
  @Input() compressImages = false;

  /** Disable multi-file select (e.g. for PO doc where one is typical). */
  @Input() multiple = true;

  /** Fully disable the upload UI (card stays visible for listing). */
  @Input() disabled = false;

  /** Custom hint text below the dropzone. */
  @Input() hintText = 'Allowed: PDF, Word, Excel, PNG, JPG';

  /** Emits after a successful upload or delete so parents can refresh state. */
  @Output() changed = new EventEmitter<Asset[]>();

  assets: Asset[] = [];
  uploading = false;
  isDragOver = false;
  assetName = '';
  displayedColumns = ['assetName', 'fileName', 'fileType', 'fileSize', 'actions'];

  constructor(
    private http: HttpClient,
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private imageCompressor: ImageCompressionService,
  ) {}

  get acceptString(): string {
    return this.allowedExtensions.map(e => `.${e}`).join(',');
  }

  ngOnInit(): void { this.loadAssets(); }
  ngOnChanges(): void { this.loadAssets(); }

  loadAssets(): void {
    const params: any = {};
    if (this.enqid) params.enqid = this.enqid;
    if (this.quotId) params.quotId = this.quotId;
    if (this.category) params.category = this.category;
    this.api.get<{ items: Asset[] }>('/assets', { ...params, pageSize: '100' }).subscribe({
      next: res => {
        this.assets = res.items;
        this.changed.emit(this.assets);
      },
    });
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = true;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
    if (event.dataTransfer?.files) {
      this.uploadFiles(event.dataTransfer.files);
    }
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) this.uploadFiles(input.files);
    input.value = ''; // reset so same file can be re-selected
  }

  async uploadFiles(files: FileList): Promise<void> {
    // Client-side extension check
    const invalid: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const ext = files[i].name.split('.').pop()?.toLowerCase() || '';
      if (!this.allowedExtensions.includes(ext)) {
        invalid.push(files[i].name);
      }
    }
    if (invalid.length) {
      this.notify.error(`Not allowed: ${invalid.join(', ')}. Allowed: ${this.allowedExtensions.join(', ')}`);
      return;
    }

    this.uploading = true;

    // Pre-process: compress images (if enabled) and enforce size cap
    const maxBytes = this.maxSizeMb > 0 ? this.maxSizeMb * 1024 * 1024 : 0;
    const prepared: File[] = [];
    try {
      for (let i = 0; i < files.length; i++) {
        let f: File = files[i];
        if (this.compressImages && this.imageCompressor.isCompressible(f)) {
          f = await this.imageCompressor.compress(f);
        }
        if (maxBytes > 0 && f.size > maxBytes) {
          this.notify.error(
            `"${f.name}" is ${(f.size / (1024 * 1024)).toFixed(1)} MB — exceeds the ${this.maxSizeMb} MB limit.`,
          );
          this.uploading = false;
          return;
        }
        prepared.push(f);
      }
    } catch {
      this.uploading = false;
      this.notify.error('Failed to process file before upload.');
      return;
    }

    let completed = 0;
    const total = prepared.length;

    for (const file of prepared) {
      const formData = new FormData();
      formData.append('file', file);
      if (this.assetName.trim()) {
        formData.append('assetName', this.assetName.trim());
      }
      if (this.enqid) formData.append('enqid', this.enqid.toString());
      if (this.quotId) formData.append('quotId', this.quotId.toString());
      if (this.category) formData.append('category', this.category);

      this.http.post(`${environment.apiUrl}/assets/upload`, formData).subscribe({
        next: () => {
          completed++;
          if (completed === total) {
            this.uploading = false;
            this.assetName = '';
            this.notify.success(`${total} file${total > 1 ? 's' : ''} uploaded`);
            this.loadAssets();
          }
        },
        error: (err) => {
          completed++;
          if (completed === total) this.uploading = false;
          const msg = err?.error?.detail || 'Upload failed';
          this.notify.error(msg);
        },
      });
    }
  }

  download(asset: Asset): void {
    // Backend streams the file directly with proper Content-Disposition
    const url = `${environment.apiUrl}/assets/${asset.assetId}/download`;
    this.http.get(url, { responseType: 'blob', observe: 'response' }).subscribe({
      next: (resp) => {
        const blob = resp.body;
        if (!blob) {
          this.notify.error('Empty file');
          return;
        }
        // Prefer filename from Content-Disposition; fallback to stored fileName
        let filename = asset.fileName || `asset-${asset.assetId}`;
        const cd = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
        if (cd) {
          const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
          if (match && match[1]) {
            try {
              filename = decodeURIComponent(match[1]);
            } catch {
              filename = match[1];
            }
          }
        }
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
      },
      error: (err) => {
        const msg = err?.error?.detail || 'Download failed';
        this.notify.error(typeof msg === 'string' ? msg : 'Download failed');
      },
    });
  }

  deleteAsset(asset: Asset): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: { title: 'Delete File', message: `Delete "${asset.assetName || asset.fileName}"?` },
    });
    ref.afterClosed().subscribe(c => {
      if (c) {
        this.api.delete(`/assets/${asset.assetId}`).subscribe({
          next: () => {
            this.notify.success('Deleted');
            this.loadAssets();
          },
          error: () => this.notify.error('Failed'),
        });
      }
    });
  }

  formatSize(bytes: number): string {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  formatType(mime: string): string {
    if (!mime) return '-';
    const map: Record<string, string> = {
      'application/pdf': 'PDF',
      'application/msword': 'DOC',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
      'application/vnd.ms-excel': 'XLS',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
      'image/png': 'PNG',
      'image/jpeg': 'JPG',
    };
    return map[mime] || mime.split('/').pop()?.toUpperCase() || mime;
  }
}
