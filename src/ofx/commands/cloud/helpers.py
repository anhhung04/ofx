"""Shared helpers for cloud CLI commands."""

from collections.abc import Callable

from ofx.cloud.base import CloudProvider
from ofx.commands.ui_helpers import error_exit


def resolve_provider(profile: str = "", provider: str = "") -> str:
    """Resolve a cloud provider name from a profile or explicit --provider flag.

    Exits with code 1 if no provider can be determined.
    """
    from ofx.cloud.config import get_cloud_profile_manager
    if profile:
        mgr = get_cloud_profile_manager()
        try:
            data = mgr.get_profile_data(profile)
        except KeyError:
            error_exit("Cloud profile not found", f"Profile '{profile}' not found.")
        provider = data.get("provider", provider)

    if not provider:
        error_exit("Missing cloud provider", "Specify --provider or --profile.")

    return provider


def create_cloud_provider(profile: str = "", provider: str = "") -> tuple[str, CloudProvider]:
    """Resolve and initialize a cloud provider client."""
    provider_name = resolve_provider(profile, provider)
    from ofx.cloud import CloudProviderRegistry

    try:
        cloud = CloudProviderRegistry.create(provider_name)
    except Exception as exc:
        error_exit(
            "Cloud provider error",
            f"Failed to initialize provider '{provider_name}'.",
            details=str(exc),
        )
    return provider_name, cloud


def run_cloud_sync[T](operation: str, fn: Callable[[], T]) -> T:
    """Run a sync cloud operation with consistent CLI error handling."""
    try:
        return fn()
    except Exception as exc:
        error_exit(
            f"{operation} failed",
            f"Failed to {operation.lower()}.",
            details=str(exc),
        )
