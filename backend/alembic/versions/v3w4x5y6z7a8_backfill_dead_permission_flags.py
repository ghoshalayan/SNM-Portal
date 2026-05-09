"""Backfill the two dead permission flags now that the API enforces them.

Two flags shipped in the schema but were never consulted by any endpoint:

* ``CanEditNumber`` — exposed for both Quotations and Enquiries menus.
  Intended to gate "user supplies a custom quotNo / enqNo and bypasses
  the auto-generated FY-scoped serial". The create endpoints accepted
  the override regardless of flag state.

* ``CanApproveViability`` — exposed for the Quotations menu. Intended to
  gate viability-sheet approval as a per-stage permission, distinct
  from the quotation-level ``CanApprove``. The viability approve
  endpoint kept using ``CanApprove`` instead.

Together with this migration, the corresponding API handlers are being
switched to consult the granular flags. Without a backfill, any role
that today uses ``CanAdd`` to create records (and incidentally overrides
numbers) or ``CanApprove`` on Quotations to approve viability would
suddenly see 403s — that's a regression, not a security improvement.

Backfill rules (conservative, idempotent, OR-not-overwrite):

* For active RoleMenuMap rows on the **Quotations** and **Enquiries**
  menus where ``CanAdd = 1`` and ``CanEditNumber = 0``, set
  ``CanEditNumber = 1``. Roles that explicitly had it already keep it.

* For active RoleMenuMap rows on the **Quotations** menu where
  ``CanApprove = 1`` and ``CanApproveViability = 0``, set
  ``CanApproveViability = 1``.

Status quo is preserved on first deploy. Admins can subsequently revoke
either flag from any role via the role-menu page; that is the intended
hand-off into proper segregation of duties.

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-05-05
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "v3w4x5y6z7a8"
down_revision: Union[str, None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CanEditNumber ← CanAdd, scoped to Quotations + Enquiries menus.
    op.execute(
        """
        UPDATE rmm
        SET CanEditNumber = 1
        FROM RoleMenuMap rmm
        INNER JOIN MenuMaster mm ON mm.menuId = rmm.menuId
        WHERE mm.menuName IN ('Quotations', 'Enquiries')
          AND rmm.isActive = 1
          AND rmm.CanAdd = 1
          AND rmm.CanEditNumber = 0
        """
    )

    # CanApproveViability ← CanApprove, scoped to the Quotations menu only.
    op.execute(
        """
        UPDATE rmm
        SET CanApproveViability = 1
        FROM RoleMenuMap rmm
        INNER JOIN MenuMaster mm ON mm.menuId = rmm.menuId
        WHERE mm.menuName = 'Quotations'
          AND rmm.isActive = 1
          AND rmm.CanApprove = 1
          AND rmm.CanApproveViability = 0
        """
    )


def downgrade() -> None:
    # Intentional no-op. Reverting the backfill is unsafe — at downgrade
    # time we cannot tell which grants were original vs. backfilled, so
    # blanket-clearing the columns would silently revoke flags an admin
    # may have explicitly granted after deploy. The safer rollback path
    # is to revert the API code change (so the now-extra-true flags are
    # ignored again) without mutating data.
    pass
