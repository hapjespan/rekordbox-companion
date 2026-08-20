"""T018: logging.py — structured JSON logging with token/key redaction.

Redaction is the security boundary (NIS2 logging plan, constraints.md): a
missed path leaks the operator's Spotify OAuth tokens or the Rekordbox
SQLCipher key into logs. These tests therefore assert the redaction is a
property of the formatter itself — structurally guaranteed for every record
emitted through it — not something each call site remembers to do. The raw
secret string must never survive into the formatted output, under any of the
realistic-misuse shapes a future caller might pass.
"""

import io
import json
import logging

from companion.logging import (
    _THIRD_PARTY_LOGGERS_TO_SILENCE,
    REDACTED,
    RedactingJsonFormatter,
    configure_logging,
    create_log_handler,
    get_logger,
)

SECRET = "BQ-super-secret-oauth-value-9f73e6b0647c"


def _record(msg="event", **extra):
    """A LogRecord as `logging` builds one from `logger.info(msg, extra=...)`."""
    record = logging.LogRecord(
        name="companion.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(record):
    formatted = RedactingJsonFormatter().format(record)
    return formatted, json.loads(formatted)


def test_output_is_one_parseable_json_object_per_line():
    formatted, payload = _format(_record("guard refused write"))
    assert "\n" not in formatted
    assert payload["message"] == "guard refused write"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "companion.test"
    assert "timestamp" in payload


def test_access_token_field_is_redacted():
    formatted, payload = _format(_record(access_token=SECRET))
    assert SECRET not in formatted
    assert payload["access_token"] == REDACTED


def test_refresh_token_field_is_redacted():
    formatted, payload = _format(_record(refresh_token=SECRET))
    assert SECRET not in formatted
    assert payload["refresh_token"] == REDACTED


def test_sqlcipher_key_field_is_redacted():
    formatted, payload = _format(_record(sqlcipher_key=SECRET))
    assert SECRET not in formatted
    assert payload["sqlcipher_key"] == REDACTED


def test_other_plausible_names_for_the_sqlcipher_key_are_also_redacted():
    # "sqlcipher_key" is one specific spelling; rb/guard.py and rb/writer.py
    # (built later, US3) are just as likely to call the same value db_key,
    # encryption_key, master_key, cipher_key, or bare key -- none of these
    # contain the substring "sqlcipher" or "private_key", so the original
    # marker set missed them (adversarial gate-review finding, T018).
    for field_name in ("db_key", "encryption_key", "master_key", "cipher_key", "key"):
        formatted, payload = _format(_record(**{field_name: SECRET}))
        assert SECRET not in formatted, f"{field_name!r} leaked the secret"
        assert payload[field_name] == REDACTED, f"{field_name!r} was not redacted"


def test_authorization_header_field_is_redacted():
    # Request headers can carry `Authorization: Bearer ...` (constraints.md:
    # request headers are deliberately never logged).
    formatted, payload = _format(_record(authorization=f"Bearer {SECRET}"))
    assert SECRET not in formatted
    assert payload["authorization"] == REDACTED


def test_bare_auth_field_name_is_also_redacted():
    # "authorization" matched, but the marker check is substring-in-key, not
    # key-in-marker: a field literally named "auth" (a very plausible
    # abbreviation) didn't contain the substring "authorization" and slipped
    # through (adversarial gate-review finding, T018).
    formatted, payload = _format(_record(auth=SECRET))
    assert SECRET not in formatted
    assert payload["auth"] == REDACTED


def test_bare_pass_field_name_is_also_redacted():
    # "password"/"passwd" matched, but not the field name "pass" alone
    # (adversarial gate-review finding, T018).
    formatted, payload = _format(_record(**{"pass": SECRET}))
    assert SECRET not in formatted
    assert payload["pass"] == REDACTED


def test_pkce_code_verifier_field_is_redacted():
    # The Spotify PKCE code_verifier (research.md R2/FR-001) matched none of
    # the original markers (adversarial gate-review finding, T018).
    formatted, payload = _format(_record(code_verifier=SECRET))
    assert SECRET not in formatted
    assert payload["code_verifier"] == REDACTED


def test_non_sensitive_fields_pass_through_untouched():
    formatted, payload = _format(
        _record("backup created", rb_content_id="1234", pruned_count=3, path="rotation-slot-2")
    )
    assert payload["rb_content_id"] == "1234"
    assert payload["pruned_count"] == 3
    assert payload["path"] == "rotation-slot-2"


def test_secret_nested_in_a_dict_is_redacted():
    # A careless caller logs a whole structured payload; the secret sits one
    # level down, under a sensitive key, next to a harmless sibling.
    formatted, payload = _format(
        _record(response={"refresh_token": SECRET, "account": "dj@example.com"})
    )
    assert SECRET not in formatted
    assert payload["response"]["refresh_token"] == REDACTED
    assert payload["response"]["account"] == "dj@example.com"


def test_secret_nested_in_a_list_of_dicts_is_redacted():
    # Non-sensitive outer key, so the list is walked rather than blanked
    # wholesale; the secret hides in each element under a sensitive key.
    formatted, payload = _format(
        _record(accounts=[{"access_token": SECRET}, {"access_token": SECRET + "2"}])
    )
    assert SECRET not in formatted
    assert payload["accounts"][0]["access_token"] == REDACTED
    assert payload["accounts"][1]["access_token"] == REDACTED


def test_bearer_token_in_the_message_string_is_redacted():
    # Best-effort value-level redaction: a Bearer credential rendered into the
    # message text itself, with no sensitive field name to key off.
    formatted, payload = _format(_record(f"calling spotify with Authorization: Bearer {SECRET}"))
    assert SECRET not in formatted
    assert "Bearer" in payload["message"]
    assert REDACTED in payload["message"]


def test_exception_stack_trace_is_included_and_scrubbed():
    try:
        raise ValueError(f"boom with Bearer {SECRET}")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="companion.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="write failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    formatted, payload = _format(record)
    assert "exception" in payload
    assert "ValueError" in payload["exception"]
    assert SECRET not in formatted


def test_redaction_holds_through_a_configured_logger_and_handler():
    # The structural guarantee end to end: a caller who never redacts anything
    # by hand still cannot leak, because the handler's formatter does it.
    stream = io.StringIO()
    logger = logging.getLogger("companion.test.integration")
    logger.handlers.clear()
    logger.addHandler(create_log_handler(stream))
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("token refresh", extra={"access_token": SECRET})

    line = stream.getvalue()
    assert SECRET not in line
    assert json.loads(line)["access_token"] == REDACTED


def test_get_logger_returns_companion_child_and_is_idempotent():
    first = get_logger("companion.rb.writer")
    second = get_logger("companion.rb.writer")
    assert first is second


def test_configure_logging_attaches_the_redacting_handler_to_root_only_once():
    # Root, not just the companion tree (see the two tests below for why):
    # a handler attached only to "companion" never sees a third-party
    # library's own logger, which isn't a child of "companion" at all
    # (adversarial gate-review finding, T018).
    root = logging.getLogger()
    root.handlers = [
        h for h in root.handlers if not isinstance(h.formatter, RedactingJsonFormatter)
    ]

    configure_logging()
    configure_logging()  # idempotent: calling twice must not duplicate

    redacting = [h for h in root.handlers if isinstance(h.formatter, RedactingJsonFormatter)]
    assert len(redacting) == 1


def test_pyrekordbox_logger_is_silenced_above_the_level_it_logs_the_key_at():
    # pyrekordbox.db6.database.Rekordbox6Database.__init__ does
    # `logger.debug("Key: %s", key)` on its OWN logger -- entirely outside
    # the companion tree, and the raw key is interpolated into free text
    # with no recognizable pattern the Bearer-only text scrub could catch.
    # The only structural defense available is preventing the record from
    # ever being created: raise the third-party logger's level so its DEBUG
    # call never fires (adversarial gate-review finding, T018).
    assert "pyrekordbox" in _THIRD_PARTY_LOGGERS_TO_SILENCE

    configure_logging()

    assert logging.getLogger("pyrekordbox").getEffectiveLevel() > logging.DEBUG


def test_pyrekordbox_key_log_call_does_not_reach_any_handler_after_configuring():
    # End-to-end: the exact call pyrekordbox makes, verified to produce no
    # output at all once this module has configured logging -- not just
    # that the level looks right, but that the record is truly suppressed.
    stream = io.StringIO()
    configure_logging()
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, RedactingJsonFormatter):
            handler.stream = stream

    pyrekordbox_logger = logging.getLogger("pyrekordbox.db6.database")
    pyrekordbox_logger.debug("Key: %s", SECRET)

    assert stream.getvalue() == ""


