import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"


class SignupIn(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN, examples=["alice"])
    # The upper bound keeps hashing cost bounded.
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    # No format rules here: a login form should not reveal them.
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str


class SessionOut(BaseModel):
    user: UserOut
    # The client schedules its refresh from this; the token itself stays in an httpOnly cookie.
    access_expires_at: datetime
