"""The forge-agnostic provider seam and its normalized data model.

`ForgeProvider` is the interface every analysis capability acquires data
through, so the capabilities never name a concrete forge. Providers map their
native JSON onto the frozen dataclasses below — `ForgePullRequest`,
`ForgeComment`, `ForgeIssueEvent`, `ForgeCommit`, `ForgeRepo` — each of which
carries only the fields the analyses actually read plus a `raw: dict` holding
the provider's original response (so the mapping stays non-lossy and storage's
`raw_payload` column is fed verbatim).

Timestamps are normalized to UTC ISO-8601 with a trailing ``Z`` in the mapping
layer (see :func:`normalize_timestamp`), so GitHub (already ``Z``) and Forgejo
(timezone offsets like ``+02:00``) produce identical downstream strings.

The model lands with the first non-GitHub provider (Forgejo): a second concrete
shape is what makes the abstraction real rather than speculative. The
parameterised contract suite encodes the cross-forge invariants both providers
must satisfy.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


def normalize_timestamp(value: str | None) -> str | None:
    """Normalize an ISO-8601 timestamp to UTC with a trailing ``Z``.

    GitHub already emits ``...Z`` (UTC) and round-trips unchanged. Forgejo/Gitea
    emit a timezone offset (e.g. ``2026-06-13T19:43:08+02:00``) which is
    converted to the equivalent UTC instant. ``None`` and empty strings pass
    through as ``None`` so nullable fields (``merged_at``, ``closed_at``) stay
    nullable.

    Gitea/Forgejo also emit a year-1 "zero time" sentinel (e.g.
    ``0001-01-01T00:00:00Z``) for an unset timestamp. Converting that to UTC
    can overflow ``MINYEAR`` (a positive offset pushes it below year 1), and
    even when it parses it yields a malformed non-zero-padded year. Any parse
    failure, or a parsed year before 1970, is treated as "unset" and returns
    ``None``.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if parsed.year < 1970:
            return None
        return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class ForgePullRequest:
    """A pull request, normalized across forges.

    ``merged_at`` is non-null iff the PR was merged; ``closed_at`` is non-null
    for any closed PR (merged or not). ``raw`` is the provider's original PR
    JSON, persisted verbatim as the ``raw_payload`` column.
    """

    number: int
    state: str
    created_at: str
    merged_at: str | None
    closed_at: str | None
    author: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class ForgeComment:
    """A comment on an issue/PR, normalized across forges."""

    created_at: str
    author: str
    body: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class ForgeIssueEvent:
    """A timeline/issue event, normalized to what close-actor detection needs.

    ``event`` is the normalized event type (``"closed"`` for the close action);
    ``actor`` is the login of the user who performed it, or ``None`` when the
    forge does not attribute it.
    """

    event: str
    actor: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ForgeCommit:
    """A commit, normalized across forges.

    ``author`` is the forge login when known, else ``None``; ``author_name`` is
    the name from the commit metadata (the reconcile capability falls back to it
    when there is no login).
    """

    sha: str
    message: str
    author: str | None
    author_name: str | None
    author_date: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ForgeRepo:
    """A repository reference, normalized across forges."""

    owner: str
    name: str
    raw: dict[str, Any]


@runtime_checkable
class ForgeProvider(Protocol):
    """What an analysis capability needs from a forge to acquire data."""

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterator[ForgePullRequest]: ...

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeComment]: ...

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeIssueEvent]: ...

    def list_org_repos(self, org: str) -> Iterator[ForgeRepo]: ...

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        since: str | None = None,
        sha: str | None = None,
    ) -> Iterator[ForgeCommit]: ...

    def close(self) -> None: ...

    def __enter__(self) -> ForgeProvider: ...

    def __exit__(self, *exc: object) -> None: ...
