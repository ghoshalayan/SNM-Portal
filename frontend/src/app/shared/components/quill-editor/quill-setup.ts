import Quill from 'quill';

const Parchment = Quill.import('parchment') as any;

// ===== Line Height — inline style for print portability =====
const lineHeightStyle = new Parchment.StyleAttributor('lineHeight', 'line-height', {
  scope: Parchment.Scope.BLOCK,
  whitelist: ['1', '1.15', '1.5', '1.75', '2', '2.5', '3'],
});
Quill.register(lineHeightStyle, true);

// ===== Alignment — inline style so it survives outside Quill =====
const AlignStyle = Quill.import('attributors/style/align') as any;
Quill.register(AlignStyle, true);

// ===== Font Size (extended) — inline style =====
const SizeStyle = Quill.import('attributors/style/size') as any;
SizeStyle.whitelist = [
  '8px', '9px', '10px', '11px', '12px', '14px', '16px', '18px',
  '20px', '24px', '28px', '32px', '36px', '48px', '72px',
];
Quill.register(SizeStyle, true);

// ===== Font Family (extended) — inline style =====
const FontStyle = Quill.import('attributors/style/font') as any;
FontStyle.whitelist = [
  'arial', 'times-new-roman', 'calibri', 'georgia', 'verdana',
  'courier-new', 'trebuchet-ms', 'comic-sans-ms', 'tahoma',
];
Quill.register(FontStyle, true);

export { Quill };
