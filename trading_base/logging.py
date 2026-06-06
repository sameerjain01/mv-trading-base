from __future__ import annotations

import json
import logging
import smtplib
import sys
from email.message import EmailMessage
from os import environ
from pathlib import Path

_STANDARD_ATTRS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})


class _PipeFormatter(logging.Formatter):
    """TIMESTAMP | LEVEL | MODULE | MESSAGE | {extra JSON}"""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = self.formatTime(record, self.datefmt)
        extra = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        suffix = f" | {json.dumps(extra, default=str)}" if extra else ""
        line = f"{ts} | {record.levelname} | {record.module} | {record.message}{suffix}"
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = line + "\n" + record.exc_text
        if record.stack_info:
            line = line + "\n" + self.formatStack(record.stack_info)
        return line


def setup_logging(log_file: Path) -> None:
    """Wire root logger to log_file and stdout. Safe to call repeatedly."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = _PipeFormatter()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    for h in root.handlers[:]:
        h.close()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def send_alert(message: str, level: str = "CRITICAL", extra: dict | None = None) -> None:
    logger = logging.getLogger(__name__)
    logger.log(logging.CRITICAL, message, extra=extra or {})
    _write_alerts_log(level, message)
    _try_smtp(level, message)


def _write_alerts_log(level: str, message: str) -> None:
    alerts_log_path = environ.get("ALERTS_LOG")
    if not alerts_log_path:
        return
    try:
        import datetime as _dt
        alerts_log = Path(alerts_log_path)
        alerts_log.parent.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with open(alerts_log, "a", encoding="utf-8") as fh:
            fh.write(f"{ts} [{level}] {message}\n")
    except OSError:
        logging.getLogger(__name__).warning("Failed to write ALERTS_LOG", exc_info=True)


def _try_smtp(level: str, message: str) -> None:
    host = environ.get("ALERT_SMTP_HOST")
    from_addr = environ.get("ALERT_EMAIL_FROM")
    to_addr = environ.get("ALERT_EMAIL_TO")
    if not (host and from_addr and to_addr):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[{level}] trading-base alert"
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(message)
        with smtplib.SMTP(host) as s:
            s.send_message(msg)
    except Exception:
        logging.getLogger(__name__).warning("SMTP alert dispatch failed", exc_info=True)
