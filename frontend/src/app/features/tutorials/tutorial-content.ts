/**
 * Tutorial content store. Each entry is a structured walkthrough rendered
 * by TutorialDialogComponent — no Markdown parser, just strongly-typed
 * sections so we can style consistently and keep the bundle small.
 *
 * To add a tutorial: define a new TutorialId and add an entry to
 * TUTORIALS. To extend an existing one: add another Section. Sections
 * render in order with subtle dividers between them.
 */

export type TutorialId =
  | 'customer'
  | 'enquiry'
  | 'quotation'
  | 'raw-material-cost';

export interface TutorialStep {
  /** Bold label shown at the start of the step (e.g. "Open the form"). */
  label?: string;
  /** Plain-text body. Newlines render as paragraph breaks. */
  body: string;
}

export interface TutorialSection {
  heading: string;
  /** One short intro paragraph displayed under the heading (optional). */
  intro?: string;
  /** Numbered/bulleted steps under the section. */
  steps: TutorialStep[];
}

export interface Tutorial {
  id: TutorialId;
  title: string;
  /** One-sentence subtitle shown under the title in the dialog header. */
  subtitle: string;
  /** Material icon name shown beside the title and in the menu. */
  icon: string;
  /** Where to navigate to find the feature, shown as a breadcrumb. */
  whereToFind: string[];
  sections: TutorialSection[];
}

