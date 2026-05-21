"""Pure parser helpers for commit-message footers.

No I/O. Two functions:

- :func:`parse_time_footer` extracts a ``Time: <duration>`` line and
  returns minutes, or None when absent. Case-insensitive on the
  prefix; duration formats match Billbird's ``/log`` (``2h``, ``45m``,
  ``1h30m``). If multiple footers appear in the same message, the
  last one wins — the dev's most recent intent.
- :func:`parse_issue_refs` extracts same-repo issue references
  (``#42``, ``Closes #42``, etc.). Cross-repo references
  (``other/repo#42``) are intentionally ignored: they point at work
  outside this repo's reconcile scope.

Kept small and dependency-free so the test suite covers it
exhaustively without DB or HTTP.
"""

from __future__ import annotations

import re

# Anchor the footer to its own line so a duration inside the commit
# body proper (e.g. "took 2h to write") doesn't trip it.
_TIME_RE = re.compile(
    r"^[ \t]*Time:[ \t]*(?:(\d+)h)?(?:(\d+)m)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Same-repo #N references. The negative-lookbehind blocks
# `owner/repo#N` cross-repo refs (the `/` would precede the `#`).
_ISSUE_RE = re.compile(r"(?<![A-Za-z0-9/_-])#(\d+)\b")


def parse_time_footer(message: str) -> int | None:
    """Return the duration encoded in the last ``Time:`` footer, in
    minutes; return None when no footer is present or the duration
    parses to zero.
    """
    if not message:
        return None
    last_minutes: int | None = None
    for match in _TIME_RE.finditer(message):
        hours_str, mins_str = match.group(1), match.group(2)
        if not hours_str and not mins_str:
            # `Time:` with nothing after — ignored.
            continue
        hours = int(hours_str) if hours_str else 0
        minutes = int(mins_str) if mins_str else 0
        total = hours * 60 + minutes
        if total > 0:
            last_minutes = total
    return last_minutes


def parse_issue_refs(message: str) -> list[int]:
    """Return same-repo issue numbers referenced in ``message`` —
    deduplicated, ordered by first appearance. Cross-repo references
    are ignored.
    """
    if not message:
        return []
    seen: list[int] = []
    for match in _ISSUE_RE.finditer(message):
        n = int(match.group(1))
        if n not in seen:
            seen.append(n)
    return seen
