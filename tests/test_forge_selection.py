"""Forge selection: override, host detection, and the GitHub default."""

from __future__ import annotations

import pytest

from gitsweeper.lib.forge import (
    SUPPORTED_FORGES,
    ForgejoClient,
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


def test_explicit_forge_forgejo_overrides() -> None:
    provider = get_forge_provider("o/r", forge="forgejo")
    assert isinstance(provider, ForgejoClient)
    provider.close()


def test_codeberg_host_detected_as_forgejo() -> None:
    provider = get_forge_provider("https://codeberg.org/forgejo/forgejo")
    assert isinstance(provider, ForgejoClient)
    provider.close()


def test_self_hosted_forgejo_host_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITSWEEPER_FORGEJO_URL", "https://git.example.org")
    provider = get_forge_provider("https://git.example.org/team/project")
    assert isinstance(provider, ForgejoClient)
    provider.close()


def test_bare_owner_repo_still_github_even_with_forgejo_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A configured self-hosted host must not hijack a bare owner/repo.
    monkeypatch.setenv("GITSWEEPER_FORGEJO_URL", "https://git.example.org")
    provider = get_forge_provider("ConductionNL/openregister")
    assert isinstance(provider, GitHubClient)
    provider.close()


def test_unsupported_forge_is_named_not_guessed() -> None:
    with pytest.raises(UnsupportedForgeError) as excinfo:
        get_forge_provider("ConductionNL/openregister", forge="gitlab")
    message = str(excinfo.value)
    assert "gitlab" in message
    # the error lists what *is* available rather than silently using GitHub
    assert all(name in message for name in SUPPORTED_FORGES)
