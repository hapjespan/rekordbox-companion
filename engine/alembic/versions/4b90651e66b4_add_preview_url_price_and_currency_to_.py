"""add preview url price and currency to missing_track

Revision ID: 4b90651e66b4
Revises: 8cd0cf8178d6
Create Date: 2026-08-19 15:15:09.369336

FR-041 (ADR 0021): the store lookup that already resolves `itunes_url_auto`
also returns that track's 30 second preview and its storefront price, so
both are persisted next to the link they describe. Nullable and backfilled
by the next `POST /api/missing/refresh-links`, never by this migration: the
values belong to an iTunes response, and a migration makes no network calls.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b90651e66b4"
down_revision: str | Sequence[str] | None = "8cd0cf8178d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("missing_track", sa.Column("itunes_preview_url", sa.String(), nullable=True))
    op.add_column("missing_track", sa.Column("itunes_price", sa.Float(), nullable=True))
    op.add_column("missing_track", sa.Column("itunes_currency", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Reversible like its siblings. Wrapped in batch_alter_table because
    # SQLite is this app's only database (data/app.sqlite) and a plain
    # DROP COLUMN there depends on the bundled SQLite being >= 3.35; the
    # batch operator recreates the table instead where it is not.
    with op.batch_alter_table("missing_track") as batch_op:
        batch_op.drop_column("itunes_currency")
        batch_op.drop_column("itunes_price")
        batch_op.drop_column("itunes_preview_url")
