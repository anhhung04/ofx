"""Tests for doctor reliability commands."""

from __future__ import annotations

from typer.testing import CliRunner

from ofx.commands.__init__ import _register_commands, app

runner = CliRunner()
_register_commands()


class TestDoctorFleet:
    def test_doctor_fleet_no_default_profile(self, monkeypatch, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        monkeypatch.setattr(
            "ofx.cloud.config.get_cloud_profile_manager",
            lambda: mgr,
        )

        result = runner.invoke(app, ["doctor", "fleet"])
        assert result.exit_code == 1
        assert "No profile specified" in result.output

    def test_doctor_fleet_static_profile_pass(self, monkeypatch, tmp_path):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add(
            "st",
            {"provider": "static", "host": "127.0.0.1", "ssh_key": "~/.ssh/id_rsa"},
        )
        mgr.set_default("st")
        monkeypatch.setattr(
            "ofx.cloud.config.get_cloud_profile_manager",
            lambda: mgr,
        )

        result = runner.invoke(app, ["doctor", "fleet"])
        assert result.exit_code == 0
        assert "Fleet Reliability Scorecard" in result.output
