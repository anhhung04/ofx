"""Handler for `ofx flow list` — list available workflows as a folder tree."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import yaml
from rich.table import Table
from rich.tree import Tree

from ofx.collections import CollectionManager
from ofx.commands.ui_helpers import error_exit, print_warning
from ofx.settings import (
    ALLOWED_WORKFLOW_FILE_EXTENSIONS,
    BUILTIN_WORKFLOWS_DIR,
    get_console,
)

logger = logging.getLogger("ofx")


def _scan_yaml_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
        files.extend(sorted(root.rglob(f"*{ext}")))
    return sorted(set(files))


def _read_metadata(path: Path) -> dict:
    """Read name, description, and tags from a workflow YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            tags = data.get("tags", [])
            return {
                "name": str(data.get("name", path.stem)),
                "description": str(data.get("description", "")),
                "tags": [str(t).lower() for t in tags]
                if isinstance(tags, list)
                else [],
            }
    except Exception as e:
        logger.debug("Failed to parse workflow metadata from %s: %s", path, e)
    return {"name": path.stem, "description": "", "tags": []}


def show_list(
    *,
    builtin: bool = False,
    collection: str = "",
    filter_tags: set[str] | None = None,
    search_term: str = "",
    show_tags: bool = False,
    show_descriptions: bool = False,
    list_tags: bool = False,
) -> None:
    """List available workflows, optionally filtered by source, tag, or search."""
    if filter_tags is None:
        filter_tags = set()

    show_all = not builtin and not collection

    all_files: list[tuple[Path, str, Path]] = []
    seen_paths: set[str] = set()

    def _collect(root: Path, source: str) -> None:
        for file in _scan_yaml_files(root):
            resolved = str(file.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                all_files.append((file, source, root))

    if builtin or show_all:
        if BUILTIN_WORKFLOWS_DIR.is_dir():
            _collect(BUILTIN_WORKFLOWS_DIR, "📦 Built-in")

    if collection or show_all:
        manager = CollectionManager()
        installed = manager.list_installed()

        if collection and collection not in installed:
            error_exit(
                "Collection not found",
                f"'{collection}' is not installed.",
                f"Installed: {', '.join(installed) or '(none)'}",
            )

        targets = {collection: installed[collection]} if collection else installed
        for coll_name, entry in targets.items():
            coll_path = Path(entry.path)
            if not coll_path.is_dir():
                continue
            _collect(coll_path, f"📦 {coll_name}")

    console = get_console()

    # --list-tags mode
    if list_tags:
        tag_counts: dict[str, int] = defaultdict(int)
        for file, _, _ in all_files:
            for t in _read_metadata(file)["tags"]:
                tag_counts[t] += 1

        if not tag_counts:
            print_warning("No Tags Found", "No workflows have tags defined.")
            return

        table = Table(title="Available Tags", show_lines=False, padding=(0, 2))
        table.add_column("Tag", style="cyan bold")
        table.add_column("Workflows", style="white", justify="right")
        for t in sorted(tag_counts, key=lambda x: (-tag_counts[x], x)):
            table.add_row(t, str(tag_counts[t]))
        console.print(table)
        return

    # Read metadata when filtering or showing extra columns
    need_metadata = (
        bool(filter_tags) or bool(search_term) or show_tags or show_descriptions
    )
    file_meta: dict[str, dict] = {}
    if need_metadata:
        for file, _, _ in all_files:
            file_meta[str(file.resolve())] = _read_metadata(file)

    # Build grouped tree: source_label -> {category -> [(name, tags, description)]}
    groups: dict[str, dict[str, list[tuple[str, list[str], str]]]] = {}

    for file, source, base_root in all_files:
        resolved = str(file.resolve())
        meta = file_meta.get(
            resolved, {"name": file.stem, "description": "", "tags": []}
        )
        tags = meta["tags"]
        description = meta["description"]

        if filter_tags and not filter_tags.intersection(tags):
            continue

        if search_term:
            searchable = (
                f"{file.stem} {meta['name']} {description} {' '.join(tags)}".lower()
            )
            if search_term not in searchable:
                continue

        try:
            category = file.relative_to(base_root).parent
            cat_str = str(category) if str(category) != "." else ""
        except ValueError:
            cat_str = ""
        groups.setdefault(source, defaultdict(list))[cat_str].append(
            (file.stem, tags, description)
        )

    if not groups:
        if filter_tags:
            print_warning(
                "No Workflows Found",
                f"No workflows matched tags: {', '.join(sorted(filter_tags))}",
            )
        elif search_term:
            print_warning(
                "No Workflows Found", f"No workflows matched search: '{search_term}'"
            )
        else:
            print_warning("No Workflows Found", "No workflows matched the filter.")
        return

    root = Tree("[bold]Available Workflows[/bold]")

    for source_label in sorted(groups):
        categories = groups[source_label]
        source_branch = root.add(f"[bold magenta]{source_label}[/bold magenta]")
        for cat in sorted(categories):
            if cat:
                cat_branch = source_branch.add(f"[yellow]📁 {cat}[/yellow]")
            else:
                cat_branch = source_branch
            for name, tags, description in sorted(categories[cat]):
                parts = [f"[cyan]{name}[/cyan]"]
                if show_tags and tags:
                    parts.append(" ".join(f"[dim]#{t}[/dim]" for t in tags))
                if (show_descriptions or search_term) and description:
                    desc = description.split("\n")[0][:80]
                    parts.append(f"[dim italic]{desc}[/dim italic]")
                cat_branch.add("  ".join(parts))

    console.print(root)
