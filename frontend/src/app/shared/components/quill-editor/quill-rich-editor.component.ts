import {
  Component,
  Input,
  OnInit,
  ViewChild,
  ElementRef,
  forwardRef,
  OnDestroy,
  AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { Quill } from './quill-setup';

@Component({
  selector: 'app-quill-rich-editor',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="editor-container">
      <div #toolbar class="ql-toolbar ql-snow">
        <!-- Row 1: Text formatting -->
        <span class="ql-formats">
          <select class="ql-font">
            <option value="">Default</option>
            <option value="arial">Arial</option>
            <option value="times-new-roman">Times New Roman</option>
            <option value="calibri">Calibri</option>
            <option value="georgia">Georgia</option>
            <option value="verdana">Verdana</option>
            <option value="courier-new">Courier New</option>
            <option value="trebuchet-ms">Trebuchet MS</option>
            <option value="tahoma">Tahoma</option>
          </select>
          <select class="ql-size">
            <option value="8px">8</option>
            <option value="9px">9</option>
            <option value="10px">10</option>
            <option value="11px">11</option>
            <option value="12px">12</option>
            <option value="14px">14</option>
            <option selected>Default</option>
            <option value="18px">18</option>
            <option value="20px">20</option>
            <option value="24px">24</option>
            <option value="28px">28</option>
            <option value="32px">32</option>
            <option value="36px">36</option>
            <option value="48px">48</option>
            <option value="72px">72</option>
          </select>
        </span>

        <span class="ql-formats">
          <button class="ql-bold"></button>
          <button class="ql-italic"></button>
          <button class="ql-underline"></button>
          <button class="ql-strike"></button>
        </span>

        <span class="ql-formats">
          <select class="ql-color"></select>
          <select class="ql-background"></select>
        </span>

        <span class="ql-formats">
          <select class="ql-header">
            <option value="1">H1</option>
            <option value="2">H2</option>
            <option value="3">H3</option>
            <option selected>Normal</option>
          </select>
        </span>

        <!-- Row 2: Paragraph, line height, lists, alignment -->
        <span class="ql-formats">
          <select class="ql-lineHeight" title="Line Spacing">
            <option selected value="">Default</option>
            <option value="1">1.0</option>
            <option value="1.15">1.15</option>
            <option value="1.5">1.5</option>
            <option value="1.75">1.75</option>
            <option value="2">2.0</option>
            <option value="2.5">2.5</option>
            <option value="3">3.0</option>
          </select>
        </span>

        <span class="ql-formats">
          <button class="ql-list" value="ordered"></button>
          <button class="ql-list" value="bullet"></button>
          <button class="ql-indent" value="-1"></button>
          <button class="ql-indent" value="+1"></button>
        </span>

        <span class="ql-formats">
          <select class="ql-align"></select>
        </span>

        <span class="ql-formats">
          <button class="ql-link"></button>
          <button class="ql-image"></button>
        </span>

        <span class="ql-formats">
          <button class="ql-clean"></button>
        </span>
      </div>
      <div #editorEl></div>
    </div>
  `,
  styles: [`
    .editor-container {
      border: 1px solid #ccc;
      border-radius: 4px;
      overflow: hidden;
    }
    :host ::ng-deep .ql-toolbar.ql-snow {
      border: none;
      border-bottom: 1px solid #ccc;
      background: #fafafa;
    }
    :host ::ng-deep .ql-container.ql-snow {
      border: none;
      font-family: 'Segoe UI', Arial, sans-serif;
      font-size: 13px;
    }
    :host ::ng-deep .ql-editor {
      min-height: 250px;
    }
    /* Style the line-height dropdown label */
    :host ::ng-deep .ql-snow .ql-picker.ql-lineHeight .ql-picker-label::before {
      content: 'Spacing';
    }
    :host ::ng-deep .ql-snow .ql-picker.ql-lineHeight .ql-picker-item::before {
      content: attr(data-value) 'x';
    }
    :host ::ng-deep .ql-snow .ql-picker.ql-lineHeight .ql-picker-item[data-value=""]::before {
      content: 'Default';
    }
    :host ::ng-deep .ql-snow .ql-picker.ql-lineHeight {
      width: 90px;
    }
    /* Font name display */
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="arial"]::before { content: 'Arial'; font-family: Arial; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="arial"]::before { content: 'Arial'; font-family: Arial; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="times-new-roman"]::before { content: 'Times New Roman'; font-family: 'Times New Roman'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="times-new-roman"]::before { content: 'Times New Roman'; font-family: 'Times New Roman'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="calibri"]::before { content: 'Calibri'; font-family: Calibri; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="calibri"]::before { content: 'Calibri'; font-family: Calibri; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="georgia"]::before { content: 'Georgia'; font-family: Georgia; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="georgia"]::before { content: 'Georgia'; font-family: Georgia; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="verdana"]::before { content: 'Verdana'; font-family: Verdana; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="verdana"]::before { content: 'Verdana'; font-family: Verdana; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="courier-new"]::before { content: 'Courier New'; font-family: 'Courier New'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="courier-new"]::before { content: 'Courier New'; font-family: 'Courier New'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="trebuchet-ms"]::before { content: 'Trebuchet MS'; font-family: 'Trebuchet MS'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="trebuchet-ms"]::before { content: 'Trebuchet MS'; font-family: 'Trebuchet MS'; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-item[data-value="tahoma"]::before { content: 'Tahoma'; font-family: Tahoma; }
    :host ::ng-deep .ql-snow .ql-picker.ql-font .ql-picker-label[data-value="tahoma"]::before { content: 'Tahoma'; font-family: Tahoma; }
    /* Apply actual font-family */
    :host ::ng-deep .ql-font-arial { font-family: Arial, sans-serif; }
    :host ::ng-deep .ql-font-times-new-roman { font-family: 'Times New Roman', serif; }
    :host ::ng-deep .ql-font-calibri { font-family: Calibri, sans-serif; }
    :host ::ng-deep .ql-font-georgia { font-family: Georgia, serif; }
    :host ::ng-deep .ql-font-verdana { font-family: Verdana, sans-serif; }
    :host ::ng-deep .ql-font-courier-new { font-family: 'Courier New', monospace; }
    :host ::ng-deep .ql-font-trebuchet-ms { font-family: 'Trebuchet MS', sans-serif; }
    :host ::ng-deep .ql-font-tahoma { font-family: Tahoma, sans-serif; }
  `],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => QuillRichEditorComponent),
      multi: true,
    },
  ],
})
export class QuillRichEditorComponent implements AfterViewInit, OnDestroy, ControlValueAccessor {
  @ViewChild('editorEl', { static: true }) editorEl!: ElementRef<HTMLDivElement>;
  @ViewChild('toolbar', { static: true }) toolbar!: ElementRef<HTMLDivElement>;
  @Input() placeholder = '';
  @Input() editorHeight = 300;

  private quill!: any;
  private value = '';
  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  ngAfterViewInit() {
    this.quill = new Quill(this.editorEl.nativeElement, {
      theme: 'snow',
      placeholder: this.placeholder,
      modules: {
        toolbar: this.toolbar.nativeElement,
      },
    });

    // Set height
    const editorDiv = this.editorEl.nativeElement.querySelector('.ql-editor') as HTMLElement;
    if (editorDiv) {
      editorDiv.style.minHeight = this.editorHeight + 'px';
    }

    // Set initial value
    if (this.value) {
      this.quill.root.innerHTML = this.value;
    }

    // Listen for changes
    this.quill.on('text-change', () => {
      const html = this.quill.root.innerHTML;
      this.value = html === '<p><br></p>' ? '' : html;
      this.onChange(this.value);
    });

    this.quill.on('selection-change', (range: any) => {
      if (!range) {
        this.onTouched();
      }
    });
  }

  ngOnDestroy() {
    // Quill cleans up with the DOM
  }

  writeValue(val: string): void {
    this.value = val || '';
    if (this.quill) {
      this.quill.root.innerHTML = this.value;
    }
  }

  registerOnChange(fn: (val: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }
}
