from http import HTTPStatus

from pushtalk.core.errors import AppError


class ChannelNotFound(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "channel_not_found"
    message = "This channel does not exist."


class ChannelExists(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "channel_exists"
    message = "A channel with this name already exists."


class NotAMember(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "not_a_member"
    message = "Join this channel first."


class CannotJoinDirect(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "cannot_join_direct"
    message = "Direct conversations cannot be joined."
