import { Injectable } from '@angular/core';

export interface ImageCompressOptions {
  maxDimensionPx?: number;   // longest edge; default 3000
  quality?: number;          // JPEG/WebP quality 0-1; default 0.9
  mimeType?: string;         // output; default 'image/jpeg' (falls back if PNG has alpha)
}

/**
 * Canvas-based image compression. Modular by design: tweak defaults in one
 * place, or pass custom options per call. Non-image files pass through
 * untouched so the same call-site works for mixed PDFs + images.
 *
 * Trade-offs kept visible:
 *  - Output MIME defaults to JPEG (smaller files, widest compatibility).
 *    PNG inputs with transparency are converted to white-background JPEG —
 *    acceptable for scans/photos; override with mimeType='image/png' if not.
 *  - Only downscales; never upscales. If the image is already smaller than
 *    maxDimensionPx, we still re-encode to apply quality reduction.
 *  - If the browser can't decode the file (corrupt or exotic format), the
 *    original File is returned and the caller can rely on server-side checks.
 */
@Injectable({ providedIn: 'root' })
export class ImageCompressionService {

  private static readonly DEFAULTS: Required<ImageCompressOptions> = {
    maxDimensionPx: 3000,
    quality: 0.9,
    mimeType: 'image/jpeg',
  };

  /** True for file types we'll try to compress. Others returned as-is. */
  isCompressible(file: File): boolean {
    return /^image\/(jpeg|png|webp)$/i.test(file.type);
  }

  async compress(file: File, opts: ImageCompressOptions = {}): Promise<File> {
    if (!this.isCompressible(file)) return file;

    const options: Required<ImageCompressOptions> = { ...ImageCompressionService.DEFAULTS, ...opts };

    try {
      const bitmap = await this.decode(file);
      const { width, height } = this.fitWithin(bitmap.width, bitmap.height, options.maxDimensionPx);

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return file;

      // White backdrop so transparent PNGs → clean JPEG output
      if (options.mimeType === 'image/jpeg') {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
      }
      ctx.drawImage(bitmap, 0, 0, width, height);

      const blob = await this.toBlob(canvas, options.mimeType, options.quality);
      if (!blob) return file;

      // If compression made the file bigger (rare, tiny images), keep the original
      if (blob.size >= file.size) return file;

      const outName = this.replaceExtension(file.name, options.mimeType);
      return new File([blob], outName, { type: options.mimeType, lastModified: Date.now() });
    } catch {
      return file;
    }
  }

  private decode(file: File): Promise<HTMLImageElement | ImageBitmap> {
    if ('createImageBitmap' in window) {
      return createImageBitmap(file);
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
      img.src = url;
    });
  }

  private fitWithin(w: number, h: number, maxEdge: number): { width: number; height: number } {
    if (w <= maxEdge && h <= maxEdge) return { width: w, height: h };
    const scale = Math.min(maxEdge / w, maxEdge / h);
    return { width: Math.round(w * scale), height: Math.round(h * scale) };
  }

  private toBlob(canvas: HTMLCanvasElement, mime: string, quality: number): Promise<Blob | null> {
    return new Promise(resolve => canvas.toBlob(resolve, mime, quality));
  }

  private replaceExtension(name: string, mime: string): string {
    const base = name.replace(/\.[^.]+$/, '');
    const ext = mime === 'image/png' ? 'png' : mime === 'image/webp' ? 'webp' : 'jpg';
    return `${base}.${ext}`;
  }
}
