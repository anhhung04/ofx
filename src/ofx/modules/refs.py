"""Parsing namespaced module references.

A module spec has the form::

    <owner>.<repo>.<module>[@<ref>][::<func>]

See ``docs/guide/jobs-steps/steps.md`` for the full reference table.
"""

from __future__ import annotations

from dataclasses import dataclass

BUILTIN_KIND = "builtin"
TOOL_KIND = "tool"
LOCAL_FILE_KIND = "local_file"
LOCAL_NAMED_KIND = "local_named"
REMOTE_KIND = "remote"
LIB_KIND = "lib"

BUILTIN_PREFIX = "builtin."
LOCAL_PREFIX = "local."
LOCAL_MODULES_SUBDIR = "modules"

REMOTE_SCHEME_HINT = (
    "Remote modules reference GitHub repos as "
    "'<owner>.<repo>.<module>[@<ref>][::<func>]', e.g. "
    "'anhhung04.ofx-modules.parse_nmap'."
)


@dataclass(frozen=True, slots=True)
class ModuleRef:
    """A parsed module reference.

    Attributes:
        kind: One of ``builtin``, ``local_file``, ``local_named``, ``remote``,
            ``api``.
        raw: The original (stripped) spec string.
        name: Builtin name (``builtin``), module directory name
            (``local_named``), or manifest module key (``remote``).
        owner/repo: GitHub owner and repository for ``remote`` refs.
        module: Manifest module key for ``remote`` refs.
        ref: Optional git tag/branch/commit for ``remote`` refs.
        function: Optional entry function name (``::<func>`` suffix).
        file: File path portion of a ``local_file`` UDF spec.
        api_path: Dotted path under ``ofx.lib`` for ``api`` refs (the function
            is the last segment of the path).
    """

    kind: str
    raw: str
    name: str | None = None
    owner: str | None = None
    repo: str | None = None
    module: str | None = None
    ref: str | None = None
    function: str | None = None
    file: str | None = None
    api_path: str | None = None

    @property
    def display(self) -> str:
        """Human-readable label (``owner.repo.module@ref::func``) for messages."""
        if self.kind != REMOTE_KIND:
            return self.raw
        label = f"{self.owner}.{self.repo}.{self.module}"
        if self.ref:
            label = f"{label}@{self.ref}"
        if self.function:
            label = f"{label}::{self.function}"
        return label

    @property
    def cache_key(self) -> str:
        """Cache directory name for the cloned repo (``<repo>[@<ref>]``)."""
        return f"{self.repo}@{self.ref}" if self.ref else str(self.repo)

    @property
    def clone_url(self) -> str:
        """HTTPS clone URL for the referenced GitHub repo."""
        return f"https://github.com/{self.owner}/{self.repo}"


def _split_function(raw: str) -> tuple[str, str | None]:
    """Split ``spec`` into ``(base, function)`` on the single ``::``."""
    if "::" not in raw:
        return raw, None
    base, _, function = raw.partition("::")
    if not function:
        raise ValueError(
            f"Invalid module reference '{raw}': missing function after '::' "
            "(use '<spec>::<func>')"
        )
    if "::" in function:
        raise ValueError(
            f"Invalid module reference '{raw}': '::' may appear at most once"
        )
    return base, function


def _split_ref(base: str, raw: str) -> tuple[str, str | None]:
    """Split ``base`` into ``(name, ref)`` on the single ``@``."""
    if "@" not in base:
        return base, None
    name, _, ref = base.partition("@")
    if not name:
        raise ValueError(
            f"Invalid module reference '{raw}': missing module before '@'"
        )
    if not ref:
        raise ValueError(
            f"Invalid module reference '{raw}': missing ref after '@' "
            "(use '<owner>.<repo>.<module>@<tag|branch|commit>')"
        )
    if "@" in ref:
        raise ValueError(
            f"Invalid module reference '{raw}': '@' may appear at most once"
        )
    return name, ref


def _reject_ref(kind: str, ref: str | None, raw: str) -> None:
    if ref is not None:
        scheme = (
            "<owner>.<repo>.<module>@<ref>"
            if kind != LOCAL_FILE_KIND
            else "<path>.py"
        )
        raise ValueError(
            f"Unknown module reference '{raw}': '@<ref>' is only valid on "
            f"remote modules ('<owner>.<repo>.<module>@<ref>'), not on "
            f"'{kind}' specs (expected '{scheme}')"
        )


def _reject_function(kind: str, function: str | None, raw: str) -> None:
    if function is not None:
        raise ValueError(
            f"Invalid module reference '{raw}': '{kind}' modules do not take "
            "a '::<func>' suffix (only UDF files, 'local.<name>' and "
            "'<owner>.<repo>.<module>' specs do)"
        )