export const TUTORIALS: Record<TutorialId, Tutorial> = {
  // ============================================================
  // CUSTOMER
  // ============================================================
  customer: {
    id: 'customer',
    title: 'Customers',
    subtitle: 'Manage customer master data, contacts, and sites.',
    icon: 'groups',
    whereToFind: ['Sidebar', 'Customers'],
    sections: [
      {
        heading: 'Where to find it',
        intro:
          'Customers is the master list of buyers your company sells to. ' +
          'Each customer can have multiple contacts (people) and multiple ' +
          'sites (billing / consignee addresses).',
        steps: [
          {
            label: 'Open the list',
            body:
              'Click "Customers" in the left sidebar. The list shows ' +
              'customer name, code, classification (e.g. Trader / OEM), ' +
              'GSTN, and PAN.',
          },
          {
            label: 'Search and paginate',
            body:
              'The search box matches customer name, code, or GSTN. The ' +
              'list is server-paginated — page size dropdown sits at the ' +
              'bottom right.',
          },
        ],
      },
      {
        heading: 'Create a customer',
        steps: [
          {
            label: 'Click "Add Customer"',
            body:
              'Top-right of the list. Required fields: Customer Name. ' +
              'Optional but commonly filled: Customer Code, GSTN, PAN, ' +
              'Classification.',
          },
          {
            label: 'Save',
            body:
              'Saving creates the customer master record. Contacts and ' +
              'sites are managed under separate tabs on the customer ' +
              'detail page.',
          },
        ],
      },
      {
        heading: 'Add contacts',
        intro:
          'Contacts are the people you talk to at the customer ' +
          '(purchase manager, accounts, etc.). They are picked when ' +
          'creating an enquiry or quotation.',
        steps: [
          {
            label: 'Open the Contacts tab',
            body:
              'On the customer detail page, switch to the "Contacts" tab ' +
              'and click "Add Contact".',
          },
          {
            label: 'Fill in details',
            body:
              'Contact Person Name, Designation, Phone, Email, and an ' +
              'optional Contact Type (Primary / Secondary / Accounts). ' +
              'State and District drive location-based access — only ' +
              'users assigned to that region will see this contact.',
          },
        ],
      },
      {
        heading: 'Add sites (addresses)',
        intro:
          'Sites are addresses you ship to or bill. Each site has its ' +
          'own GST and contact details. The first site can be marked ' +
          'as Head Office.',
        steps: [
          {
            label: 'Open the Sites tab',
            body:
              'On the customer detail page, switch to the "Sites" tab ' +
              'and click "Add Site".',
          },
          {
            label: 'Fill in the address',
            body:
              'Site Address Code is auto-generated from the customer ' +
              'code (e.g. CUST001, CUST001/1, CUST001/2). The Country → ' +
              'State → District dropdowns cascade — pick country first, ' +
              'then state. PIN, primary contact (name + phone + email) ' +
              'and the "Mark as Head Office" checkbox finish the form.',
          },
        ],
      },
      {
        heading: 'Tips',
        steps: [
          {
            body:
              'You can also save a site on-the-fly while capturing a ' +
              'Purchase Order on a quotation — pick "Manual Entry" in ' +
              'the Site dropdown, fill in the address, and tick "Save ' +
              'this address permanently". It then appears in the regular ' +
              'site picker for future use.',
          },
          {
            body:
              'Soft delete: deleting a customer marks it inactive. ' +
              'It disappears from pickers but historical enquiries / ' +
              'quotations referencing it stay intact.',
          },
        ],
      },
    ],
  },

  // ============================================================
  // ENQUIRY
  // ============================================================
  enquiry: {
    id: 'enquiry',
    title: 'Enquiries',
    subtitle: 'Capture incoming buyer enquiries and price them.',
    icon: 'help_outline',
    whereToFind: ['Sidebar', 'Enquiries'],
    sections: [
      {
        heading: 'Where to find it',
        intro:
          'An enquiry is the first stage — a customer asks for prices ' +
          'on a list of items. You record the items, dia, length, ' +
          'quantity, and run costing on them. Approved enquiries can be ' +
          'converted into a Quotation.',
        steps: [
          {
            label: 'Open the list',
            body:
              'Click "Enquiries" in the left sidebar. The list shows ' +
              'enquiry number, customer, status, and total quantity.',
          },
        ],
      },
      {
        heading: 'Create an enquiry',
        steps: [
          {
            label: 'Click "New Enquiry"',
            body:
              'The form opens with header fields: Customer, Contact, ' +
              'Site, Enquiry Date, and Reference No. Pick the customer ' +
              'first — contact and site dropdowns then filter to that ' +
              'customer.',
          },
          {
            label: 'Add line items',
            body:
              'In the Line Items section click "Add Item". Required: ' +
              'Item Grade (defaults to 550D for new lines, override from ' +
              'the dropdown), Item Name (e.g. TMT Bar), Dia, Length, ' +
              'Unit (default MT), Quantity. Remarks are optional.',
          },
          {
            label: 'Save',
            body:
              'Saving creates the enquiry in Draft status. The list now ' +
              'shows it under your ownership.',
          },
        ],
      },
      {
        heading: 'Costing',
        intro:
          'After the line items are saved, the Costing tab opens up. ' +
          'This is where you compute landed cost and propose a price.',
        steps: [
          {
            label: 'Open the Costing tab',
            body:
              'Inside the enquiry form. The grid shows each line with ' +
              'columns for raw material cost, conversion, freight, ' +
              'overheads, margin, and final price.',
          },
          {
            label: 'Apply raw material rates',
            body:
              'The grid auto-pulls the latest active raw material cost ' +
              'for the matching grade + dia from the Raw Material Cost ' +
              'master. You can override per-line if needed.',
          },
          {
            label: 'Versioning',
            body:
              'Each saved costing creates a new version. Older versions ' +
              'become read-only — useful when you want to revise a quote ' +
              'without losing history.',
          },
        ],
      },
      {
        heading: 'Status & ownership',
        steps: [
          {
            label: 'Approve',
            body:
              'A user with "Can Approve" permission moves the enquiry ' +
              'from Draft to Approved. Once approved, the enquiry is ' +
              'eligible to be imported into a quotation.',
          },
          {
            label: 'Handover',
            body:
              'Transfers ownership to another user — used when the ' +
              'enquiry needs to be picked up by a different rep. The ' +
              'target user must be in your visibility tree.',
          },
        ],
      },
    ],
  },

  // ============================================================
  // QUOTATION
  // ============================================================
  quotation: {
    id: 'quotation',
    title: 'Quotations',
    subtitle:
      'The full quote-to-PO-to-Annexure lifecycle in one form.',
    icon: 'receipt_long',
    whereToFind: ['Sidebar', 'Quotations'],
    sections: [
      {
        heading: 'Where to find it',
        intro:
          'Quotations is the most feature-rich module. A single form ' +
          'walks through four stages: Quotation → Purchase Order → ' +
          'Viability Sheet → Annexure. Each stage has its own status, ' +
          'version history, and lock/unlock control.',
        steps: [
          {
            label: 'Open the list',
            body:
              'Click "Quotations" in the sidebar. Filter by status ' +
              '(Draft / Approved / Converted / Reject / Revised) using ' +
              'the chip filter at the top.',
          },
        ],
      },
      {
        heading: 'Stage 1 — Quotation',
        intro:
          'Capture the quote header, line items with cost heads, and ' +
          'terms & conditions. Same structure as an enquiry but with ' +
          'pricing for the customer.',
        steps: [
          {
            label: 'Header',
            body:
              'Customer, Contact, Site, Quotation Date, Reference No., ' +
              'Delivery Term (FOR / Ex-Works / etc.), Mode of Dispatch ' +
              '(Trailer / Truck) — these last two affect freight ' +
              'calculation rules.',
          },
          {
            label: 'Working Sheet (line items)',
            body:
              'Item Grade defaults to 550D. Each line carries cost ' +
              'heads: TPW+GST, Marketing, Freight (Trailer or Truck per ' +
              'mode), Unloading, OHD, IFC, etc. Some heads auto-lock ' +
              'based on the Delivery Term — locked cells show a tooltip ' +
              'explaining why.',
          },
          {
            label: 'Terms & Conditions',
            body:
              'The Terms tab pulls from a master. Drag to reorder; ' +
              'click "Import from Master" to add standard clauses.',
          },
          {
            label: 'Toolbar actions',
            body:
              'Approve (Draft → Approved), Revise (creates a new ' +
              'version while archiving the current one), Reject, and ' +
              'Handover. After approval, the Convert button unlocks ' +
              'Stage 2.',
          },
        ],
      },
      {
        heading: 'Stage 2 — Purchase Order',
        intro:
          'When the customer issues a PO, you record it here. The PO ' +
          'has its own Final Working Sheet which can differ from the ' +
          'quoted BOM (qty / price changes are common).',
        steps: [
          {
            label: 'Convert',
            body:
              'On an Approved quotation, click Convert (Stage 1 ' +
              'toolbar). A blank PO is created and the Final Working ' +
              'Sheet is auto-populated from the quotation line items.',
          },
          {
            label: 'Capture PO',
            body:
              'Stage 2 toolbar → Edit PO. Fill in PO Number, PO Date, ' +
              'and override the Customer / Contact / Billing / Consignee ' +
              'addresses if the PO uses different ones than the quote.',
          },
          {
            label: 'Final Working Sheet',
            body:
              'A sub-tab on Stage 2. Same line-item grid as Stage 1, ' +
              'but bound to the PO. Edit qty / cost heads to match the ' +
              'actual PO. Locked once the PO is Submitted.',
          },
          {
            label: 'Submit & Mature',
            body:
              'Snapshots the Final Working Sheet (no further edits) and ' +
              'opens Stage 3. To roll back, use Reject PO — the ' +
              'quotation flips to Approved so you can Revise & re-Convert.',
          },
        ],
      },
      {
        heading: 'Stage 3 — Viability Sheet',
        intro:
          'A landed-cost analysis: latest raw material rates × Final ' +
          'Working Sheet quantities = projected margin per line.',
        steps: [
          {
            label: 'Generate Viability',
            body:
              'On a Submitted PO, click Generate Viability. The system ' +
              'reads from the Final Working Sheet and pulls live rates ' +
              'from the Raw Material Cost master.',
          },
          {
            label: 'Review & approve',
            body:
              'The viability sheet shows raw material breakdown, ' +
              'conversion costs, freight, GST, and final margin per ' +
              'line. A user with "Can Approve Viability" approves it; ' +
              'after approval, both the PO and Viability pages are ' +
              'locked.',
          },
        ],
      },
      {
        heading: 'Stage 4 — Annexure',
        intro:
          'The customer-facing PDF appendix attached to the quotation. ' +
          'Letterhead-style document showing dispatch terms, delivery ' +
          'schedule, and signatory.',
        steps: [
          {
            label: 'Generate Annexure',
            body:
              'On an Approved Viability, click Generate Annexure. A ' +
              'draft annexure is created with auto-populated fields ' +
              '(Addressed To = consignee address, Company Name from ' +
              'the company master, etc.).',
          },
          {
            label: 'Edit and approve',
            body:
              'Editable fields: From / To headers, transport charges, ' +
              'delivery schedule, signatory line. Click Approve ' +
              'Annexure to lock it; export to PDF from the Print toolbar.',
          },
        ],
      },
      {
        heading: 'Version history & Unlock',
        steps: [
          {
            label: 'Version pill',
            body:
              'Top of every stage card shows "vN of M". Click to drop ' +
              'down past versions in read-only mode. Restore button ' +
              'creates a new head version from the past one.',
          },
          {
            label: 'Unlock & Edit',
            body:
              'Privileged escape valve — admins with the matching ' +
              '"Can Unlock & Edit {Stage}" permission can reopen a ' +
              'locked stage for in-place edits. A reason dialog logs ' +
              'the action to LifecycleUnlockAudit.',
          },
        ],
      },
    ],
  },

  // ============================================================
  // RAW MATERIAL COST
  // ============================================================
  'raw-material-cost': {
    id: 'raw-material-cost',
    title: 'Raw Material Cost',
    subtitle: 'Maintain time-effective rates per grade & dia.',
    icon: 'savings',
    whereToFind: ['Sidebar', 'Masters', 'Raw Material Cost'],
    sections: [
      {
        heading: 'Where to find it',
        intro:
          'Raw Material Cost is the rate book the Viability Sheet pulls ' +
          'from when computing margin. Rates are time-effective — each ' +
          'row has an "Effective From" date and only the latest active ' +
          'row per (grade, dia) is used.',
        steps: [
          {
            label: 'Navigate',
            body:
              'Sidebar → Masters → Raw Material Cost. The list shows ' +
              'Item Grade, Dia, Effective From date, TP Cost, Diff From ' +
              'Base, and Active/Inactive status.',
          },
        ],
      },
      {
        heading: 'Add or update a rate',
        steps: [
          {
            label: 'Click "Add Rate"',
            body:
              'Required: Item Grade, Dia, Effective From date, TP Cost ' +
              '(per MT or per piece depending on item). Optional: Diff ' +
              'From Base (used to mark which size is the "base" cost).',
          },
          {
            label: 'Marking a base size',
            body:
              'Leave Diff From Base blank for whichever size you ' +
              'consider the reference (commonly 16 mm for TMT). Other ' +
              'sizes record their delta against that base — useful for ' +
              'reporting and bulk updates.',
          },
          {
            label: 'Effective dating',
            body:
              'Always create a new row with a future Effective From ' +
              'date rather than overwriting the current row. This ' +
              'preserves history — old quotations still show the rate ' +
              'that was active when they were costed.',
          },
        ],
      },
      {
        heading: 'How it feeds the Viability Sheet',
        steps: [
          {
            body:
              'When you Generate Viability on a quotation\'s ' +
              'Submitted PO, the system reads each Final Working Sheet ' +
              'line\'s grade + dia, looks up the Raw Material Cost row ' +
              'with the latest Effective From ≤ today, and uses that TP ' +
              'Cost as the raw material rate. If no row matches, the ' +
              'line is flagged as "rate missing" and the viability ' +
              'cannot be approved until you add the rate.',
          },
        ],
      },
      {
        heading: 'Tips',
        steps: [
          {
            body:
              'Soft delete (deactivate) an old row instead of hard- ' +
              'deleting if the rate is no longer used — it keeps the ' +
              'audit trail clean and lets you reactivate later.',
          },
          {
            body:
              'For a bulk price change (e.g. monthly market revision), ' +
              'add one new row per (grade, dia) with the new Effective ' +
              'From date. The Smart Analysis chatbot can answer ' +
              '"what changed in raw material costs this month?" by ' +
              'querying this table.',
          },
        ],
      },
    ],
  },
};
