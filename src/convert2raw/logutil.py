"""Shared helper for building the timestamped, human-readable conversion log.

Used by every pipeline module (main, filterMZML, fixMSMSPrecursor,
prefixTimestamp) so that log lines emitted from any step - regardless of
which module produced them - carry the same '[YYYY-MM-DD HH:MM:SS]' prefix
in both the live TUI log and the per-file .log files written to disk.
"""

from __future__ import annotations

from datetime import datetime


def timestamp_line(msg: str) -> str:
    """Prefix *msg* with a '[YYYY-MM-DD HH:MM:SS]' timestamp.

    Blank lines and pure visual separators (e.g. a row of '=' or '-') are
    left untouched so they still read as spacing/dividers in the log file.
    """
    stripped = msg.strip()
    is_separator = bool(stripped) and len(set(stripped)) == 1 and not stripped[0].isalnum()
    if not msg or is_separator:
        return msg
    return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"


def log_line(log: list[str] | None, msg: str) -> None:
    """Append the timestamped *msg* to *log*, or print it if *log* is None."""
    line = timestamp_line(msg)
    if log is None:
        print(line)
    else:
        log.append(line)
