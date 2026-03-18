"""AI command handlers for OFX."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ofx.commands.ui_helpers import print_error, print_success, print_warning
from ofx.settings import get_console


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ai_config(model_override: Optional[str] = None) -> dict:
    """Return resolved AI config dict from settings + env."""
    import os

    from ofx.settings import settings

    ai = settings.ai
    api_key = ai.api_key or os.getenv("OPENAI_API_KEY", "")
    return {
        "api_key": api_key,
        "model": model_override or ai.model,
        "temperature": ai.temperature,
        "max_tokens": ai.max_tokens,
        "max_history_tokens": ai.max_history_tokens,
        "base_url": ai.base_url or None,
    }


def _require_deps(cfg: dict) -> None:
    """Check anthropic is installed and an API key is available."""
    from ofx.ai.client import check_ai_available

    if not check_ai_available():
        print_error(
            "Missing Dependency",
            "openai package is not installed.",
            "Install with: uv add openai",
        )
        raise SystemExit(1)

    if not cfg["api_key"] and not cfg["base_url"]:
        print_error(
            "API Key Missing",
            "No API key found and no base_url configured.",
            "Set OFX_AI__API_KEY=sk-... (or OPENAI_API_KEY=sk-...) and retry, "
            "or set OFX_AI__BASE_URL for a local provider (e.g. Ollama). "
            "Run 'ofx ai setup' for configuration help.",
        )
        raise SystemExit(1)


def _stream_to_stdout(cfg: dict, messages: list[dict]) -> str:
    """Stream LLM response to stdout and return the full text."""
    from ofx.ai.client import call_llm_stream

    chunks: list[str] = []
    for chunk in call_llm_stream(
        messages=messages,
        model=cfg["model"],
        api_key=cfg["api_key"],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
        base_url=cfg["base_url"],
    ):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    print()  # trailing newline
    return "".join(chunks)


def _build_skill_prompt(skill: Optional[str]) -> str:
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

    def __init__(self, prompt: str, output: Optional[str], model: Optional[str]):
        self.prompt = prompt
        self.output = output
        self.model = model
        self.console = get_console()

    def run(self) -> None:
        from ofx.ai.prompts import GENERATE_SYSTEM_PROMPT

        cfg = _ai_config(self.model)
        _require_deps(cfg)

        messages = [
            {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
            {"role": "user", "content": self.prompt},
        ]

        self.console.print(
            Panel(
                Text.from_markup(
                    f"[dim]Prompt:[/dim] [bold]{self.prompt}[/bold]\n"
                    f"[dim]Model:[/dim]  [cyan]{cfg['model']}[/cyan]"
                ),
                title="[bold cyan]OFX AI · Generate[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )
        self.console.print()

        yaml_content = _stream_to_stdout(cfg, messages)

        if self.output:
            path = Path(self.output)
            path.write_text(yaml_content)
            print_success("Workflow Saved", f"Written to: {path}")
        else:
            self.console.print(
                "\n[dim]Tip: use -o <file.yml> to save the generated workflow.[/dim]"
            )


# ---------------------------------------------------------------------------
# AnalyzeHandler
# ---------------------------------------------------------------------------


class AnalyzeHandler:
    """Analyze workflow output with an optional skill persona."""

    def __init__(
        self,
        output_file: Optional[str],
        workflow_file: Optional[str],
        skill: Optional[str],
        model: Optional[str],
    ):
        self.output_file = output_file
        self.workflow_file = workflow_file
        self.skill = skill
        self.model = model
        self.console = get_console()

    def run(self) -> None:
        from ofx.ai.prompts import ANALYZE_SYSTEM_PROMPT

        cfg = _ai_config(self.model)
        _require_deps(cfg)

        context_parts = self._collect_context()
        if not context_parts:
            print_error(
                "No Input",
                "Nothing to analyze.",
                "Provide --output-file, --workflow-file, or pipe data via stdin.",
            )
            raise SystemExit(1)

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
        self.console.print(
            Panel(
                Text.from_markup(
                    f"[dim]Model:[/dim] [cyan]{cfg['model']}[/cyan]{skill_label}"
                ),
                title="[bold cyan]OFX AI · Analyze[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )
        self.console.print()

        analysis = _stream_to_stdout(cfg, messages)

        # Re-render as markdown in a panel for better readability
        self.console.print()
        self.console.print(
            Panel(
                Markdown(analysis),
                title="[bold green]Analysis Report[/bold green]",
                border_style="green",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

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

    def __init__(self, initial_prompt: Optional[str], model: Optional[str]):
        self.initial_prompt = initial_prompt
        self.model = model
        self.console = get_console()

    def run(self) -> None:
        from ofx.ai.history import ChatHistory
        from ofx.ai.prompts import CHAT_SYSTEM_PROMPT

        cfg = _ai_config(self.model)
        _require_deps(cfg)

        history = ChatHistory()
        history.set_system(CHAT_SYSTEM_PROMPT)

        self.console.print(
            Panel(
                Text.from_markup(
                    f"[dim]Model:[/dim] [cyan]{cfg['model']}[/cyan]\n"
                    "[dim]Type your question. Enter 'exit' or 'quit' to end.[/dim]"
                ),
                title="[bold cyan]OFX AI · Chat[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        pending = self.initial_prompt
        while True:
            if pending is not None:
                user_input = pending
                pending = None
                self.console.print(f"\n[bold cyan]You:[/bold cyan] {user_input}")
            else:
                try:
                    user_input = input("\nYou > ").strip()
                except (KeyboardInterrupt, EOFError):
                    self.console.print("\n[dim]Session ended.[/dim]")
                    break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                self.console.print("[dim]Session ended.[/dim]")
                break

            history.maybe_compact(
                model=cfg["model"],
                api_key=cfg["api_key"],
                threshold=cfg["max_history_tokens"],
                base_url=cfg["base_url"],
            )

            history.add_user(user_input)
            self.console.print("\n[bold red]OFX AI:[/bold red] ", end="")

            response = _stream_to_stdout(cfg, history.to_list())
            history.add_assistant(response)


# ---------------------------------------------------------------------------
# list_skills / SetupHandler
# ---------------------------------------------------------------------------


def list_skills() -> None:
    """Print a table of available AI skill personas."""
    from ofx.ai.prompts import AI_SKILLS

    console = get_console()
    table = Table(
        title="Available AI Skills",
        show_header=True,
        header_style="table.header",
        border_style="table.border",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    table.add_column("Skill", style="bold cyan", no_wrap=True)
    table.add_column("Focus", style="white")

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
    for name in AI_SKILLS:
        table.add_row(name, descriptions.get(name, ""))

    console.print(table)
    console.print(
        "\n[dim]Usage:[/dim] [bold]ofx ai analyze --skill <name> -f output.json[/bold]"
    )


class SetupHandler:
    def __init__(self):
        self.console = get_console()

    def run(self) -> None:
        from ofx.ai.client import check_ai_available
        from ofx.settings import settings

        ai = settings.ai
        self.console.print(
            Panel(
                Text.from_markup(
                    "[dim]Configure OFX AI via environment variables or a .env file.[/dim]"
                ),
                title="[bold cyan]OFX AI · Setup[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        table = Table(show_header=True, header_style="table.header", box=box.SIMPLE)
        table.add_column("Variable", style="bold cyan")
        table.add_column("Current Value", style="white")
        table.add_column("Description", style="dim")

        import os

        api_key_val = ai.api_key or os.getenv("OPENAI_API_KEY", "")
        table.add_row(
            "OFX_AI__API_KEY",
            "[green]set[/green]" if api_key_val else "[red]not set[/red]",
            "Provider API key (fallback: OPENAI_API_KEY)",
        )
        table.add_row("OFX_AI__MODEL", ai.model, "Model name (default: gpt-4o)")
        table.add_row(
            "OFX_AI__BASE_URL",
            ai.base_url or "[dim]not set — uses OpenAI default[/dim]",
            "Base URL for compatible providers (Ollama, Groq, Together AI, …)",
        )
        table.add_row(
            "OFX_AI__TEMPERATURE", str(ai.temperature), "Sampling temperature (default: 0.7)"
        )
        table.add_row(
            "OFX_AI__MAX_TOKENS", str(ai.max_tokens), "Max response tokens (default: 8192)"
        )
        table.add_row(
            "OFX_AI__MAX_HISTORY_TOKENS",
            str(ai.max_history_tokens),
            "Chat history compaction threshold (default: 30000)",
        )

        self.console.print(table)

        self.console.print()
        self.console.print("[dim]Provider examples:[/dim]")
        examples = [
            ("OpenAI",       "OFX_AI__API_KEY=sk-...   OFX_AI__MODEL=gpt-4o"),
            ("Ollama",       "OFX_AI__BASE_URL=http://localhost:11434/v1   OFX_AI__MODEL=llama3.2"),
            ("Groq",         "OFX_AI__API_KEY=gsk_...  OFX_AI__BASE_URL=https://api.groq.com/openai/v1  OFX_AI__MODEL=llama-3.3-70b-versatile"),
            ("Together AI",  "OFX_AI__API_KEY=...      OFX_AI__BASE_URL=https://api.together.xyz/v1"),
            ("LM Studio",    "OFX_AI__BASE_URL=http://localhost:1234/v1   OFX_AI__MODEL=local-model"),
        ]
        for provider, example in examples:
            self.console.print(f"  [bold]{provider:<12}[/bold] [dim]{example}[/dim]")

        dep_ok = check_ai_available()
        self.console.print()
        if dep_ok:
            self.console.print("[bold green][OK][/bold green] openai package installed")
        else:
            self.console.print(
                "[bold red][X][/bold red] openai package not installed — "
                "run: [bold]uv add openai[/bold]"
            )
