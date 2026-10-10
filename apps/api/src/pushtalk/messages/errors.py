from http import HTTPStatus

from pushtalk.core.errors import AppError


class PayloadTooLarge(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"
    message = "The recording is too large."


class UnsupportedMedia(AppError):
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"
    message = "Unsupported audio format."


class InvalidAudio(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_audio"
    message = "The recording could not be read."


class MessageNotFound(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "message_not_found"
    message = "This message does not exist."


class ProcessingUnavailable(AppError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "Voice messages cannot be processed right now. Please try again."
