"""Forge access: the provider seam analysis capabilities acquire data through.

v1 ships GitHub only. See :mod:`gitsweeper.lib.forge.base` for why the
normalized cross-forge model is deferred to the first non-GitHub provider.
"""

from gitsweeper.lib.forge.base import ForgeProvider
from gitsweeper.lib.forge.github import GitHubClient, GitHubError
from gitsweeper.lib.forge.selection import (
    SUPPORTED_FORGES,
    UnsupportedForgeError,
    get_forge_provider,
)

__all__ = [
    "SUPPORTED_FORGES",
    "ForgeProvider",
    "GitHubClient",
    "GitHubError",
    "UnsupportedForgeError",
    "get_forge_provider",
]
