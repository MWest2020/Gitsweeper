"""Forge access: the provider seam analysis capabilities acquire data through.

Providers (GitHub, Forgejo/Gitea/Codeberg, and GitLab today) map their native
JSON onto the normalized model in :mod:`gitsweeper.lib.forge.base` — frozen
dataclasses with uniform merge semantics, UTC-``Z`` timestamps, and a retained
raw payload — so the analysis capabilities never name a concrete forge.
"""

from gitsweeper.lib.forge.base import (
    ForgeComment,
    ForgeCommit,
    ForgeIssueEvent,
    ForgeProvider,
    ForgePullRequest,
    ForgeRepo,
)
from gitsweeper.lib.forge.forgejo import ForgejoClient, ForgejoError
from gitsweeper.lib.forge.github import GitHubClient, GitHubError
from gitsweeper.lib.forge.gitlab import GitLabClient, GitLabError
from gitsweeper.lib.forge.selection import (
    SUPPORTED_FORGES,
    UnsupportedForgeError,
    get_forge_provider,
)

__all__ = [
    "SUPPORTED_FORGES",
    "ForgeComment",
    "ForgeCommit",
    "ForgeIssueEvent",
    "ForgeProvider",
    "ForgePullRequest",
    "ForgeRepo",
    "ForgejoClient",
    "ForgejoError",
    "GitHubClient",
    "GitHubError",
    "GitLabClient",
    "GitLabError",
    "UnsupportedForgeError",
    "get_forge_provider",
]
