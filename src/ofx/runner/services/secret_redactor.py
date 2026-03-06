"""Utility for registering secret values with the log redaction filter.

The existing code in ``CloudJobRunner`` performs secret collection and calls
``SecretRedactFilter.get_instance().register_values`` directly.  This logic is
extracted into a small service so that other components can reuse it without
duplicating the import and iteration boilerplate.
"""

from __future__ import annotations

from typing import Iterable, Set


class SecretRedactor:
    """Collects secret values and registers them with ``SecretRedactFilter``.

    The service is deliberately lightweight – it does not store state beyond the
    registration call.  It can be injected where needed (e.g. in cloud runners) to
    keep the runner classes focused on orchestration.
    """

    @staticmethod
    def register(values: Iterable[str]) -> None:
        """Register a collection of secret strings with the global filter.

        ``values`` may contain ``None`` entries; they are ignored.
        """
        # Import locally to avoid pulling the heavy filter module during normal
        # startup when redaction is not required.
        from ofx.utils.log import SecretRedactFilter

        secret_set: Set[str] = {v for v in values if v}
        if secret_set:
            SecretRedactFilter.get_instance().register_values(secret_set)
