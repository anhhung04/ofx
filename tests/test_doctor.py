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

    def test_doctor_fleet_digitalocean_profile_reports_token_configured(
        self, monkeypatch, tmp_path
    ):
        from ofx.cloud.config import CloudProfileManager

        mgr = CloudProfileManager(config_path=tmp_path / "cloud.yml")
        mgr.add(
            "do",
            {
                "provider": "digitalocean",
                "host": "127.0.0.1",
                "token": "dop_token",
            },
        )
        mgr.set_default("do")
        monkeypatch.setattr(
            "ofx.cloud.config.get_cloud_profile_manager",
            lambda: mgr,
        )

        result = runner.invoke(app, ["doctor", "fleet"])

        assert result.exit_code == 0
        assert "DigitalOcean token" in result.output
        assert "Configured" in result.output

    def test_doctor_fleet_unknown_status_uses_plain_style(self, monkeypatch, tmp_path):
        import importlib

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
        doctor_module = importlib.import_module("ofx.commands.doctor.app")
        monkeypatch.setattr(
            doctor_module,
            "_score_fleet_config",
            lambda *_args, **_kwargs: [doctor_module.CheckResult("Odd Check", "mystery", "detail")],
        )

        result = runner.invoke(app, ["doctor", "fleet"])

        assert result.exit_code == 0
        assert "MYSTERY" in result.output
