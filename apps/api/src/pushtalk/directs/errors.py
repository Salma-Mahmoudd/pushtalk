from http import HTTPStatus

from pushtalk.core.errors import AppError


class UserNotFound(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "user_not_found"
    message = "This user does not exist."


class CannotMessageYourself(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "cannot_message_yourself"
    message = "Pick someone else to talk to."