def parse_module_ref(spec: str) -> ModuleRef:
    """Parse a module spec into a :class:`ModuleRef`.

    Parsing order (per the design contract):

    1. ``::`` splits off the entry function first.
    2. ``@`` splits off a remote git ref.
    3. ``.py``-suffixed specs are workflow-local UDF files.
    4. ``local.builtin.*`` / ``builtin.*`` / bare names are builtins;
       an unregistered dotted builtin name is an ``ofx.lib`` function path
       (resolved by the registry, not here).
    5. ``local.api.*`` is rejected (removed — use ``local.builtin.<path>.<func>``).
    6. ``local.<name>`` is a workflow-local named module.
    7. Three-or-more dotted segments are remote GitHub modules.

    Raises:
        ValueError: If the spec is empty or malformed.
    """
    raw = spec.strip()
    if not raw:
        raise ValueError("Module name cannot be empty")
    base, function = _split_function(raw)
    base, ref = _split_ref(base, raw)

    if base.endswith(".py"):
        _reject_ref(LOCAL_FILE_KIND, ref, raw)
        return ModuleRef(
            kind=LOCAL_FILE_KIND,
            raw=raw,
            file=base,
            function=function,
        )

    for prefix in ("local.builtin.", "builtin."):
        if base.startswith(prefix) or (prefix == "local.builtin." and base == "local.builtin"):
            _reject_ref(BUILTIN_KIND, ref, raw)
            _reject_function(BUILTIN_KIND, function, raw)
            name = base[len(prefix) :]
            if not name or any(not segment for segment in name.split(".")):
                raise ValueError(
                    f"Invalid module reference '{raw}': malformed builtin name "
                    f"after '{prefix}' (expected 'local.builtin.<name>' or "
                    "'local.builtin.<path>.<func>')"
                )
            return ModuleRef(kind=BUILTIN_KIND, raw=raw, name=name)

    if base == "local.api" or base.startswith("local.api."):
        raise ValueError(
            f"Invalid module reference '{raw}': 'local.api.*' was removed — "
            "ofx.lib functions now resolve under the builtin namespace: "
            "'local.builtin.<path>.<func>' (e.g. "
            "'local.builtin.recon.targets.split_targets')"
        )

    if base.startswith("local.tool.") or base == "local.tool":
        _reject_ref(TOOL_KIND, ref, raw)
        _reject_function(TOOL_KIND, function, raw)
        name = base[len("local.tool") :].lstrip(".")
        if not name or any(not segment for segment in name.split(".")):
            raise ValueError(
                f"Invalid module reference '{raw}': missing tool name after "
                "'local.tool.' (expected 'local.tool.<name>', e.g. "
                "'local.tool.dalfox')"
            )
        return ModuleRef(kind=TOOL_KIND, raw=raw, name=name)

    if base.startswith("local."):
        _reject_ref(LOCAL_NAMED_KIND, ref, raw)
        name = base[len("local.") :]
        if not name:
            raise ValueError(
                f"Invalid module reference '{raw}': missing name after 'local.'"
            )
        if "." in name:
            raise ValueError(
                f"Unknown module reference '{raw}': expected 'local.<name>' "
                "(one segment after 'local.'), 'local.builtin.<name>', or "
                f"'<owner>.<repo>.<module>[@<ref>][::<func>]'. {REMOTE_SCHEME_HINT}"
            )
        return ModuleRef(
            kind=LOCAL_NAMED_KIND,
            raw=raw,
            name=name,
            function=function,
        )

    if "." in base:
        parts = base.split(".")
        if len(parts) < 3 or any(not part for part in parts):
            raise ValueError(
                f"Unknown module reference '{raw}': expected "
                "'<path>.py[::<function>]', 'local.<name>', 'builtin.<name>', "
                "or '<owner>.<repo>.<module>[@<ref>][::<func>]'. "
                f"{REMOTE_SCHEME_HINT}"
            )
        owner, repo, module = parts[0], parts[1], ".".join(parts[2:])
        return ModuleRef(
            kind=REMOTE_KIND,
            raw=raw,
            owner=owner,
            repo=repo,
            module=module,
            ref=ref,
            function=function,
        )

    _reject_ref(BUILTIN_KIND, ref, raw)
    _reject_function(BUILTIN_KIND, function, raw)
    return ModuleRef(kind=BUILTIN_KIND, raw=raw, name=base)


def parse_remote_repo(spec: str) -> ModuleRef:
    """Parse an ``<owner>.<repo>[@<ref>]`` repo spec (no module segment).

    Used by ``ofx flow modules add/update/remove``, which operate on whole
    cached clones rather than individual manifest modules.
    """
    raw = spec.strip()
    if not raw:
        raise ValueError("Invalid module repo: cannot be empty")
    base, ref = _split_ref(raw, raw)
    parts = base.split(".")
    if len(parts) != 2 or any(not part for part in parts):
        raise ValueError(
            f"Invalid module repo '{raw}': expected '<owner>.<repo>[@<ref>]'. "
            f"{REMOTE_SCHEME_HINT}"
        )
    return ModuleRef(
        kind=REMOTE_KIND,
        raw=raw,
        owner=parts[0],
        repo=parts[1],
        module="",
        ref=ref,
    )


__all__ = [
    "LIB_KIND",
    "BUILTIN_KIND",
    "BUILTIN_PREFIX",
    "LOCAL_FILE_KIND",
    "LOCAL_MODULES_SUBDIR",
    "LOCAL_NAMED_KIND",
    "LOCAL_PREFIX",
    "REMOTE_KIND",
    "REMOTE_SCHEME_HINT",
    "TOOL_KIND",
    "ModuleRef",
    "parse_module_ref",
    "parse_remote_repo",
]
