import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from pushtalk.db.base import Base


class ChannelKind(enum.StrEnum):
    group = "group"
    direct = "direct"


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        # A group channel has a name; a direct channel is identified by its pair of users.
        CheckConstraint(
            "(kind = 'group' AND name IS NOT NULL AND dm_key IS NULL)"
            " OR (kind = 'direct' AND name IS NULL AND dm_key IS NOT NULL)",
            name="kind_fields",
        ),
        # Group names are unique regardless of letter case.
        Index(
            "uq_channels_group_name_lower",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("kind = 'group'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[ChannelKind] = mapped_column(
        Enum(ChannelKind, name="channel_kind"), default=ChannelKind.group
    )
    name: Mapped[str | None] = mapped_column(String(50))
    # "<smaller user id>:<larger user id>" for direct channels (Phase 5).
    dm_key: Mapped[str | None] = mapped_column(String(73), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Sequence number of the newest ready message; incremented when a message becomes ready.
    last_seq: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelMember(Base):
    __tablename__ = "channel_members"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
