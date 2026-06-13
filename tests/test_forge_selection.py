"""Forge selection: override, host detection, and the GitHub default."""

from __future__ import annotations

import pytest

from gitsweeper.lib.forge import (
    SUPPORTED_FORGES,
    GitHubClient,
    UnsupportedForgeError,
    get_forge_provider,
)


def test_bare_owner_repo_defaults_to_github() -> None:
    provider = get_forge_provider("ConductionNL/openregister")
    assert isinstance(provider, GitHubClient)
    provider.close()


def test_no_ref_defaults_to_github() -> None:
    provider = get_forge_provider()
    assert isinstance(provider, GitHubClient)
    provider.close()


def test_explicit_forge_github_overrides() -> None:
    provider = get_forge_provider("ConductionNL/openregister", forge="github")
    assert isinstance(provider, GitHubClient)
    provider.close()


def test_github_host_url_detected() -> None:
    provider = get_forge_provider("https://github.com/ConductionNL/openregister")
    assert isinstance(provider, GitHubClient)
    provider.close()


def test_unsupported_forge_is_named_not_guessed() -> None:
    with pytest.raises(UnsupportedForgeError) as excinfo:
        get_forge_provider("ConductionNL/openregister", forge="gitlab")
    message = str(excinfo.value)
    assert "gitlab" in message
    # the error lists what *is* available rather than silently using GitHub
    assert all(name in message for name in SUPPORTED_FORGES)
