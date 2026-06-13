"""The forge-agnostic provider seam.

`ForgeProvider` is the interface every analysis capability acquires data
through, so the capabilities never name a concrete forge. v1 ships GitHub
only, and the GitHub provider returns GitHub's native JSON dicts as-is.

A normalized cross-forge data model (frozen dataclasses with uniform merge
semantics and a retained raw payload) is deliberately **not** built here:
you cannot validate a normalization layer against a single forge. It lands
with the first non-GitHub provider, where a second concrete shape makes the
abstraction real rather than speculative. Until then the protocol's return
type is the GitHub dict shape the existing capabilities already consume.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ForgeProvider(Protocol):
    """What an analysis capability needs from a forge to acquire data."""

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterator[dict[str, Any]]: ...

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[dict[str, Any]]: ...

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[dict[str, Any]]: ...

    def list_org_repos(self, org: str) -> Iterator[dict[str, Any]]: ...

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        since: str | None = None,
        sha: str | None = None,
    ) -> Iterator[dict[str, Any]]: ...

    def close(self) -> None: ...

    def __enter__(self) -> ForgeProvider: ...

    def __exit__(self, *exc: object) -> None: ...
