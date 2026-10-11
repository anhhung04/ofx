"""Module registry: resolve module specs to callables."""

from __future__ import annotations

from pathlib import Path

from ofx.modules.api import resolve_api_callable
from ofx.modules.base import ModuleSpec
from ofx.modules.builtins import BUILTIN_MODULES
from ofx.modules.refs import (
    API_KIND,
    BUILTIN_KIND,
    LOCAL_FILE_KIND,
    LOCAL_NAMED_KIND,
    REMOTE_KIND,
    REMOTE_SCHEME_HINT,
    parse_module_ref,
)
from ofx.modules.remote import ensure_remote_module
from ofx.modules.udf import DEFAULT_UDF_FUNCTION, load_module_file, load_udf_spec

BUILTIN_PREFIX = "builtin."

LOCAL_MODULES_SUBDIR = "modules"


class ModuleRegistry:
    """Resolve module specs to concrete :class:`ModuleSpec` values.

    Supported spec forms:

    - ``shell`` / ``builtin.shell`` / ``local.builtin.shell`` — builtin module
    - ``<path>.py[::<func>]`` — workflow-local UDF file
    - ``local.<name>[::<func>]`` — workflow-local ``modules/<name>.py``
    - ``local.api.<path>.<func>`` — ``ofx.api`` function (kwargs-style; the
      last path segment names the function)
    - ``<owner>.<repo>.<module>[@<ref>][::<func>]`` — remote GitHub module
      (UDF or, for manifest ``api:`` entries, an ``ofx.api`` function)

    Relative UDF paths resolve against the registry's ``workflow_dir`` (if
    given) and then the current working directory.
    """

    def __init__(self, workflow_dir: Path | None = None) -> None:
        self._workflow_dir = workflow_dir
        self._builtins: dict[str, ModuleSpec] = {
            module.name: ModuleSpec(
                kind="builtin",
                name=module.name,
                description=module.description,
                args_schema=module.args_schema,
                callable=module.run,
            )
            for module in BUILTIN_MODULES
        }

    @property
    def builtin_names(self) -> tuple[str, ...]:
        """Names of the available builtin modules, sorted."""
        return tuple(sorted(self._builtins))

    def _base_dir(self, workflow_dir: Path | None) -> Path | None:
        return workflow_dir if workflow_dir is not None else self._workflow_dir

    def resolve(self, spec: str, *, workflow_dir: Path | None = None) -> ModuleSpec:
        """Resolve a module spec to a concrete :class:`ModuleSpec`."""
        try:
            ref = parse_module_ref(spec)
        except ValueError as exc:
            available = ", ".join(self.builtin_names)
            raise ValueError(
                f"{exc} Available builtin modules: {available}."
            ) from None

        if ref.kind == BUILTIN_KIND:
            builtin = self._builtins.get(ref.name or "")
            if builtin is None:
                available = ", ".join(self.builtin_names)
                raise ValueError(
                    f"Unknown module: '{spec}'. Available builtin modules: "
                    f"{available}. {REMOTE_SCHEME_HINT}"
                )
            return builtin

        if ref.kind == API_KIND:
            return ModuleSpec(
                kind=API_KIND,
                name=ref.raw,
                callable=resolve_api_callable(ref.api_path or ""),
                function=ref.function,
            )

        if ref.kind == LOCAL_FILE_KIND:
            return load_udf_spec(ref.raw, self._base_dir(workflow_dir))

        if ref.kind == LOCAL_NAMED_KIND:
            path = self.resolve_local_named_path(
                ref.name or "", workflow_dir=workflow_dir
            )
            if not path.is_file():
                raise FileNotFoundError(
                    f"Local module '{ref.raw}' not found: '{path}' (expected "
                    f"<workflow_dir>/{LOCAL_MODULES_SUBDIR}/{ref.name}.py)"
                )
            return load_module_file(
                path, ref.function or DEFAULT_UDF_FUNCTION, name=ref.raw
            )

        if ref.kind == REMOTE_KIND:
            entry = ensure_remote_module(ref, workflow_dir=workflow_dir)
            if entry.api_path is not None:
                return ModuleSpec(
                    kind=API_KIND,
                    name=ref.raw,
                    callable=resolve_api_callable(entry.api_path),
                    function=entry.function,
                )
            return load_module_file(entry.file, entry.function, name=ref.raw)

        raise ValueError(  # pragma: no cover - defensive
            f"Unknown module reference kind '{ref.kind}' for spec '{spec}'"
        )

    def resolve_local_named_path(
        self, name: str, *, workflow_dir: Path | None = None
    ) -> Path:
        """Return ``<workflow_dir>/modules/<name>.py`` for a ``local.<name>`` ref."""
        base_dir = self._base_dir(workflow_dir)
        root = base_dir if base_dir is not None else Path.cwd()
        return root / LOCAL_MODULES_SUBDIR / f"{name}.py"


__all__ = ["BUILTIN_PREFIX", "LOCAL_MODULES_SUBDIR", "ModuleRegistry"]
