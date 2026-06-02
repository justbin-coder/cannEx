import logging

from webchat.cannex_chat.middleware.logging_setup import RedactingFilter


def test_redact_anthropic_key():
    f = RedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1,
                               "request with sk-ant-api03-xxxxx-secret in body", None, None)
    assert f.filter(record)
    assert "sk-ant-" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_does_not_break_normal_message():
    f = RedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "hello world", None, None)
    f.filter(record)
    assert record.getMessage() == "hello world"


def test_redact_in_args():
    f = RedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "key=%s", ("sk-ant-very-secret",), None)
    f.filter(record)
    assert "sk-ant" not in record.getMessage()


def test_preserves_non_string_args():
    """非字符串 args（如 %d 的 int）必须保持原类型，否则 getMessage() 会抛 TypeError。"""
    f = RedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "iter=%d msgs=%d", (0, 1), None)
    f.filter(record)
    assert record.getMessage() == "iter=0 msgs=1"
