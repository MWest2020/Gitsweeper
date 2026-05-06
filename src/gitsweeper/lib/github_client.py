"""Thin GitHub REST client.

Synchronous on purpose: the v1 use case is one user fetching one repo's
PR history at a time. Sync code is easier to read, easier to test, and
fast enough for a few thousand pull requests. If we ever need
concurrency we revisit the choice rather than designing for it now.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Iterator
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"
DEFAULT_PER_PAGE = 100
DEFAULT_TIMEOUT = 30.0
SECONDARY_RATELIMIT_MAX_RETRIES = 5

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


def _parse_next_link(header_value: str) -> str | None:
    if not header_value:
        return None
    for url, rel in _LINK_RE.findall(header_value):
        if rel == "next":
            return url
    return None


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = GITHUB_API,
        http_client: httpx.Client | None = None,
        sleep_fn=time.sleep,
        now_fn=time.time,
        warn_stream=sys.stderr,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._sleep = sleep_fn
        self._now = now_fn
        self._warn_stream = warn_stream
        self._unauth_warned = False
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gitsweeper/0.0.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = http_client or httpx.Client(headers=headers, timeout=DEFAULT_TIMEOUT)
        if http_client is not None and token:
            # Caller supplied a client; merge auth so tests can pass their own.
            self._client.headers["Authorization"] = f"Bearer {token}"
        self._rate_reset_at: float | None = None

    @classmethod
    def from_env(cls, **kwargs: Any) -> GitHubClient:
        return cls(token=os.environ.get("GITHUB_TOKEN"), **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def list_pull_requests(
        self, owner: str, repo: str, state: str = "all"
    ) -> Iterator[dict[str, Any]]:
        path = f"/repos/{owner}/{repo}/pulls"
        params: dict[str, Any] | None = {
            "state": state,
            "per_page": DEFAULT_PER_PAGE,
            "sort": "created",
            "direction": "asc",
        }
        yield from self._paginate(self._base_url + path, params)

    def list_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[dict[str, Any]]:
        path = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        params: dict[str, Any] | None = {"per_page": DEFAULT_PER_PAGE}
        yield from self._paginate(self._base_url + path, params)

    def list_issue_events(
        self, owner: str, repo: str, issue_number: int
    ) -> Iterator[dict[str, Any]]:
        path = f"/repos/{owner}/{repo}/issues/{issue_number}/events"
        params: dict[str, Any] | None = {"per_page": DEFAULT_PER_PAGE}
        yield from self._paginate(self._base_url + path, params)

    def _paginate(
        self, url: str, params: dict[str, Any] | None
    ) -> Iterator[dict[str, Any]]:
        next_url: str | None = url
        next_params = params
        while next_url is not None:
            response = self._request("GET", next_url, params=next_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubError(
                    f"expected JSON array from {next_url}, "
                    f"got {type(payload).__name__}"
                )
            yield from payload
            next_url = _parse_next_link(response.headers.get("link", ""))
            next_params = None  # follow-up URLs already carry query string

    def _request(
        self, method: str, url: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        self._maybe_warn_unauthenticated()
        self._maybe_sleep_for_primary_rate_limit()

        attempt = 0
        while True:
            response = self._client.request(method, url, params=params)
            self._update_rate_limit_state(response)

            if response.status_code in (403, 429):
                retry_after = response.headers.get("retry-after")
                if retry_after is not None and attempt < SECONDARY_RATELIMIT_MAX_RETRIES:
                    delay = max(0.0, float(retry_after))
                    self._notice(
                        f"Secondary rate limit hit on {url}; sleeping {delay:.0f}s"
                    )
                    self._sleep(delay)
                    attempt += 1
                    continue
                if response.headers.get("x-ratelimit-remaining") == "0":
                    # Primary limit; sleep until reset and retry once.
                    self._maybe_sleep_for_primary_rate_limit()
                    if attempt < SECONDARY_RATELIMIT_MAX_RETRIES:
                        attempt += 1
                        continue

            if response.status_code >= 400:
                raise GitHubError(
                    f"GitHub API error {response.status_code} for {url}: {response.text[:300]}"
                )
            return response

    def _maybe_warn_unauthenticated(self) -> None:
        if self._token or self._unauth_warned:
            return
        self._unauth_warned = True
        self._notice(
            "GITHUB_TOKEN is not set: running with the unauthenticated rate-limit "
            "budget (60 requests/hour). Fetches may be slow or incomplete for "
            "larger repositories."
        )

    def _maybe_sleep_for_primary_rate_limit(self) -> None:
        if self._rate_reset_at is None:
            return
        delta = self._rate_reset_at - self._now()
        if delta > 0:
            self._notice(
                f"Primary rate limit exhausted; sleeping {delta:.0f}s until reset"
            )
            self._sleep(delta)
        self._rate_reset_at = None

    def _update_rate_limit_state(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining == "0" and reset is not None:
            try:
                self._rate_reset_at = float(reset)
            except ValueError:
                self._rate_reset_at = None

    def _notice(self, message: str) -> None:
        print(f"[gitsweeper] {message}", file=self._warn_stream)
