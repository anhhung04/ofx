"""Shared helpers for cloud CLI commands."""

from collections.abc import Callable

import typer

from ofx.cloud.base import CloudProvider
from ofx.commands.ui_helpers import print_error


def resolve_provider(profile: str = "", provider: str = "") -> str:
    """Resolve a cloud provider name from a profile or explicit --provider flag.

    Exits with code 1 if no provider can be determined.
    """
    from ofx.cloud.config import get_cloud_profile_manager
    if profile:
        mgr = get_cloud_profile_manager()
        try:
            data = mgr.get_profile_data(profile)
        except KeyError as exc:
            print_error("Cloud profile not found", f"Profile '{profile}' not found.")
            raise typer.Exit(code=1) from exc
        provider = data.get("provider", provider)

    if not provider:
        print_error("Missing cloud provider", "Specify --provider or --profile.")
        raise typer.Exit(code=1)

    return provider


def create_cloud_provider(profile: str = "", provider: str = "") -> tuple[str, CloudProvider]:
    """Resolve and initialize a cloud provider client."""
    provider_name = resolve_provider(profile, provider)
    from ofx.cloud import CloudProviderRegistry

    try:
        cloud = CloudProviderRegistry.create(provider_name)
    except Exception as exc:
        print_error(
            "Cloud provider error",
            f"Failed to initialize provider '{provider_name}'.",
            details=str(exc),
        )
        raise typer.Exit(code=1) from exc
    return provider_name, cloud


def run_cloud_sync[T](operation: str, fn: Callable[[], T]) -> T:
    """Run a sync cloud operation with consistent CLI error handling."""
    try:
        return fn()
    except Exception as exc:
        print_error(
            f"{operation} failed",
            f"Failed to {operation.lower()}.",
            details=str(exc),
        )
        raise typer.Exit(code=1) from exc
