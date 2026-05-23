"""Renumber existing viability + annexure snapshot versionNo per cycle.

Background: between the cycle-scoping rework on 2026-05-21 and the
correction on 2026-05-22, viability snapshots had a brief quotation-wide
monotonic counter. That meant Cycle 2's first Approve recorded
``versionNo = 4`` (continuing Cycle 1's count of 3) instead of restarting
at 1. Annexure snapshots were always per-annexure-row so this primarily
affects viability — but we renumber annexure too for safety in case
mixed data exists.

This migration walks each cycle's snapshot chain in insertion order
(by snapshotId asc) and rewrites ``versionNo`` to 1, 2, 3, …. Idempotent:
re-running on already-renumbered data is a no-op.

Revision ID: g4h5i6j7k8l9
Revises: f3g4h5i6j7k8
Create Date: 2026-05-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, None] = "f3g4h5i6j7k8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ----- Viability snapshots -----
    # Group by the snapshot's owning sheet's quotOrderCycleId. Sheets
    # without a cycleId (truly legacy pre-Phase-1A) fall back to
    # per-sheet renumbering — keeps the chain coherent for that
    # quotation's single legacy sheet.
    viab_rows = bind.execute(sa.text(
        """
        SELECT s.snapshotId, vs.quotOrderCycleId, s.viabilityId
        FROM QuotViabilityApprovalSnapshot s
        JOIN QuotViabilitySheet vs ON s.viabilityId = vs.viabilityId
        ORDER BY
          COALESCE(vs.quotOrderCycleId, -s.viabilityId) ASC,
          s.snapshotId ASC
        """
    )).fetchall()

    # Walk each group (cycle id, or fallback per-sheet) and renumber.
    current_group: object = None
    counter = 0
    for row in viab_rows:
        snapshot_id, cycle_id, viab_id = row
        group_key = cycle_id if cycle_id is not None else f"sheet-{viab_id}"
        if group_key != current_group:
            current_group = group_key
            counter = 1
        else:
            counter += 1
        bind.execute(
            sa.text(
                "UPDATE QuotViabilityApprovalSnapshot "
                "SET versionNo = :v WHERE snapshotId = :id"
            ),
            {"v": counter, "id": snapshot_id},
        )

    # ----- Annexure snapshots -----
    # Annexure snapshots are already per-annexureId; one annexure per
    # cycle (CR decision C2), so per-annexure renumbering equals
    # per-cycle renumbering. Defensive sweep in case any rows drifted.
    ann_rows = bind.execute(sa.text(
        """
        SELECT snapshotId, annexureId
        FROM QuotAnnexureApprovalSnapshot
        ORDER BY annexureId ASC, snapshotId ASC
        """
    )).fetchall()

    current_ann: object = None
    counter = 0
    for row in ann_rows:
        snapshot_id, annexure_id = row
        if annexure_id != current_ann:
            current_ann = annexure_id
            counter = 1
        else:
            counter += 1
        bind.execute(
            sa.text(
                "UPDATE QuotAnnexureApprovalSnapshot "
                "SET versionNo = :v WHERE snapshotId = :id"
            ),
            {"v": counter, "id": snapshot_id},
        )


def downgrade() -> None:
    # Renumbering is destructive of the original (already wrong)
    # ordering — no clean way to reverse. Downgrade is a no-op.
    pass
