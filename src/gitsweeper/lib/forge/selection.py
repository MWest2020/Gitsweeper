"""Resolve a repository reference (and an optional override) to a provider.

Order of resolution: an explicit ``forge`` override wins; otherwise the host
of a fully-qualified reference is consulted (``github.com`` -> GitHub,
``codeberg.org`` or a configured self-hosted Forgejo host -> Forgejo);
otherwise a bare ``owner/repo`` defaults to GitHub. An unsupported forge is
rejected by name rather than silently falling back to GitHub.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from gitsweeper.lib.forge.base import ForgeProvider
from gitsweeper.lib.forge.forgejo import ForgejoClient
from gitsweeper.lib.forge.github import GitHubClient

#: Forges with a concrete provider today. GitLab is a named follow-on change;
#: its host will register here when it lands.
SUPPORTED_FORGES: tuple[str, ...] = ("github", "forgejo")


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
    available = ", ".join(SUPPORTED_FORGES)
    raise UnsupportedForgeError(
        f"unsupported forge {name!r}; available providers: {available}"
    )


def _self_hosted_forgejo_host() -> str | None:
    """The host of a configured self-hosted Forgejo base URL, if any."""
    url = os.environ.get("GITSWEEPER_FORGEJO_URL")
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
    self_hosted = _self_hosted_forgejo_host()
    if self_hosted and self_hosted in ref:
        return "forgejo"
    # A bare owner/repo carries no host; fall through to the GitHub default.
    return None
