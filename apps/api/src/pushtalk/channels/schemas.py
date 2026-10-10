import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, StringConstraints

from pushtalk.channels.models import ChannelKind


def _printable(value: str) -> str:
    if any(not character.isprintable() for character in value):
        raise ValueError("must not contain control characters")
    return value


ChannelName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    AfterValidator(_printable),
]


class ChannelCreate(BaseModel):
    name: ChannelName


class UserOut(BaseModel):
    id: uuid.UUID
    username: str


class ChannelOut(BaseModel):
    id: uuid.UUID
    kind: ChannelKind
    # Group channels only; a direct channel is titled by its other participant (peer).
    name: str | None
    is_member: bool
    member_count: int
    peer: UserOut | None = None


class MemberOut(BaseModel):
    id: uuid.UUID
    username: str
    online: bool
