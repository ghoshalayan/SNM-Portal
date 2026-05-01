"""Fix menu URLs from singular to plural to match frontend routes

Revision ID: f3a1b2c4d5e6
Revises: e88c297e3e9d
Create Date: 2026-03-28 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f3a1b2c4d5e6'
down_revision: Union[str, None] = 'e88c297e3e9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old URL → New URL mapping
URL_FIXES = {
    "/masters/item-grade": "/masters/item-grades",
    "/masters/item-name": "/masters/item-names",
    "/masters/item-length": "/masters/item-lengths",
    "/masters/item-size": "/masters/item-sizes",
    "/masters/delivery-term": "/masters/delivery-terms",
    "/masters/delivery-mode": "/masters/delivery-modes",
    "/masters/contact-type": "/masters/contact-types",
    "/masters/customer-classification": "/masters/customer-classifications",
    "/masters/cost-point": "/masters/cost-points",
    "/masters/terms-condition": "/masters/terms-conditions",
    "/masters/raw-material-cost": "/masters/raw-material-costs",
}


def upgrade() -> None:
    conn = op.get_bind()
    for old_url, new_url in URL_FIXES.items():
        conn.execute(
            sa.text("UPDATE MenuMaster SET menuUrl = :new WHERE menuUrl = :old"),
            {"old": old_url, "new": new_url},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for old_url, new_url in URL_FIXES.items():
        conn.execute(
            sa.text("UPDATE MenuMaster SET menuUrl = :old WHERE menuUrl = :new"),
            {"old": old_url, "new": new_url},
        )
