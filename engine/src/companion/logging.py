"""Structured (JSON) logging with token/key redaction as a formatter property.

The NIS2 logging plan (constraints.md) draws a hard line: guard refusals,
backup creation/rotation, Rekordbox writes with their readback verdict, and
run summaries are logged; OAuth tokens, the SQLCipher key, request headers,
audio content and full library dumps are *deliberately never* logged. This
module makes the "never logged" half a structural guarantee rather than a rule
every future call site in `rb/guard.py`, `rb/backup.py` and `rb/writer.py`
(built later, US3) has to remember: redaction lives in the formatter, so any
record emitted through a handler built here is scrubbed before it is
serialized, whether the caller knew to redact or not.

Redaction works on the *structured* payload, not the rendered line: it walks
the record's `extra` fields (including nested dicts and lists) and blanks any
value whose key name reads as a credential (`access_token`, `refresh_token`,
`sqlcipher_key`, `authorization`, ...). Catching the key name, not a flat
string match on the final line, is what lets it find a secret nested inside a
carelessly logged response object.

Known limitation, stated plainly (rb/reader.py precedent for documenting an
assumption rather than shipping false confidence): a secret with *no* sensitive
key name and *no* recognizable format — e.g. a bare token interpolated straight
into the message text via `%s` — cannot be caught structurally, because nothing
distinguishes it from ordinary content. The message string gets a best-effort
`Bearer <token>` scrub for the common header case, but the real guarantee is on
field names, so callers pass secrets (when they must reference one at all) as
named fields, never spliced into the message. Over-redaction is the safe
direction and is accepted: a non-secret field like `token_expires_at` is
blanked too, because its name contains `token`.
"""

import json
import logging
import re
from collections.abc import Mapping, Sequence

REDACTED = "[REDACTED]"

# Substrings (matched case-insensitively against field names) that mark a value
# as a credential. Deliberately broad: a false positive blanks a harmless field,
# a false negative leaks a secret, so the trade is one-sided.
SENSITIVE_KEY_SUBSTRINGS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "authorization",
        "credential",
        "api_key",
        "apikey",
        "sqlcipher",
        "private_key",
        # The SQLCipher key specifically (rb/guard.py, rb/writer.py, US3) has
        # no fixed name across callers -- "key" alone catches every plausible
        # spelling (db_key, encryption_key, master_key, cipher_key, key) that
        # "sqlcipher"/"private_key" alone missed (adversarial gate-review
        # finding, T018). Broad on purpose: over-redaction is the safe
        # direction (module docstring).
        "key",
        # "auth" alone: the marker match is substring-in-key, so
        # "authorization" doesn't cover a field literally named "auth"
        # (adversarial gate-review finding, T018).
        "auth",
        # "password"/"passwd" don't cover a field literally named "pass";
        # "code_verifier"/"pkce" are the Spotify PKCE value (research.md
        # R2, FR-001), which matched nothing in the original set (second-
        # round adversarial gate-review finding, T018).
        "pass",
        "code_verifier",
        "pkce",
    }
)

# Third-party loggers known to log sensitive values at DEBUG if left enabled.
# pyrekordbox.db6.database.Rekordbox6Database.__init__ does
# `logger.debug("Key: %s", key)` -- the raw SQLCipher key, interpolated into
# free text with no pattern this formatter's Bearer-only text scrub could
# catch, on a logger entirely outside the `companion` tree this module
# otherwise governs. Raising the logger's level is the only structural
# defense available: it stops the record from being created at all,
# regardless of what handlers exist anywhere in the process (adversarial
# gate-review finding, T018).
_THIRD_PARTY_LOGGERS_TO_SILENCE = ("pyrekordbox",)

# `Authorization: Bearer <token>` rendered into free text; the one value-level
# shape common enough to be worth a best-effort scrub (see module limitation).
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[\w.\-+/=~]+")

# LogRecord's own attributes; everything else in `record.__dict__` came from a
# caller's `extra=` and is treated as a structured field to emit and redact.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
    }
)

