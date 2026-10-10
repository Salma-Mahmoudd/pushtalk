import uuid

from pydantic import BaseModel

from pushtalk.channels.schemas import UserOut


class DirectOpen(BaseModel):
    user_id: uuid.UUID


class DirectOut(BaseModel):
    # The conversation's channel: messages, history and the WebSocket use the channel API.
    id: uuid.UUID
    peer: UserOut
    # The peer has PushTalk open somewhere (any tab or device).
    online: bool
