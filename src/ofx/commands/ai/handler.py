"""AI command handlers for OFX."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console

from ofx.commands.ui_helpers import (
    error_exit,
    header_panel,
    print_success,
    print_warning,
    status_table,
)
from ofx.settings import get_console

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ai_config(model_override: str | None = None) -> dict:
    """Return resolved AI config dict from settings + env."""
    import os

    from ofx.settings import settings

    ai = settings.ai
    api_key = ai.api_key.get_secret_value() or os.getenv("OPENAI_API_KEY", "")
    return {
        "api_key": api_key,
        "model": model_override or ai.model,
        "temperature": ai.temperature,
        "max_tokens": ai.max_tokens,
        "max_history_tokens": ai.max_history_tokens,
        "base_url": ai.base_url or None,
    }


def _require_deps(cfg: dict) -> None:
    """Ensure the openai SDK is installed and credentials are available."""
    from ofx.ai.client import check_ai_available

    if not check_ai_available():
        error_exit(
            "Missing Dependency",
            "openai package is not installed.",
            "Install with: uv add openai",
        )

    if not cfg["api_key"] and not cfg["base_url"]:
        error_exit(
            "API Key Missing",
            "No API key found and no base_url configured.",
            "Set OFX_AI__API_KEY=sk-... (or OPENAI_API_KEY=sk-...) and retry, "
            "or set OFX_AI__BASE_URL for a local provider (e.g. Ollama). "
            "Run 'ofx ai setup' for configuration help.",
        )


def _prepare(model: str | None = None) -> tuple[dict, Console]:  # noqa: F821
    """Resolve config, check deps, return ``(cfg, console)``."""
    cfg = _ai_config(model)
    _require_deps(cfg)
    return cfg, get_console()


def _stream_to_stdout(cfg: dict, messages: list[dict]) -> str:
    """Stream LLM response to stdout with rich rendering.

    * Shows a spinner while waiting for the first token.
    * **Thinking** tokens stream live in dim italic.
    * **Content** tokens render as live-updating Markdown.

    Only content text is returned (for history / downstream use).
    """
    from rich.columns import Columns
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.spinner import Spinner
    from rich.text import Text

    from ofx.ai.client import call_llm_stream

    console = get_console()
    content_parts: list[str] = []
    thinking_parts: list[str] = []

    stream = call_llm_stream(
        messages=messages,
        model=cfg["model"],
        api_key=cfg["api_key"],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
        base_url=cfg["base_url"],
    )

    # --- Wait for first token with a spinner ----------------------------
    first_chunk = None
    try:
        with Live(
            Columns([Spinner("dots", style="cyan"), Text(" Thinking…", style="dim")]),
            console=console,
            refresh_per_second=12,
            transient=True,
        ):
            try:
                first_chunk = next(stream)
            except StopIteration:
                pass
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        return ""

    if first_chunk is None:
        return ""

    # --- Stream thinking tokens live ------------------------------------
    if first_chunk.kind == "thinking":
        thinking_parts.append(first_chunk.text)
        try:
            with Live(
                Text(f"💭 {''.join(thinking_parts)}", style="dim italic"),
                console=console,
                refresh_per_second=8,
                vertical_overflow="visible",
            ) as live:
                for chunk in stream:
                    if chunk.kind == "thinking":
                        thinking_parts.append(chunk.text)
                        live.update(
                            Text(f"💭 {''.join(thinking_parts)}", style="dim italic")
                        )
                    else:
                        first_chunk = chunk
                        break
                else:
                    return ""
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
            return ""
        console.print()

    # --- Stream content with Live markdown ------------------------------
    content_parts.append(first_chunk.text)

    try:
        with Live(
            Markdown("".join(content_parts)),
            console=console,
            refresh_per_second=8,
            vertical_overflow="visible",
        ) as live:
            for chunk in stream:
                if chunk.kind == "content":
                    content_parts.append(chunk.text)
                    live.update(Markdown("".join(content_parts)))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")

    return "".join(content_parts)


def _build_skill_prompt(skill: str | None) -> str:
    """Return the skill system-prompt addition, or empty string."""
    if not skill:
        return ""
    from ofx.ai.prompts import AI_SKILLS

    normalized = skill.lower().strip()
    text = AI_SKILLS.get(normalized)
    if text is None:
        from ofx.ai.prompts import SKILL_NAMES

        print_warning(
            "Unknown Skill",
            f"'{skill}' is not a recognized skill.",
            f"Available: {', '.join(SKILL_NAMES)}",
        )
        return ""
    return text


# ---------------------------------------------------------------------------
# GenerateHandler
# ---------------------------------------------------------------------------


class GenerateHandler:
    """Generate an OFX workflow YAML from a natural language description."""

    def __init__(self, prompt: str, output: str | None, model: str | None):
        self.prompt = prompt
        self.output = output
        self.model = model

    def run(self) -> None:
        from ofx.ai.prompts import GENERATE_SYSTEM_PROMPT

        cfg, console = _prepare(self.model)

        messages = [
            {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
            {"role": "user", "content": self.prompt},
        ]

        console.print(
            header_panel(
                "OFX AI · Generate",
                "",
                Prompt=f"[bold]{self.prompt}[/bold]",
                Model=f"[cyan]{cfg['model']}[/cyan]",
            )
        )
        console.print()

        yaml_content = _stream_to_stdout(cfg, messages)

        if self.output:
            path = Path(self.output)
            path.write_text(yaml_content)
            print_success("Workflow Saved", f"Written to: {path}")
        else:
            console.print(
                "\n[dim]Tip: use -o <file.yml> to save the generated workflow.[/dim]"
            )


# ---------------------------------------------------------------------------
# AnalyzeHandler
# ---------------------------------------------------------------------------


class AnalyzeHandler:
    """Analyze workflow output with an optional skill persona."""

    def __init__(
        self,
        output_file: str | None,
        workflow_file: str | None,
        skill: str | None,
        model: str | None,
    ):
        self.output_file = output_file
        self.workflow_file = workflow_file
        self.skill = skill
        self.model = model

    def run(self) -> None:
        from ofx.ai.prompts import ANALYZE_SYSTEM_PROMPT

        cfg, console = _prepare(self.model)

        context_parts = self._collect_context()
        if not context_parts:
            error_exit(
                "No Input",
                "Nothing to analyze.",
                "Provide --output-file, --workflow-file, or pipe data via stdin.",
            )

        skill_text = _build_skill_prompt(self.skill)
        system = ANALYZE_SYSTEM_PROMPT
        if skill_text:
            system = f"{system}\n\n## Skill focus\n{skill_text}"

        user_content = "\n\n".join(context_parts)
        user_content += "\n\nAnalyze the above data and produce your report."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        skill_label = f" · skill: [bold]{self.skill}[/bold]" if self.skill else ""
        fields = {"Model": f"[cyan]{cfg['model']}[/cyan]{skill_label}"}
        console.print(header_panel("OFX AI · Analyze", "", **fields))
        console.print()

        analysis = _stream_to_stdout(cfg, messages)

        if not analysis:
            print_warning("Empty Response", "The model returned no content.")

    def _collect_context(self) -> list[str]:
        parts: list[str] = []

        if self.workflow_file:
            wf_path = Path(self.workflow_file)
            if wf_path.exists():
                parts.append(f"## Workflow Definition\n```yaml\n{wf_path.read_text()}\n```")
            else:
                print_warning("Not Found", f"Workflow file not found: {self.workflow_file}")

        if self.output_file:
            out_path = Path(self.output_file)
            if out_path.exists():
                raw = out_path.read_text()
                try:
                    data = json.loads(raw)
                    formatted = json.dumps(data, indent=2)
                    parts.append(f"## Execution Output\n```json\n{formatted}\n```")
                except json.JSONDecodeError:
                    parts.append(f"## Execution Output (raw)\n```\n{raw}\n```")
            else:
                print_warning("Not Found", f"Output file not found: {self.output_file}")

        if not parts and not sys.stdin.isatty():
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                parts.append(f"## Input Data\n```\n{stdin_data}\n```")

        return parts


# ---------------------------------------------------------------------------
# ChatHandler
# ---------------------------------------------------------------------------


class ChatHandler:
    """Interactive multi-turn chat session."""

    def __init__(self, initial_prompt: str | None, model: str | None):
        self.initial_prompt = initial_prompt
        self.model = model

    def run(self) -> None:
        from ofx.ai.history import ChatHistory
        from ofx.ai.prompts import CHAT_SYSTEM_PROMPT

        cfg, console = _prepare(self.model)

        history = ChatHistory()
        history.set_system(CHAT_SYSTEM_PROMPT)

        console.print(
            header_panel(
                "OFX AI · Chat",
                "",
                Model=f"[cyan]{cfg['model']}[/cyan]",
                Hint="[dim]Type your question. Enter 'exit' or 'quit' to end.[/dim]",
            )
        )

        pending = self.initial_prompt
        while True:
            if pending is not None:
                user_input = pending
                pending = None
                console.print(f"\n[bold cyan]You:[/bold cyan] {user_input}")
            else:
                try:
                    user_input = input("\nYou > ").strip()
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[dim]Session ended.[/dim]")
                    break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[dim]Session ended.[/dim]")
                break

            history.maybe_compact(
                model=cfg["model"],
                api_key=cfg["api_key"],
                threshold=cfg["max_history_tokens"],
                base_url=cfg["base_url"],
            )

            history.add_user(user_input)
            console.print("\n[bold red]OFX AI:[/bold red]")

            response = _stream_to_stdout(cfg, history.to_list())
            history.add_assistant(response)


# ---------------------------------------------------------------------------
# list_skills / SetupHandler
# ---------------------------------------------------------------------------


def list_skills() -> None:
    """Print a table of available AI skill personas."""
    from ofx.ai.prompts import AI_SKILLS

    console = get_console()
    descriptions = {
        "recon": "Exposed services, CVEs, attack surface prioritization",
        "exploit": "CVE mapping, misconfigs, exploitation recommendations",
        "search": "Credential extraction, topology mapping, pattern analysis",
        "lateral": "Pivot points, SMB/WMI/RDP paths, AD trust chains",
        "persistence": "Persistence mechanisms, AV/EDR awareness, fallbacks",
        "privesc": "SUID/sudo/AD misconfigs, Kerberoast, privilege paths",
        "report": "Professional engagement report with findings & remediation",
        "opsec": "Detection risk, noisy commands, cleanup recommendations",
    }
    table = status_table(
        ("Skill", "bold cyan"),
        ("Focus", "white"),
        rows=[(name, descriptions.get(name, "")) for name in AI_SKILLS],
    )
    table.title = "Available AI Skills"
    console.print(table)
    console.print(
        "\n[dim]Usage:[/dim] [bold]ofx ai analyze --skill <name> -f output.json[/bold]"
    )


class SetupHandler:
    def __init__(self):
        pass

    def run(self) -> None:
        import os

        from ofx.ai.client import check_ai_available
        from ofx.settings import settings

        console = get_console()
        ai = settings.ai
        console.print(
            header_panel(
                "OFX AI · Setup",
                "[dim]Configure OFX AI via environment variables or a .env file.[/dim]",
            )
        )

        api_key_val = ai.api_key.get_secret_value() or os.getenv("OPENAI_API_KEY", "")
        table = status_table(
            ("Variable", "bold cyan"),
            ("Current Value", "white"),
            ("Description", "dim"),
            rows=[
                (
                    "OFX_AI__API_KEY",
                    "[green]set[/green]" if api_key_val else "[red]not set[/red]",
                    "Provider API key (fallback: OPENAI_API_KEY)",
                ),
                ("OFX_AI__MODEL", ai.model, "Model name (default: gpt-4o)"),
                (
                    "OFX_AI__BASE_URL",
                    ai.base_url or "[dim]not set — uses OpenAI default[/dim]",
                    "Base URL for compatible providers (Ollama, Groq, Together AI, …)",
                ),
                ("OFX_AI__TEMPERATURE", str(ai.temperature), "Sampling temperature (default: 0.7)"),
                ("OFX_AI__MAX_TOKENS", str(ai.max_tokens), "Max response tokens (default: 8192)"),
                (
                    "OFX_AI__MAX_HISTORY_TOKENS",
                    str(ai.max_history_tokens),
                    "Chat history compaction threshold (default: 30000)",
                ),
            ],
        )
        console.print(table)

        console.print()
        console.print("[dim]Provider examples:[/dim]")
        examples = [
            ("OpenAI",       "OFX_AI__API_KEY=sk-...   OFX_AI__MODEL=gpt-4o"),
            ("Ollama",       "OFX_AI__BASE_URL=http://localhost:11434/v1   OFX_AI__MODEL=llama3.2"),
            ("Groq",         "OFX_AI__API_KEY=gsk_...  OFX_AI__BASE_URL=https://api.groq.com/openai/v1  OFX_AI__MODEL=llama-3.3-70b-versatile"),
            ("Together AI",  "OFX_AI__API_KEY=...      OFX_AI__BASE_URL=https://api.together.xyz/v1"),
            ("LM Studio",    "OFX_AI__BASE_URL=http://localhost:1234/v1   OFX_AI__MODEL=local-model"),
        ]
        for provider, example in examples:
            console.print(f"  [bold]{provider:<12}[/bold] [dim]{example}[/dim]")

        dep_ok = check_ai_available()
        console.print()
        if dep_ok:
            console.print("[bold green][OK][/bold green] openai package installed")
        else:
            console.print(
                "[bold red][X][/bold red] openai package not installed — "
                "run: [bold]uv add openai[/bold]"
            )
