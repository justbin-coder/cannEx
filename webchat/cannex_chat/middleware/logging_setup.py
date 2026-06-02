"""Logging setup with API key redaction and daily file rotation."""
import logging
import re
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

KEY_PATTERN = re.compile(r"sk-(?:ant-)?[\w-]{8,}", re.IGNORECASE)


class RedactingFilter(logging.Filter):
    """Replace any Anthropic/OpenAI-style API key with [REDACTED]."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple):
            try:
                # 只对字符串参数做脱敏；int 等非字符串保持原类型，
                # 否则 record.getMessage() 的 %d 等格式化会抛 TypeError。
                record.args = tuple(self._redact_arg(a) for a in record.args)
            except Exception:
                pass
        record.msg = self._redact(str(record.msg))
        return True

    @classmethod
    def _redact_arg(cls, a):
        return cls._redact(a) if isinstance(a, str) else a

    @staticmethod
    def _redact(s: str) -> str:
        return KEY_PATTERN.sub("[REDACTED]", s)


def setup_logging(logs_dir: Path | str = "logs", level: int = logging.INFO):
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        logs_dir / "webchat.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(fmt)
    handler.addFilter(RedactingFilter())

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler, console]
