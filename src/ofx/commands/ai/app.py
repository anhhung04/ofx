"""AI assistant commands for OFX."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "ai"
HELP = "AI assistant: workflow generation, output analysis, and interactive chat"


@app.command("generate")
def generate(
    prompt: Annotated[str, typer.Argument(help="Natural language workflow description")],
    output: Annotated[
        str | None,
        typer.Option("-o", "--output", help="Save generated YAML to this file path"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override LLM model (e.g. claude-opus-4-6)"),
    ] = None,
):
    """Generate an OFX workflow YAML from a natural language description."""
    from ofx.commands.ai.handler import GenerateHandler

    GenerateHandler(prompt=prompt, output=output, model=model).run()


@app.command("analyze")
def analyze(
    output_file: Annotated[
        str | None,
        typer.Option(
            "--output-file", "-f",
            help="Workflow run output JSON file to analyze (or pipe via stdin)",
        ),
    ] = None,
    workflow_file: Annotated[
        str | None,
        typer.Option("--workflow-file", "-w", help="Workflow YAML for additional context"),
    ] = None,
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill", "-s",
            help=(
                "Analysis persona to apply. Built-in skills: "
                "recon, exploit, search, lateral, persistence, privesc, report, opsec"
            ),
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override LLM model"),
    ] = None,
):
    """Analyze workflow execution output with AI.

    Pass --output-file for a run output JSON, optionally --workflow-file for
    the source YAML, and --skill to focus the analysis on a specific red team
    phase (recon, exploit, search, lateral, persistence, privesc, report, opsec).

    Data can also be piped via stdin:
        cat run_output.json | ofx ai analyze --skill recon
    """
    from ofx.commands.ai.handler import AnalyzeHandler

    AnalyzeHandler(
        output_file=output_file,
        workflow_file=workflow_file,
        skill=skill,
        model=model,
    ).run()


@app.command("chat")
def chat(
    prompt: Annotated[
        str | None,
        typer.Option("-p", "--prompt", help="Opening message (skips interactive input)"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override LLM model"),
    ] = None,
):
    """Start an interactive AI chat session about OFX.

    Ask questions about workflow syntax, API modules, cloud config, and more.
    Type 'exit' or 'quit' to end the session.
    """
    from ofx.commands.ai.handler import ChatHandler

    ChatHandler(initial_prompt=prompt, model=model).run()


@app.command("skills")
def skills():
    """List available AI skill personas for the analyze command."""
    from ofx.commands.ai.handler import list_skills

    list_skills()


@app.command("setup")
def setup():
    """Show AI configuration status and environment variable reference."""
    from ofx.commands.ai.handler import SetupHandler

    SetupHandler().run()
