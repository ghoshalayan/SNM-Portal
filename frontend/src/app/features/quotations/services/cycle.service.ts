import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../../core/services/api.service';

/** A single cycle row, shape mirrors backend ``CycleResponse``. */
export interface OrderCycle {
  quotOrderCycleId: number;
  companyId: number;
  quotId: number;
  cycleNo: number;
  status: 'Active' | 'Complete' | 'Abandoned';
  parentCycleId: number | null;
  startedOn: string;
  startedBy: number;
  closedOn: string | null;
  closedBy: number | null;
  notes: string | null;
  isActive: boolean;
}

export interface CycleListResponse {
  cycles: OrderCycle[];
}

/** Bundle returned by ``GET /cycles/{cId}/bundle``. POs come back with
 *  the full ``QuotPurchaseOrderResponse`` shape; WS/viability/annexure
 *  are lite refs (id + status) so the frontend can decide whether to
 *  fetch the full sheets on demand. */
export interface OrderCycleBundle {
  cycle: OrderCycle;
  purchaseOrders: CyclePurchaseOrder[];
  workingSheetLineCount: number;
  viabilityId: number | null;
  viabilityStatus: string | null;
  annexureId: number | null;
  annexureStatus: string | null;
}

export interface CycleHistory {
  bundles: OrderCycleBundle[];
}

export interface CyclePurchaseOrder {
  quotPOId: number;
  companyId: number;
  quotId: number;
  parentPOId: number | null;
  versionNo: number;
  status: string;
  poNo: string;
  poDate: string;
  customerId: number;
  customerContactId: number | null;
  billingSiteId: number | null;
  billingAddressManual: string | null;
  consigneeSiteId: number | null;
  consigneeAddressManual: string | null;
  remarks: string | null;
  isActive: boolean;
  customerName: string | null;
  contactPersonName: string | null;
  billingSiteAddress: string | null;
  consigneeSiteAddress: string | null;
  // Cycle-aware fields (Phase 1A onwards) — surfaced when the row was
  // appended via the cycle endpoint. Null on legacy single-PO rows.
  quotOrderCycleId?: number | null;
  isLOI?: boolean;
  loiSequence?: number | null;
}

export interface CycleStartRequest {
  parentCycleId?: number | null;
  notes?: string | null;
}

export interface CycleCloseRequest {
  reason?: string | null;
}

export interface InheritancePreview {
  parentCycleId: number;
  parentCycleNo: number;
  /** ``viability`` = preferred (approved viability inherited);
   *  ``working_sheet`` = fallback when no approved viability exists;
   *  ``none`` = parent has neither, child starts empty. */
  sourceType: 'viability' | 'working_sheet' | 'none';
  lineCount: number;
}

export interface FwsApprovalSnapshot {
  snapshotId: number;
  versionNo: number;
  approvedByUserId: number | null;
  approvedByName: string | null;
  approvedAt: string;
  quotOrderCycleId: number;
  quotId: number;
  label: string;
}

export interface FwsApprovalSnapshotList {
  items: FwsApprovalSnapshot[];
}

export interface FwsApproveResult {
  snapshotId: number;
  versionNo: number;
  created: boolean;
  label: string;
  approvedAt: string;
  approvedByUserId: number | null;
  approvedByName: string | null;
}

export interface ViabilityApprovalSnapshot {
  snapshotId: number;
  viabilityId: number;
  quotId: number;
  versionNo: number;
  approvedByUserId: number | null;
  approvedByName: string | null;
  approvedAt: string;
}

export interface ViabilityApprovalSnapshotList {
  items: ViabilityApprovalSnapshot[];
}

export interface AnnexureApprovalSnapshot {
  snapshotId: number;
  annexureId: number;
  quotId: number;
  versionNo: number;
  approvedByUserId: number | null;
  approvedByName: string | null;
  approvedAt: string;
}

export interface AnnexureApprovalSnapshotList {
  items: AnnexureApprovalSnapshot[];
}

export interface AppendPurchaseOrderRequest {
  isLOI: boolean;
  poNo: string;
  poDate: string;
  customerId: number;
  customerContactId?: number | null;
  billingSiteId?: number | null;
  billingAddressManual?: string | null;
  consigneeSiteId?: number | null;
  consigneeAddressManual?: string | null;
  remarks?: string | null;
}

/** Typed wrapper around the Phase 1C cycle endpoints. Keeps the route
 *  paths in one place so a future API rename (e.g. /quotations →
 *  /quots) doesn't require grepping every component. */
@Injectable({ providedIn: 'root' })
export class CycleService {
  constructor(private api: ApiService) {}

  list(quotId: number, includeAbandoned = false): Observable<CycleListResponse> {
    return this.api.get<CycleListResponse>(
      `/quotations/${quotId}/cycles`,
      { include_abandoned: includeAbandoned },
    );
  }

  start(quotId: number, body: CycleStartRequest): Observable<OrderCycle> {
    return this.api.post<OrderCycle>(`/quotations/${quotId}/cycles`, body);
  }

