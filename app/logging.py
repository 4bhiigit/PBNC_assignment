import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variables for tracing across asynchronous execution
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
document_id_ctx: ContextVar[str | None] = ContextVar("document_id", default=None)
task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON without decorative banners or emojis."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach request and task tracking identifiers if set in the execution context
        req_id = request_id_ctx.get()
        if req_id:
            log_payload["request_id"] = req_id

        doc_id = document_id_ctx.get()
        if doc_id:
            log_payload["document_id"] = doc_id

        t_id = task_id_ctx.get()
        if t_id:
            log_payload["task_id"] = t_id

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


def setup_logging(log_level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Silence verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
