"""Resolve a repository reference (and an optional override) to a provider.

Order of resolution: an explicit ``forge`` override wins; otherwise the host
of a fully-qualified reference is consulted (``github.com`` -> GitHub,
``codeberg.org`` or a configured self-hosted Forgejo host -> Forgejo,
``gitlab.com`` or a configured self-hosted GitLab host -> GitLab); otherwise a
bare ``owner/repo`` defaults to GitHub. An unsupported forge is rejected by
name rather than silently falling back to GitHub.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from gitsweeper.lib.forge.base import ForgeProvider
from gitsweeper.lib.forge.forgejo import ForgejoClient
from gitsweeper.lib.forge.github import GitHubClient
from gitsweeper.lib.forge.gitlab import GitLabClient

#: Forges with a concrete provider today.
SUPPORTED_FORGES: tuple[str, ...] = ("github", "forgejo", "gitlab")


class UnsupportedForgeError(ValueError):
    """Raised when a forge is requested that has no registered provider."""


def get_forge_provider(
    repo_ref: str | None = None, *, forge: str | None = None, **kwargs: Any
) -> ForgeProvider:
    """Return a forge provider for ``repo_ref`` / ``forge``.

    ``kwargs`` are forwarded to the provider's ``from_env`` constructor so
    tests can inject an http client or clock.
    """
    name = (forge or _detect_forge(repo_ref) or "github").lower()
    if name == "github":
        return GitHubClient.from_env(**kwargs)
    if name == "forgejo":
        return ForgejoClient.from_env(**kwargs)
    if name == "gitlab":
        return GitLabClient.from_env(**kwargs)
    available = ", ".join(SUPPORTED_FORGES)
    raise UnsupportedForgeError(
        f"unsupported forge {name!r}; available providers: {available}"
    )


def _self_hosted_host(env_var: str) -> str | None:
    """The host of a configured self-hosted base URL in ``env_var``, if any."""
    url = os.environ.get(env_var)
    if not url:
        return None
    return (urlparse(url).hostname or "").lower() or None


def _detect_forge(repo_ref: str | None) -> str | None:
    """Best-effort host detection. Returns None for a bare ``owner/repo``."""
    if not repo_ref:
        return None
    ref = repo_ref.lower()
    if "github.com" in ref:
        return "github"
    if "codeberg.org" in ref:
        return "forgejo"
    if "gitlab.com" in ref:
        return "gitlab"
    forgejo_host = _self_hosted_host("GITSWEEPER_FORGEJO_URL")
    if forgejo_host and forgejo_host in ref:
        return "forgejo"
    gitlab_host = _self_hosted_host("GITSWEEPER_GITLAB_URL")
    if gitlab_host and gitlab_host in ref:
        return "gitlab"
    # A bare owner/repo carries no host; fall through to the GitHub default.
    return None