  bundle(quotId: number, cycleId: number): Observable<OrderCycleBundle> {
    return this.api.get<OrderCycleBundle>(
      `/quotations/${quotId}/cycles/${cycleId}/bundle`,
    );
  }

  close(
    quotId: number, cycleId: number, body: CycleCloseRequest,
  ): Observable<OrderCycle> {
    return this.api.post<OrderCycle>(
      `/quotations/${quotId}/cycles/${cycleId}/close`, body,
    );
  }

  abandon(
    quotId: number, cycleId: number, body: CycleCloseRequest,
  ): Observable<OrderCycle> {
    return this.api.post<OrderCycle>(
      `/quotations/${quotId}/cycles/${cycleId}/abandon`, body,
    );
  }

  appendPurchaseOrder(
    quotId: number, cycleId: number, body: AppendPurchaseOrderRequest,
  ): Observable<CyclePurchaseOrder> {
    return this.api.post<CyclePurchaseOrder>(
      `/quotations/${quotId}/cycles/${cycleId}/purchase-orders`, body,
    );
  }

  /** Preview what a new cycle would inherit if started against the
   *  given parent cycle. Used by the Start New Call-off confirm dialog. */
  inheritancePreview(
    quotId: number, parentCycleId: number,
  ): Observable<InheritancePreview> {
    return this.api.get<InheritancePreview>(
      `/quotations/${quotId}/cycles/${parentCycleId}/inheritance-preview`,
    );
  }

  /** Cycle-scoped Final Working Sheet rows (one WS per cycle, CR
   *  decision C2). Phase 1E replacement for the legacy
   *  ``/quotations/{id}/purchase-order/working-sheet`` single-PO path. */
  listWorkingSheetForCycle(quotId: number, cycleId: number): Observable<any[]> {
    return this.api.get<any[]>(
      `/quotations/${quotId}/cycles/${cycleId}/working-sheet`,
    );
  }

  /** Every cycle's bundle in one fetch. Phase 1F: backs the Cycle
   *  History tab. Includes Abandoned cycles unconditionally. */
  history(quotId: number): Observable<CycleHistory> {
    return this.api.get<CycleHistory>(
      `/quotations/${quotId}/cycles/history`,
    );
  }

  /** List FWS approval snapshots for a cycle, newest first. Backs the
   *  version-picker dropdown and the FWS "Last approved" badge. */
  listFwsApprovalSnapshots(
    quotId: number, cycleId: number,
  ): Observable<FwsApprovalSnapshotList> {
    return this.api.get<FwsApprovalSnapshotList>(
      `/quotations/${quotId}/cycles/${cycleId}/fws/approval-snapshots`,
    );
  }

  /** Approve the cycle's Final Working Sheet — snapshots the current
   *  line items as a new versioned row. D3 short-circuit: if content
   *  is unchanged since the last snapshot, ``created`` is false and no
   *  new version is created (audit event only). */
  approveFws(quotId: number, cycleId: number): Observable<FwsApproveResult> {
    return this.api.post<FwsApproveResult>(
      `/quotations/${quotId}/cycles/${cycleId}/fws/approve`, {},
    );
  }

  /** Restore an FWS approval snapshot — the snapshot's content
   *  replaces the cycle's current active line items so the user can
   *  edit forward from that point. Powers the FWS version-switcher
   *  dropdown's "Load this version" action. */
  loadFwsSnapshot(
    quotId: number, cycleId: number, snapshotId: number,
  ): Observable<{ restoredFromSnapshotId: number; restoredFromLabel: string; rowsInserted: number }> {
    return this.api.post(
      `/quotations/${quotId}/cycles/${cycleId}/fws/approval-snapshots/${snapshotId}/restore`,
      {},
    );
  }

  // ---- Viability snapshots ----
  listViabilitySnapshots(
    viabilityId: number,
  ): Observable<ViabilityApprovalSnapshotList> {
    return this.api.get<ViabilityApprovalSnapshotList>(
      `/viability/${viabilityId}/approval-snapshots`,
    );
  }

  /** Restore a viability snapshot — the snapshot's header + lines
   *  replace the live sheet's state. User edits forward; next Approve
   *  creates a new version (or D3 short-circuits if unchanged). */
  loadViabilitySnapshot(
    viabilityId: number, snapshotId: number,
  ): Observable<{ restoredFromSnapshotId: number; restoredFromLabel: string; linesInserted: number }> {
    return this.api.post(
      `/viability/${viabilityId}/approval-snapshots/${snapshotId}/load`,
      {},
    );
  }

  // ---- Annexure snapshots ----
  listAnnexureSnapshots(
    annexureId: number,
  ): Observable<AnnexureApprovalSnapshotList> {
    return this.api.get<AnnexureApprovalSnapshotList>(
      `/annexure/${annexureId}/approval-snapshots`,
    );
  }

  /** Restore an annexure snapshot — its frozen content replaces the
   *  head row's editable fields. */
  loadAnnexureSnapshot(
    annexureId: number, snapshotId: number,
  ): Observable<{ restoredFromSnapshotId: number; restoredFromLabel: string }> {
    return this.api.post(
      `/annexure/${annexureId}/approval-snapshots/${snapshotId}/load`,
      {},
    );
  }
}
