"""Thin GitLab REST API v4 client.

Targets the GitLab REST API v4 (``/api/v4``); gitlab.com is the reference
public instance, and self-hosted GitLab instances expose the same API under
their own base URL.

Synchronous on purpose, mirroring :mod:`gitsweeper.lib.forge.forgejo` and
:mod:`gitsweeper.lib.forge.github`: the use case is one user reading one
project's history at a time. The structure (``from_env``, context manager,
``_paginate``, the five ``list_*`` methods) deliberately parallels the other
providers; only the API specifics differ.

Differences from the GitHub/Forgejo providers, all sourced from the live
GitLab v4 API (gitlab.com):

- A project is addressed by its URL-encoded ``namespace/project`` path
  (``owner%2Frepo``); this provider encodes ``owner/repo`` once via
  :func:`urllib.parse.quote`.
- A merge request's per-project number is ``iid`` (NOT the global ``id``).
- State is ``opened`` / ``closed`` / ``merged``: ``opened`` normalizes to
  ``"open"`` and both ``merged`` and ``closed`` normalize to ``"closed"``.
  ``merged_at`` is treated as non-null only when the MR actually merged.
- Auth header is ``PRIVATE-TOKEN: <value>`` (GitLab's PAT convention).
- The branch parameter for commits is ``ref_name`` (not ``sha``); ``since``
  is supported.
- Close-actor detection uses ``resource_state_events``, whose close action is
  ``state == "closed"`` with the actor under ``user.username``. The endpoint
  is absent on old self-hosted GitLab (404), in which case it degrades to no
  close actor rather than crashing.
- Pagination is ``page`` (1-based) + ``per_page``; we advance ``page`` until a
  page returns zero items — the robust universal approach.
- Rate limiting is generic ``429`` / ``Retry-After`` backoff; GitLab also
  sends ``RateLimit-*`` headers but generic backoff is sufficient.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx

from gitsweeper.lib.forge.base import (
    ForgeComment,
    ForgeCommit,
    ForgeIssueEvent,
    ForgePullRequest,
    ForgeRepo,
    normalize_timestamp,
)

GITLAB_URL = "https://gitlab.com"
DEFAULT_PER_PAGE = 50
# Self-hosted GitLab and gitlab.com under load can be slow per request, so
# allow the same headroom as the Forgejo provider rather than GitHub's 30s.
DEFAULT_TIMEOUT = 60.0
RATELIMIT_MAX_RETRIES = 5


class GitLabError(RuntimeError):
    pass


def _encode_project(owner: str, repo: str) -> str:
    """URL-encode ``owner/repo`` to the GitLab project path ``owner%2Frepo``."""
    return quote(f"{owner}/{repo}", safe="")


def _to_pull_request(raw: dict[str, Any]) -> ForgePullRequest:
    # `iid` is the per-project number GitLab shows in the UI; `id` is global
    # and must not be used. State `opened` -> open; `merged`/`closed` -> closed.
    # GitLab sets `merged_at` only when the MR merged, but guard on state too.
    gl_state = raw.get("state")
    state = "open" if gl_state == "opened" else "closed"
    merged = gl_state == "merged" or bool(raw.get("merged_at"))
    merged_at = normalize_timestamp(raw.get("merged_at")) if merged else None
    # A merged MR is closed at merge time even though GitLab leaves `closed_at`
    # null for it; fall back to merged_at so closed_at is non-null for any
    # closed PR (base.py's contract).
    closed_at = normalize_timestamp(raw.get("closed_at")) or merged_at
    author = raw.get("author") or {}
    return ForgePullRequest(
        number=int(raw["iid"]),
        state=state,
        created_at=normalize_timestamp(raw.get("created_at")) or "",
        merged_at=merged_at,
        closed_at=closed_at,
        author=author.get("username") or "",
        raw=raw,
    )


def _to_comment(raw: dict[str, Any]) -> ForgeComment:
    author = raw.get("author") or {}
    return ForgeComment(
        created_at=normalize_timestamp(raw.get("created_at")) or "",
        author=author.get("username") or "",
        body=raw.get("body") or "",
        raw=raw,
    )


def _to_issue_event(raw: dict[str, Any]) -> ForgeIssueEvent:
    # A resource state event marks a close with `state == "closed"`; normalize
    # it to the `"closed"` event the close-actor classifier looks for. The
    # actor is the event's `user.username`.
    raw_state = raw.get("state")
    event = "closed" if raw_state == "closed" else (raw_state or "")
    user = raw.get("user") or {}
    return ForgeIssueEvent(
        event=event,
        actor=user.get("username"),
        raw=raw,
    )


def _to_repo(raw: dict[str, Any], *, default_owner: str) -> ForgeRepo:
    # `path` is the bare repo name; the group is the namespace's full path.
    namespace = raw.get("namespace") or {}
    owner = namespace.get("full_path")
    if not owner:
        path_with_namespace = raw.get("path_with_namespace") or ""
        owner = path_with_namespace.rsplit("/", 1)[0] if "/" in path_with_namespace else ""
    return ForgeRepo(
        owner=owner or default_owner,
        name=raw.get("path") or raw.get("name") or "",
        raw=raw,
    )


def _to_commit(raw: dict[str, Any]) -> ForgeCommit:
    # GitLab keys commits by name/email, so there is no forge login.
    return ForgeCommit(
        sha=raw.get("id") or "",
        message=raw.get("message") or "",
        author=None,
        author_name=raw.get("author_name"),
        author_date=normalize_timestamp(raw.get("authored_date")),
        raw=raw,
    )


class GitLabClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = GITLAB_URL,
        http_client: httpx.Client | None = None,
        sleep_fn=time.sleep,
        warn_stream=sys.stderr,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_url = self._base_url + "/api/v4"
        self._token = token
        self._sleep = sleep_fn
        self._warn_stream = warn_stream
        self._unauth_warned = False
        headers = {
            "Accept": "application/json",
            "User-Agent": "gitsweeper/0.0.0",
        }
        if token:
            headers["PRIVATE-TOKEN"] = token
        self._client = http_client or httpx.Client(headers=headers, timeout=DEFAULT_TIMEOUT)
        if http_client is not None and token:
            # Caller supplied a client; merge auth so tests can pass their own.
            self._client.headers["PRIVATE-TOKEN"] = token

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitLabClient:
        env_url = os.environ.get("GITSWEEPER_GITLAB_URL")
        if env_url and "base_url" not in kwargs:
            kwargs["base_url"] = env_url
        return cls(token=os.environ.get("GITLAB_TOKEN"), **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitLabClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterator[ForgePullRequest]:
        project = _encode_project(owner, repo)
        path = f"/projects/{project}/merge_requests"
        # No server-side sort: no analysis depends on MR order (percentiles and
        # per-PR metrics are order-independent; storage upserts by (repo, number)).
        params = {"state": state}
        for raw in self._paginate(self._api_url + path, params):
            yield _to_pull_request(raw)

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeComment]:
        project = _encode_project(owner, repo)
        path = f"/projects/{project}/merge_requests/{issue_number}/notes"
        for raw in self._paginate(self._api_url + path, {}):
            yield _to_comment(raw)

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[ForgeIssueEvent]:
        # GitLab exposes the close actor via resource state events. The endpoint
        # is absent on old self-hosted GitLab: degrade to no close actor.
        project = _encode_project(owner, repo)
        path = f"/projects/{project}/merge_requests/{issue_number}/resource_state_events"
        for raw in self._paginate(self._api_url + path, {}, missing_ok=True):
            yield _to_issue_event(raw)

    def list_org_repos(self, org: str) -> Iterator[ForgeRepo]:
        group = quote(org, safe="")
        path = f"/groups/{group}/projects"
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
        """List commits on a project branch. Paginated.

        ``since`` is an ISO 8601 timestamp passed verbatim to GitLab.
        ``sha`` is the branch name (defaults to the project's default branch
        when omitted); GitLab's branch parameter is ``ref_name``.
        """
        project = _encode_project(owner, repo)
        path = f"/projects/{project}/repository/commits"
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if sha:
            params["ref_name"] = sha
        for raw in self._paginate(self._api_url + path, params):
            yield _to_commit(raw)

    def _paginate(
        self, url: str, params: dict[str, Any], *, missing_ok: bool = False
    ) -> Iterator[dict[str, Any]]:
        """Advance ``page`` until a page returns zero items.

        A ``Link``/``X-Next-Page`` header may or may not be present, so we do
        not rely on it: an empty page is the universal end-of-data signal. When
        ``missing_ok`` is set, a 404 (endpoint absent on old self-hosted
        GitLab) is treated as no data rather than an error.
        """
        page = 1
        while True:
            page_params = {**params, "page": page, "per_page": DEFAULT_PER_PAGE}
            response = self._request("GET", url, params=page_params, missing_ok=missing_ok)
            if response is None:
                return
            payload = response.json()
            if not isinstance(payload, list):
                raise GitLabError(
                    f"expected JSON array from {url}, "
                    f"got {type(payload).__name__}"
                )
            if not payload:
                return
            yield from payload
            page += 1

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> httpx.Response | None:
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

            if missing_ok and response.status_code == 404:
                return None

            if response.status_code >= 400:
                raise GitLabError(
                    f"GitLab API error {response.status_code} for {url}: "
                    f"{response.text[:300]}"
                )
            return response

    def _maybe_warn_unauthenticated(self) -> None:
        if self._token or self._unauth_warned:
            return
        self._unauth_warned = True
        self._notice(
            "GITLAB_TOKEN is not set: reading anonymously. This works for "
            "public projects on instances that permit it, but may be "
            "rate-limited or incomplete (some sub-resources require a token)."
        )

    def _notice(self, message: str) -> None:
        print(f"[gitsweeper] {message}", file=self._warn_stream)
