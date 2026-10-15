"""Structured JSON logging. Each line carries org_id, actor_id, request_id and
investigation_id from the ContextVars in infra.context. Content fields are
never logged by these helpers; callers log identifiers and counts."""

import json
import logging

from .context import get_actor_id, get_investigation_id, get_org_id, get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.org_id = get_org_id()
        record.request_id = get_request_id()
        record.actor_id = get_actor_id()
        record.investigation_id = get_investigation_id()
        return True


class JsonFormatter(logging.Formatter):
    _BASE_KEYS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "org_id": getattr(record, "org_id", None),
            "request_id": getattr(record, "request_id", None),
            "actor_id": getattr(record, "actor_id", None),
            "investigation_id": getattr(record, "investigation_id", None),
        }
        for key, value in record.__dict__.items():
            if key in self._BASE_KEYS or key in payload or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