def test_pyrekordboxs_own_raw_handler_is_removed_not_just_leveled_down():
    # pyrekordbox/logger.py bolts its OWN plain-text, non-redacting
    # StreamHandler directly onto `logging.getLogger("pyrekordbox")` at
    # import time. Raising the level alone is not handler-independent the
    # way the module doc claims: if that level is ever lowered again
    # anywhere in the process (a future debug flag, a pyrekordbox version
    # bump), the record would still reach pyrekordbox's own raw handler and
    # print the key to stderr unredacted, bypassing this module's root
    # handler entirely (second-round adversarial gate-review finding,
    # T018). The handler itself must be removed, not just the level raised.
    import pyrekordbox.logger  # noqa: F401  (registers pyrekordbox's own handler)

    configure_logging()

    pyrekordbox_logger = logging.getLogger("pyrekordbox")
    assert pyrekordbox_logger.handlers == []
    # propagate=False, deliberately: propagating to root would only move the
    # leak, not close it -- root's formatter redacts known field names and
    # Bearer-shaped text, but "Key: %s" % key has neither, so the raw
    # secret would still land in this module's own JSON `message` field.
    # With no handler and no propagation, a record that slips past the
    # level guard is dropped silently instead of leaking anywhere.
    assert pyrekordbox_logger.propagate is False


def test_pyrekordbox_key_log_is_still_suppressed_even_if_level_is_later_lowered():
    # The level-guard is one layer; this proves the *second* layer (handler
    # removed, propagation off) also holds if something later re-enables
    # DEBUG on pyrekordbox specifically: the record is created but reaches
    # no handler anywhere, so nothing is printed, not even redacted.
    stream = io.StringIO()
    configure_logging()
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, RedactingJsonFormatter):
            handler.stream = stream

    logging.getLogger("pyrekordbox").setLevel(logging.DEBUG)
    logging.getLogger("pyrekordbox.db6.database").debug("Key: %s", SECRET)

    assert stream.getvalue() == ""
