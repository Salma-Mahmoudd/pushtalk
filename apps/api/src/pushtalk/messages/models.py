import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pushtalk.db.base import Base


class MessageStatus(enum.StrEnum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Order within a channel; assigned when processing finishes (see DECISIONS.md, 1.5).
        UniqueConstraint("channel_id", "seq", name="uq_messages_channel_id_seq"),
        # A retried upload (same client id) never creates a second message.
        UniqueConstraint("sender_id", "client_msg_id", name="uq_messages_sender_id_client_msg_id"),
        Index("ix_messages_channel_id_created_at", "channel_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    client_msg_id: Mapped[uuid.UUID]
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status"), default=MessageStatus.processing
    )
    seq: Mapped[int | None]
    duration_ms: Mapped[int | None]
    # 64 peak levels (0 to 100) for drawing the waveform.
    waveform: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    original_key: Mapped[str] = mapped_column(String(200))
    audio_key: Mapped[str | None] = mapped_column(String(200))
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageReceipt(Base):
    """What one recipient's app reported about one message (story 7: delivered, then played)."""

    __tablename__ = "message_receipts"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
