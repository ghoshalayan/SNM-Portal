"""Add post-Convert lifecycle Approve + Regenerate permission flags.

Adds four new boolean flags to RoleMenuMap so each stage's Approve
and Re-generate actions can be granted independently:

- ``CanApproveFWS``         : approve the cycle's Final Working Sheet.
- ``CanRegenerateFWS``      : trigger FWS regenerate (from past FWS /
                              quotation lines / parent cycle).
- ``CanRegenerateViability``: trigger viability regenerate (from past
                              FWS or past viability snapshot).
- ``CanRegenerateAnnexure`` : trigger annexure regenerate / re-source.

Existing roles continue to work through the legacy fallbacks
(``CanApprove`` for FWS approve, ``CanEdit`` for the three regenerates)
until they are explicitly granted the new flags via the role-menu
mapping UI. New roles created after this migration default each flag
to ``False`` and must be granted intentionally.

**Doubles as a merge migration.** Before this point, the project had
two parallel heads:
  * ``g4h5i6j7k8l9`` — soft-flow snapshot renumbering chain.
  * ``h5i6j7k8l9m0`` — KPI dashboard item-grid chain.
``alembic upgrade head`` errored out asking for a specific target.
This migration's ``down_revision`` is a tuple of both heads, which
collapses them into a single head from here on.

Idempotent: re-running on a database where the columns already exist
is a no-op (handled by ``IF NOT EXISTS``-style probe).

Revision ID: i6j7k8l9m0n1
Revises: g4h5i6j7k8l9, h5i6j7k8l9m0
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i6j7k8l9m0n1"
# Tuple of two parents — collapses the soft-flow + KPI chains so
# ``alembic upgrade head`` resolves to a single revision again.
down_revision: Union[str, Sequence[str], None] = (
    "g4h5i6j7k8l9",
    "h5i6j7k8l9m0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    "CanApproveFWS",
    "CanRegenerateFWS",
    "CanRegenerateViability",
    "CanRegenerateAnnexure",
]


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    for col in NEW_COLUMNS:
        if _column_exists(bind, "RoleMenuMap", col):
            continue
        # SQL Server requires a DEFAULT constraint when adding a NOT
        # NULL column to a table that already has rows; the constraint
        # gives every existing row the value ``0``.
        op.add_column(
            "RoleMenuMap",
            sa.Column(
                col,
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    # Drop the server-side default once existing rows are backfilled so
    # future inserts must specify the value explicitly via the Python
    # model defaults — keeps the schema clean and matches the other
    # boolean flags on this table.
    for col in NEW_COLUMNS:
        if not _column_exists(bind, "RoleMenuMap", col):
            continue
        try:
            op.alter_column(
                "RoleMenuMap",
                col,
                server_default=None,
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )
        except Exception:
            # Some SQL Server drivers refuse the alter when the default
            # is a system-generated constraint with a varying name. The
            # backfill is already done at this point, so leaving the
            # default in place is harmless.
            pass


def downgrade() -> None:
    for col in NEW_COLUMNS:
        try:
            op.drop_column("RoleMenuMap", col)
        except Exception:
            # Column may have been dropped manually; ignore.
            pass
