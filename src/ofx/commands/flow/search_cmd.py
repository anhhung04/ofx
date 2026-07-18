"""Handler for `ofx flow search` — search workflows by keyword, name, or tag."""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.table import Table

from ofx.collections import CollectionManager
from ofx.commands.ui_helpers import print_warning
from ofx.settings import (
    ALLOWED_WORKFLOW_FILE_EXTENSIONS,
    BUILTIN_WORKFLOWS_DIR,
    get_console,
)

def show_search(
    *,
    query: str = "",
    filter_tags: set[str] | None = None,
    show_tags: bool = False,
) -> None:
    """Search workflows across all sources and display matching results."""
    if filter_tags is None:
        filter_tags = set()

    search_term = query.lower().strip()
    console = get_console()

    sources: list[tuple[Path, str]] = []
    if BUILTIN_WORKFLOWS_DIR.is_dir():
        sources.append((BUILTIN_WORKFLOWS_DIR, "builtin"))

    user_dir = Path.home() / ".ofx" / "workflows"
    if user_dir.is_dir():
        sources.append((user_dir, "user"))

    manager = CollectionManager()
    for cname, entry in manager.list_installed().items():
        cpath = Path(entry.path)
        if cpath.is_dir():
            sources.append((cpath, f"collection:{cname}"))

    results: list[dict] = []
    seen: set[str] = set()

    for root, source in sources:
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for path in sorted(root.rglob(f"*{ext}")):
                if path.name in ("collection.yaml", "collection.yml"):
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)

                try:
                    data = yaml.safe_load(path.read_text())
                    if not isinstance(data, dict):
                        continue
                except Exception:
                    continue

                name = str(data.get("name", path.stem))
                desc = str(data.get("description", "")).strip()
                tags_list = [str(t).lower() for t in data.get("tags") or [] if t]

                if filter_tags and not filter_tags.intersection(tags_list):
                    continue

                if search_term:
                    searchable = (
                        f"{path.stem} {name} {desc} {' '.join(tags_list)}".lower()
                    )
                    if search_term not in searchable:
                        continue

                try:
                    category = str(path.relative_to(root).parent)
                    if category == ".":
                        category = ""
                except ValueError:
                    category = ""

                results.append(
                    {
                        "name": path.stem,
                        "category": category,
                        "description": desc.split("\n")[0][:80] if desc else "",
                        "tags": tags_list,
                        "source": source,
                    }
                )

    if not results:
        if search_term and filter_tags:
            print_warning(
                "No Results",
                f"No workflows matched '{search_term}' with tags: {', '.join(sorted(filter_tags))}",
            )
        elif search_term:
            print_warning("No Results", f"No workflows matched '{search_term}'")
        else:
            print_warning(
                "No Results",
                f"No workflows matched tags: {', '.join(sorted(filter_tags))}",
            )
        return

    table = Table(
        title=f"Search Results ({len(results)})", show_lines=False, padding=(0, 1)
    )
    table.add_column("Workflow", style="cyan bold", no_wrap=True)
    table.add_column("Description", style="white")
    if show_tags:
        table.add_column("Tags", style="dim")
    table.add_column("Source", style="dim", no_wrap=True)

    for r in sorted(results, key=lambda x: (x["source"], x["category"], x["name"])):
        wf_name = f"{r['category']}/{r['name']}" if r["category"] else r["name"]
        row = [wf_name, r["description"]]
        if show_tags:
            row.append(", ".join(r["tags"]) if r["tags"] else "")
        row.append(r["source"])
        table.add_row(*row)

    console.print(table)
