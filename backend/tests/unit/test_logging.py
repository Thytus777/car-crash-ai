import json
import logging

from app.core.logging import JsonFormatter, request_id_var


def _record(msg: str, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        "app.test", logging.WARNING, __file__, 1, msg, args, None
    )
    record.__dict__.update(extra)
    return record


def test_json_lines_include_level_logger_message_and_extras() -> None:
    line = json.loads(
        JsonFormatter().format(_record("hello %s", "world", zone="front"))
    )

    assert line["level"] == "WARNING" and line["logger"] == "app.test"
    assert line["message"] == "hello world" and line["zone"] == "front"
    assert "request_id" not in line  # outside a request
    assert line["ts"].endswith("Z")


def test_request_id_comes_from_the_context() -> None:
    token = request_id_var.set("abc123")
    try:
        line = json.loads(JsonFormatter().format(_record("x")))
    finally:
        request_id_var.reset(token)

    assert line["request_id"] == "abc123"


def test_exceptions_are_serialised_on_one_line() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record("failed", exc_info=sys.exc_info())

    text = JsonFormatter().format(record)

    assert "\n" not in text and "ValueError: boom" in json.loads(text)["exc_info"]


def test_lines_carry_a_cloud_logging_severity() -> None:
    # Cloud Logging grades JSON lines by `severity`; without it every line,
    # errors included, is DEFAULT and `severity>=ERROR` finds nothing.
    for level in (
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ):
        record = _record("x")
        record.levelno, record.levelname = level, logging.getLevelName(level)

        line = json.loads(JsonFormatter().format(record))

        assert line["severity"] == logging.getLevelName(level)
