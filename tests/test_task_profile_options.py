"""Tests for shared task profile option merging helpers."""

from __future__ import annotations

from ofx.profiles.models import OFXProfile
from ofx.runner.task_profile_options import (
    adapt_task_command_for_profile,
    build_profile_env_overrides,
    build_profile_var_overrides,
    merge_profile_task_options,
    profile_to_dict,
)


def test_merge_profile_task_options_injects_common_declared_opts():
    profile = OFXProfile(proxy="socks5://127.0.0.1:9050", threads=3)

    merged, injected, override_keys = merge_profile_task_options(
        task_name="feroxbuster",
        user_opts={},
        task_declared_opts={"proxy": object(), "threads": object()},
        profile=profile,
    )

    assert merged["proxy"] == "socks5://127.0.0.1:9050"
    assert merged["threads"] == 3
    assert injected == ["proxy=socks5://127.0.0.1:9050", "threads=3"]
    assert override_keys == []


def test_merge_profile_task_options_preserves_user_opts_over_profile():
    profile = OFXProfile(threads=3, task_options={"httpx": {"rate_limit": 20}})

    merged, injected, override_keys = merge_profile_task_options(
        task_name="httpx",
        user_opts={"threads": 10},
        task_declared_opts={"threads": object(), "rate_limit": object()},
        profile=profile,
    )

    assert merged == {"rate_limit": 20, "threads": 10}
    assert injected == []
    assert override_keys == ["rate_limit"]


def test_merge_profile_task_options_applies_task_overrides_without_declared_opts():
    profile = OFXProfile(task_options={"httpx": {"rate_limit": 20}})

    merged, injected, override_keys = merge_profile_task_options(
        task_name="httpx",
        user_opts={"threads": 10},
        task_declared_opts={},
        profile=profile,
    )

    assert merged == {"rate_limit": 20, "threads": 10}
    assert injected == []
    assert override_keys == ["rate_limit"]


def test_merge_profile_task_options_filters_empty_profile_values():
    profile = OFXProfile(proxy="", threads=0, rate_limit=20)

    merged, injected, override_keys = merge_profile_task_options(
        task_name="httpx",
        user_opts={},
        task_declared_opts={"proxy": object(), "threads": object(), "rate_limit": object()},
        profile=profile,
    )

    assert merged == {"rate_limit": 20}
    assert injected == ["rate_limit=20"]
    assert override_keys == []


def test_merge_profile_task_options_prefers_first_available_declared_option():
    profile = OFXProfile(proxy="socks5://127.0.0.1:9050")

    merged, injected, _override_keys = merge_profile_task_options(
        task_name="feroxbuster",
        user_opts={"proxy": "user-set"},
        task_declared_opts={"proxy_url": object(), "proxy": object()},
        profile=profile,
    )

    assert merged == {
        "proxy": "user-set",
        "proxy_url": "socks5://127.0.0.1:9050",
    }
    assert injected == ["proxy_url=socks5://127.0.0.1:9050"]


def test_merge_profile_task_options_keeps_common_values_over_task_overrides():
    profile = OFXProfile(
        threads=3,
        task_options={"httpx": {"threads": 9, "rate_limit": 20}},
    )

    merged, injected, override_keys = merge_profile_task_options(
        task_name="httpx",
        user_opts={},
        task_declared_opts={"threads": object(), "rate_limit": object()},
        profile=profile,
    )

    assert merged == {"threads": 3, "rate_limit": 20}
    assert injected == ["threads=3"]
    assert override_keys == ["threads", "rate_limit"]


def test_adapt_task_command_for_profile_adds_proxy_env_prefix_without_native_proxy_opt():
    profile = OFXProfile(proxy="socks5://127.0.0.1:9050")

    command = adapt_task_command_for_profile(
        "whois example.com",
        task_declared_opts={},
        resolved_opts={},
        profile=profile,
    )

    assert command.startswith("env ")
    assert "HTTP_PROXY=socks5://127.0.0.1:9050" in command
    assert "ALL_PROXY=socks5://127.0.0.1:9050" in command
    assert command.endswith("whois example.com")


def test_adapt_task_command_for_profile_prefers_native_proxy_option_when_present():
    profile = OFXProfile(proxy="socks5://127.0.0.1:9050")

    command = adapt_task_command_for_profile(
        "feroxbuster -p socks5://127.0.0.1:9050 -u http://example.com",
        task_declared_opts={"proxy": object()},
        resolved_opts={"proxy": "socks5://127.0.0.1:9050"},
        profile=profile,
    )

    assert command == "feroxbuster -p socks5://127.0.0.1:9050 -u http://example.com"


def test_build_profile_env_overrides_exports_all_profile_fields():
    profile = OFXProfile(
        name="stealth",
        description="slow and quiet",
        rate_limit=20,
        threads=3,
        delay=1.5,
        jitter=0.5,
        proxy="socks5://127.0.0.1:9050",
        user_agent="agent/1.0",
        env={"EXTRA_ENV": "1"},
        task_options={"httpx": {"rate_limit": 10}},
        tags=["quiet"],
    )

    env = build_profile_env_overrides(profile)

    assert env["OFX_THREADS"] == "3"
    assert env["OFX_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["OFX_PROFILE_NAME"] == "stealth"
    assert env["OFX_PROFILE_DESCRIPTION"] == "slow and quiet"
    assert env["OFX_PROFILE_TASK_OPTIONS"] == '{"httpx": {"rate_limit": 10}}'
    assert env["OFX_PROFILE_TAGS"] == '["quiet"]'
    assert env["OFX_PROFILE_JSON"]
    assert env["HTTP_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["EXTRA_ENV"] == "1"


def test_build_profile_var_overrides_and_profile_to_dict_normalize_profile_data():
    profile = OFXProfile(name="stealth", threads=4)

    vars_update = build_profile_var_overrides(profile)

    assert vars_update["profile_model"] is profile
    assert vars_update["profile"] == profile_to_dict(profile)
    assert vars_update["profile"]["name"] == "stealth"
