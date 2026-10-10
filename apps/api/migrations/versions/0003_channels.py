"""channels

Revision ID: 0003
Revises: 0002

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("group", "direct", name="channel_kind"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=True),
        sa.Column("dm_key", sa.String(length=73), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'group' AND name IS NOT NULL AND dm_key IS NULL)"
            " OR (kind = 'direct' AND name IS NULL AND dm_key IS NOT NULL)",
            name=op.f("ck_channels_kind_fields"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_channels_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("dm_key", name=op.f("uq_channels_dm_key")),
    )
    op.create_index(
        "uq_channels_group_name_lower",
        "channels",
        [sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("kind = 'group'"),
    )
    op.create_table(
        "channel_members",
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_channel_members_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("channel_id", "user_id", name=op.f("pk_channel_members")),
    )
    op.create_index(
        op.f("ix_channel_members_user_id"), "channel_members", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_channel_members_user_id"), table_name="channel_members")
    op.drop_table("channel_members")
    op.drop_index(
        "uq_channels_group_name_lower",
        table_name="channels",
        postgresql_where=sa.text("kind = 'group'"),
    )
    op.drop_table("channels")
    # Alembic does not drop enum types with their table.
    sa.Enum(name="channel_kind").drop(op.get_bind(), checkfirst=True)
