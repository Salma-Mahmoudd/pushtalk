import logging
import sys

import structlog
from structlog.typing import Processor


def configure_logging(level: str, log_format: str) -> None:
    """Send structlog and standard-library logs (uvicorn included) to stdout as one format."""
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: list[Processor] = (
        [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
        if log_format == "json"
        else [structlog.dev.ConsoleRenderer()]
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Replaced by the request.completed event from RequestContextMiddleware.
    logging.getLogger("uvicorn.access").disabled = True
