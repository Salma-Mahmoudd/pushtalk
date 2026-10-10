"""messages

Revision ID: 0004
Revises: 0003

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("client_msg_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("processing", "ready", "failed", name="message_status"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("waveform", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("original_key", sa.String(length=200), nullable=False),
        sa.Column("audio_key", sa.String(length=200), nullable=True),
        sa.Column("failure_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_messages_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("channel_id", "seq", name="uq_messages_channel_id_seq"),
        sa.UniqueConstraint(
            "sender_id", "client_msg_id", name="uq_messages_sender_id_client_msg_id"
        ),
    )
    op.create_index(
        "ix_messages_channel_id_created_at", "messages", ["channel_id", "created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_messages_channel_id_created_at", table_name="messages")
    op.drop_table("messages")
    # Alembic does not drop enum types with their table.
    sa.Enum(name="message_status").drop(op.get_bind(), checkfirst=True)
