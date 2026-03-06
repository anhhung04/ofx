"""Template resolution service used by runners.

This service encapsulates the heavy Jinja2 ``TemplateResolver`` import and
provides a thin async API for resolving values within a given context.  It is
intended to be injected into ``BaseRunner`` (or its subclasses) so that the
resolver can be mocked in tests and the import is performed lazily.
"""

from __future__ import annotations

from typing import Any, Dict

# The actual resolver is imported lazily inside the class to avoid import‑time
# overhead for code paths that never render templates.


class TemplateService:
    """Thin wrapper around :class:`ofx.runner.templates.resolver.TemplateResolver`.

    The public ``resolve`` method mirrors the ``BaseRunner._resolve_template``
    behaviour – it receives a value (which may be a string, dict, list, etc.) and
    a dictionary of variables that are made available to the template engine.
    """

    def __init__(self) -> None:
        # Delay heavy import until first use.
        self._resolver = None

    def _ensure_resolver(self) -> None:
        if self._resolver is None:
            from ofx.runner.templates.resolver import TemplateResolver

            self._resolver = TemplateResolver()

    async def resolve(self, value: Any, context_vars: Dict[str, Any]) -> Any:
        """Resolve ``value`` as a Jinja2 template using ``context_vars``.

        ``value`` can be any JSON‑serialisable structure.  The underlying
        ``TemplateResolver`` handles the recursion for complex containers.
        """
        self._ensure_resolver()
        # ``TemplateResolver.resolve`` is async, so we await it directly.
        return await self._resolver.resolve(value, context_vars)

    # Helper used by ``BaseRunner._resolve_template_fields`` – resolves a list of
    # model attribute names in parallel.  The implementation mirrors the original
    # logic but delegates to ``resolve`` for each field.
    async def resolve_fields(self, runner, fields: list[str]) -> bool:
        """Resolve a sequence of model fields on ``runner``.

        Returns ``True`` if any field was resolved, otherwise ``False``.
        """
        if not fields:
            return False
        tasks = []
        target_fields = []
        for field in fields:
            if hasattr(runner.model, field):
                tasks.append(
                    runner._resolve_template(getattr(runner.model, field))
                )
                target_fields.append(field)
        if not tasks:
            return False
        results = await runner._resolve_template_concurrent(tasks)
        for field, resolved in zip(target_fields, results, strict=True):
            setattr(runner.model, field, resolved)
        return True
