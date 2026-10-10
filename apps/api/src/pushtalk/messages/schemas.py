import uuid
from datetime import datetime

from pydantic import BaseModel

from pushtalk.messages.models import MessageStatus


class SenderOut(BaseModel):
    id: uuid.UUID
    username: str


class ReceiptSummary(BaseModel):
    delivered: int
    played: int
    # Channel members other than the sender.
    total: int


class RecipientReceipt(BaseModel):
    user_id: uuid.UUID
    username: str
    delivered_at: datetime | None
    played_at: datetime | None


class MessageOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    client_msg_id: uuid.UUID
    sender: SenderOut
    status: MessageStatus
    # Position in the channel; set when the message becomes ready.
    seq: int | None
    duration_ms: int | None
    waveform: list[int] | None
    failure_reason: str | None
    created_at: datetime
    # Only on the caller's own messages.
    receipts: ReceiptSummary | None = None


class MessagePage(BaseModel):
    # Ready messages in seq order.
    messages: list[MessageOut]
    # The caller's own messages that are still processing or failed.
    pending: list[MessageOut]
    # More ready messages exist in the requested direction.
    has_more: bool
