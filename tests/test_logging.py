from __future__ import annotations

import logging
import os

import pytest


def test_setup_logging_creates_file(tmp_path):
    from trading_base.logging import setup_logging
    log_file = tmp_path / "trading.log"
    setup_logging(log_file)
    logger = logging.getLogger("test_setup_logging")
    logger.info("pipe test")
    assert log_file.exists()


def test_setup_logging_pipe_format(tmp_path):
    from trading_base.logging import setup_logging
    log_file = tmp_path / "trading.log"
    setup_logging(log_file)
    logger = logging.getLogger("test_pipe_format")
    logger.warning("pipe format check")
    content = log_file.read_text()
    assert "|" in content


def test_setup_logging_always_debug(tmp_path):
    from trading_base.logging import setup_logging
    log_file = tmp_path / "trading.log"
    setup_logging(log_file)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_send_alert_logs_critical(tmp_path, caplog):
    from trading_base.logging import send_alert
    with caplog.at_level(logging.CRITICAL, logger="trading_base.logging"):
        send_alert("critical test message", "CRITICAL")
    assert any("critical test message" in r.message for r in caplog.records)


def test_send_alert_skips_smtp_when_env_absent(tmp_path):
    from trading_base.logging import send_alert
    os.environ.pop("ALERT_SMTP_HOST", None)
    os.environ.pop("ALERT_EMAIL_FROM", None)
    os.environ.pop("ALERT_EMAIL_TO", None)
    send_alert("no smtp test", "CRITICAL")  # should not raise
