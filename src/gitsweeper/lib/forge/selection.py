"""Resolve a repository reference (and an optional override) to a provider.

Order of resolution: an explicit ``forge`` override wins; otherwise the host
of a fully-qualified reference is consulted; otherwise a bare ``owner/repo``
defaults to GitHub. An unsupported forge is rejected by name rather than
silently falling back to GitHub.
"""

from __future__ import annotations

from typing import Any

from gitsweeper.lib.forge.base import ForgeProvider
from gitsweeper.lib.forge.github import GitHubClient

#: Forges with a concrete provider today. Forgejo/Codeberg and GitLab are
#: named follow-on changes; their hosts will register here when they land.
SUPPORTED_FORGES: tuple[str, ...] = ("github",)


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
    if name != "github":
        available = ", ".join(SUPPORTED_FORGES)
        raise UnsupportedForgeError(
            f"unsupported forge {name!r}; available providers: {available}"
        )
    return GitHubClient.from_env(**kwargs)


def _detect_forge(repo_ref: str | None) -> str | None:
    """Best-effort host detection. Returns None for a bare ``owner/repo``."""
    if not repo_ref:
        return None
    if "github.com" in repo_ref.lower():
        return "github"
    # A non-GitHub host can't be matched until its provider registers; a bare
    # owner/repo carries no host. Both fall through to the GitHub default.
    return None
