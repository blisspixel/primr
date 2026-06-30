"""Unit tests for tracked-company CLI handling."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import CLIConfig, Command, _handle_company


def _config(**overrides):
    defaults = {"command": Command.COMPANY}
    defaults.update(overrides)
    return CLIConfig(**defaults)


class TestCompanyList:
    def test_returns_0_with_empty_store(self, monkeypatch):
        store = MagicMock()
        store.list_profiles.return_value = []
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        assert _handle_company(_config(company_profile_list=True)) == 0

    def test_lists_profiles(self, monkeypatch):
        profile = MagicMock()
        profile.name = "Acme Corp"
        profile.url = "https://acme.example"
        profile.freshness_status = "unrun"
        profile.last_run_at = None
        store = MagicMock()
        store.list_profiles.return_value = [profile]
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        assert _handle_company(_config(company_profile_list=True)) == 0
        store.list_profiles.assert_called_once()


class TestCompanyTrack:
    def test_requires_url(self, monkeypatch):
        store = MagicMock()
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        result = _handle_company(_config(company_profile_track="Acme Corp"))

        assert result == 1
        store.track.assert_not_called()

    def test_tracks_profile(self, monkeypatch):
        profile = MagicMock()
        profile.name = "Acme Corp"
        profile.url = "https://acme.example"
        profile.freshness_status = "unrun"
        store = MagicMock()
        store.track.return_value = profile
        store.profile_dir.return_value = "profiles/acme"
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        result = _handle_company(
            _config(
                company_profile_track="Acme Corp",
                company_profile_url="https://acme.example",
            )
        )

        assert result == 0
        store.track.assert_called_once_with("Acme Corp", "https://acme.example")


class TestCompanyShow:
    def test_returns_0_when_profile_missing(self, monkeypatch):
        store = MagicMock()
        store.get_profile.return_value = None
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        result = _handle_company(_config(company_profile_show="Acme Corp"))

        assert result == 0
        store.get_profile.assert_called_once_with("Acme Corp")

    def test_shows_profile(self, monkeypatch):
        profile = MagicMock()
        profile.name = "Acme Corp"
        profile.url = "https://acme.example"
        profile.freshness_status = "unrun"
        profile.last_run_at = None
        profile.run_pointers = ()
        profile.retention_policy = "keep_until_cleared"
        store = MagicMock()
        store.get_profile.return_value = profile
        store.profile_dir.return_value = "profiles/acme"
        monkeypatch.setattr(
            "primr.agentic.company_profiles.CompanyProfileStore",
            MagicMock(return_value=store),
        )

        result = _handle_company(_config(company_profile_show="Acme Corp"))

        assert result == 0
        store.get_profile.assert_called_once_with("Acme Corp")
