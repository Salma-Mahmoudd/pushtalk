from http import HTTPStatus

from pushtalk.core.errors import AppError


class UsernameTaken(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "username_taken"
    message = "This username is already taken."


class InvalidCredentials(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "invalid_credentials"
    message = "Wrong username or password."


class RefreshInvalid(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "refresh_invalid"
    message = "The session has ended. Please log in again."


class Unauthorized(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "unauthorized"
    message = "Please log in."