# Guards against a pathologically deep or cyclic structure exhausting the stack.
_MAX_REDACT_DEPTH = 12

_COMPANION_LOGGER_NAME = "companion"


def _is_sensitive_key(key: object) -> bool:
    key_lower = str(key).lower()
    return any(marker in key_lower for marker in SENSITIVE_KEY_SUBSTRINGS)


def _redact_text(value: str) -> str:
    return _BEARER_RE.sub(f"Bearer {REDACTED}", value)


def _redact(value: object, depth: int = 0) -> object:
    """Return a scrubbed copy of `value`, recursing into mappings and sequences.

    A value under a sensitive key is replaced wholesale; otherwise the walk
    continues so a secret nested below a harmless key is still reached.
    """
    if depth >= _MAX_REDACT_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            key: (REDACTED if _is_sensitive_key(key) else _redact(item, depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, str):
        return _redact_text(value)
    # str is a Sequence too, so it must be handled above this branch.
    if isinstance(value, Sequence):
        return [_redact(item, depth + 1) for item in value]
    return value


class RedactingJsonFormatter(logging.Formatter):
    """Emit one JSON object per record, with credentials structurally removed.

    Redaction happens here, at format time, so it cannot be bypassed by a call
    site that forgot to scrub: every record routed through a handler carrying
    this formatter is cleaned before serialization.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = REDACTED if _is_sensitive_key(key) else _redact(value)

        if record.exc_info:
            payload["exception"] = _redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = _redact_text(self.formatStack(record.stack_info))

        return json.dumps(payload, default=str)


def create_log_handler(stream=None) -> logging.Handler:
    """Build a fresh StreamHandler wired to the redacting formatter.

    A factory, not a module-level singleton, for the same reason
    `db.session.create_session_factory` is: no import-time global state that
    leaks between tests or accumulates handlers on repeated use.
    """
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    return handler


def configure_logging() -> None:
    """Make redaction the default for the *whole process*, not just the
    `companion` logger tree.

    A handler attached only to `companion` would never see a third-party
    library's own logger (e.g. `pyrekordbox`), which isn't a child of
    `companion` and never propagates there. So the redacting handler goes
    on the *root* logger instead -- every logger in the process propagates
    to root by default, `companion`'s own included, so one handler covers
    everything without every module needing to know this exists.

    Known-risky third-party loggers (`pyrekordbox` logs the raw SQLCipher
    key at DEBUG, via `logger.debug("Key: %s", key)` -- text with no
    sensitive field name and no Bearer-shaped pattern, so the formatter's
    redaction can't structurally catch it, module docstring's known
    limitation) get three layers, not just a level bump:

    1. Level raised above DEBUG, so the record is never created at all in
       the common case.
    2. Any handler the library attached *directly to its own logger*
       removed. `pyrekordbox/logger.py` bolts a plain-text, non-redacting
       `StreamHandler` straight onto `logging.getLogger("pyrekordbox")` at
       import time -- independent of this module's root handler, and
       independent of the level, if that level is ever lowered again
       (second-round adversarial gate-review finding).
    3. Propagation to root turned off. A record that still gets created
       (level lowered elsewhere later) would reach *this* module's own
       JSON `message` field with the raw secret in it -- the message-text
       limitation applies here just as much as to the library's own
       handler, so routing it to root doesn't close the gap, only moves
       it. With no handler and no propagation, such a record is dropped
       silently instead of leaking anywhere.

    Idempotent: safe to call on every `get_logger()` call.
    """
    root = logging.getLogger()
    already_configured = any(
        isinstance(handler.formatter, RedactingJsonFormatter) for handler in root.handlers
    )
    if not already_configured:
        root.addHandler(create_log_handler())
        root.setLevel(logging.INFO)

    for logger_name in _THIRD_PARTY_LOGGERS_TO_SILENCE:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
        third_party_logger.handlers.clear()
        third_party_logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger with redaction guaranteed, via `configure_logging()`."""
    configure_logging()
    return logging.getLogger(name or _COMPANION_LOGGER_NAME)
