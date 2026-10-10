"""transcripts

Revision ID: 0006
Revises: 0005

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing messages keep no transcript (status NULL); new ones start as pending.
    # add_column does not create enum types (create_table does), so the type comes first.
    transcript_status = postgresql.ENUM("pending", "done", "failed", name="transcript_status")
    transcript_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "messages",
        sa.Column(
            "transcript_status",
            postgresql.ENUM(name="transcript_status", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("messages", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("transcript_lang", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("messages", "transcript_lang")
    op.drop_column("messages", "transcript")
    op.drop_column("messages", "transcript_status")
    # Alembic does not drop enum types with their column.
    sa.Enum(name="transcript_status").drop(op.get_bind(), checkfirst=True)
