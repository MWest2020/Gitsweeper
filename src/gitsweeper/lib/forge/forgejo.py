"""Thin Forgejo/Gitea REST client.

Targets the Gitea-compatible v1 API (``/api/v1``) that Forgejo exposes;
Codeberg.org is the reference public instance, and self-hosted Forgejo/Gitea
instances expose the same API under their own base URL.

Synchronous on purpose, mirroring :mod:`gitsweeper.lib.forge.github`: the v1
use case is one user reading one repo's history at a time. The structure
(``from_env``, context manager, ``_paginate``, the five ``list_*`` methods)
deliberately parallels the GitHub provider; only the API specifics differ.

Differences from the GitHub provider, all sourced from the live Gitea v1 API:

- Auth header is Gitea-style ``Authorization: token <value>`` (not ``Bearer``).
- Timestamps carry a timezone offset (e.g. ``+02:00``), normalized to UTC
  ``Z`` in the mapping layer so they match GitHub downstream.
- Pagination is ``page`` (1-based) + ``limit``. A ``Link``/``X-Total-Count``
  header may or may not be present, so we advance ``page`` until a page
  returns zero items — the robust universal approach.
- Close-actor detection uses the issue *timeline* endpoint, whose close action
  is ``type == "close"`` with the actor under ``user.login`` (mapped to the
  normalized ``ForgeIssueEvent(event="closed", actor=...)``).
- Rate limiting is generic ``429`` / ``Retry-After`` backoff; there are no
  GitHub ``X-RateLimit-*`` assumptions.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from typing import Any

import httpx

from gitsweeper.lib.forge.base import (
    ForgeComment,
    ForgeCommit,
    ForgeIssueEvent,
    ForgePullRequest,
    ForgeRepo,
    normalize_timestamp,
)

CODEBERG_URL = "https://codeberg.org"
DEFAULT_LIMIT = 50
# Forgejo instances (Codeberg, self-hosted) are markedly slower per request
# than GitHub, so allow more headroom than the GitHub provider's 30s.
DEFAULT_TIMEOUT = 60.0
RATELIMIT_MAX_RETRIES = 5


class ForgejoError(RuntimeError):
    pass


def _to_pull_request(raw: dict[str, Any]) -> ForgePullRequest:
    # Gitea gives both a `merged` bool and `merged_at`; merge semantics are
    # "merged_at is non-null iff the PR merged".
    merged_at = normalize_timestamp(raw.get("merged_at")) if raw.get("merged") else None
    user = raw.get("user") or {}
    return ForgePullRequest(
        number=int(raw["number"]),
        state=raw.get("state", "open"),
        created_at=normalize_timestamp(raw.get("created_at")) or "",
        merged_at=merged_at,
        closed_at=normalize_timestamp(raw.get("closed_at")),
        author=user.get("login") or user.get("username") or "",
        raw=raw,
    )


def _to_comment(raw: dict[str, Any]) -> ForgeComment:
    user = raw.get("user") or {}
    return ForgeComment(
        created_at=normalize_timestamp(raw.get("created_at")) or "",
        author=user.get("login") or user.get("username") or "",
        body=raw.get("body") or "",
        raw=raw,
    )


def _to_issue_event(raw: dict[str, Any]) -> ForgeIssueEvent:
    # The Gitea timeline marks a close action with `type == "close"`; normalize
    # it to the `"closed"` event the close-actor classifier looks for. The
    # actor is the timeline entry's `user.login`.
    raw_type = raw.get("type")
    event = "closed" if raw_type == "close" else (raw_type or "")
    user = raw.get("user") or {}
    return ForgeIssueEvent(
        event=event,
        actor=user.get("login") or user.get("username"),
        raw=raw,
    )


def _to_repo(raw: dict[str, Any], *, default_owner: str) -> ForgeRepo:
    owner = raw.get("owner") or {}
    return ForgeRepo(
        owner=owner.get("login") or owner.get("username") or default_owner,
        name=raw["name"],
        raw=raw,
    )


def _to_commit(raw: dict[str, Any]) -> ForgeCommit:
    commit = raw.get("commit") or {}
    commit_author = commit.get("author") or {}
    author = raw.get("author") or {}
    return ForgeCommit(
        sha=raw.get("sha") or "",
        message=commit.get("message") or "",
        author=author.get("login") or author.get("username"),
        author_name=commit_author.get("name"),
        author_date=normalize_timestamp(raw.get("created") or commit_author.get("date")),
        raw=raw,
    )


class ForgejoClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = CODEBERG_URL,
        http_client: httpx.Client | None = None,
        sleep_fn=time.sleep,
        warn_stream=sys.stderr,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_url = self._base_url + "/api/v1"
        self._token = token
        self._sleep = sleep_fn
        self._warn_stream = warn_stream
        self._unauth_warned = False
        headers = {
            "Accept": "application/json",
            "User-Agent": "gitsweeper/0.0.0",
        }
        if token:
            headers["Authorization"] = f"token {token}"
        self._client = http_client or httpx.Client(headers=headers, timeout=DEFAULT_TIMEOUT)
        if http_client is not None and token:
            # Caller supplied a client; merge auth so tests can pass their own.
            self._client.headers["Authorization"] = f"token {token}"

    @classmethod
    def from_env(cls, **kwargs: Any) -> ForgejoClient:
        env_url = os.environ.get("GITSWEEPER_FORGEJO_URL")
        if env_url and "base_url" not in kwargs:
            kwargs["base_url"] = env_url
        return cls(token=os.environ.get("FORGEJO_TOKEN"), **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ForgejoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterator[ForgePullRequest]:
        path = f"/repos/{owner}/{repo}/pulls"
        # No server-side sort: Gitea's `sort=oldest` forces a full ordered scan
        # that 504s on large repos at slow instances like Codeberg, and no
        # analysis depends on PR order (percentiles and per-PR metrics are
        # order-independent; storage upserts by (repo, number)).
        params = {"state": state}
        for raw in self._paginate(self._api_url + path, params):
            yield _to_pull_request(raw)

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeComment]:
        path = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        for raw in self._paginate(self._api_url + path, {}):
            yield _to_comment(raw)

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeIssueEvent]:
        # Gitea exposes the close actor via the issue timeline.
        path = f"/repos/{owner}/{repo}/issues/{issue_number}/timeline"
        for raw in self._paginate(self._api_url + path, {}):
            yield _to_issue_event(raw)

    def list_org_repos(self, org: str) -> Iterator[ForgeRepo]:
        path = f"/orgs/{org}/repos"
        for raw in self._paginate(self._api_url + path, {}):
            yield _to_repo(raw, default_owner=org)

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        since: str | None = None,
        sha: str | None = None,
    ) -> Iterator[ForgeCommit]:
        """List commits on a repo branch. Paginated.

        ``since`` is an ISO 8601 timestamp passed verbatim to Gitea.
        ``sha`` is the branch name (defaults to the repo's default
        branch when omitted).
        """
        path = f"/repos/{owner}/{repo}/commits"
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if sha:
            params["sha"] = sha
        for raw in self._paginate(self._api_url + path, params):
            yield _to_commit(raw)

    def _paginate(
        self, url: str, params: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """Advance ``page`` until a page returns zero items.

        A ``Link``/``X-Total-Count`` header may or may not be present, so we
        do not rely on it: an empty page is the universal end-of-data signal.
        """
        page = 1
        while True:
            page_params = {**params, "page": page, "limit": DEFAULT_LIMIT}
            response = self._request("GET", url, params=page_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise ForgejoError(
                    f"expected JSON array from {url}, "
                    f"got {type(payload).__name__}"
                )
            if not payload:
                return
            yield from payload
            page += 1

    def _request(
        self, method: str, url: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        self._maybe_warn_unauthenticated()

        attempt = 0
        while True:
            response = self._client.request(method, url, params=params)

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                if retry_after is not None and attempt < RATELIMIT_MAX_RETRIES:
                    delay = max(0.0, float(retry_after))
                    self._notice(
                        f"Rate limit hit on {url}; sleeping {delay:.0f}s"
                    )
                    self._sleep(delay)
                    attempt += 1
                    continue

            if response.status_code >= 400:
                raise ForgejoError(
                    f"Forgejo API error {response.status_code} for {url}: "
                    f"{response.text[:300]}"
                )
            return response

    def _maybe_warn_unauthenticated(self) -> None:
        if self._token or self._unauth_warned:
            return
        self._unauth_warned = True
        self._notice(
            "FORGEJO_TOKEN is not set: reading anonymously. This works for "
            "public repositories on instances that permit it (e.g. Codeberg), "
            "but may be rate-limited or incomplete."
        )

    def _notice(self, message: str) -> None:
        print(f"[gitsweeper] {message}", file=self._warn_stream)
