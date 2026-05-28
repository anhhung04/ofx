"""Tests for shared task profile option merging helpers."""

from __future__ import annotations

from ofx.profiles.models import OFXProfile
from ofx.runner.task_profile_options import merge_profile_task_options


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
