import fcntl
import json
import logging
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import typer

from ofx.commands.ui_helpers import inputs_table
from ofx.models.config import DurableRunConfig
from ofx.runner import run_workflow
from ofx.settings import (
    TEMP_DIR,
    ensure_dir,
    get_workflow_search_dirs,
    settings,
)

logger = logging.getLogger(f"{settings.app_branding}.console")


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for cron-friendly logs."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_tmp_dir(output: str = "") -> Path:
    """Get the temporary directory for workflow runs"""
    if output and Path(output).is_dir():
        return Path(output)
    return Path(
        tempfile.mkdtemp(
            prefix=f"run_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}_",
            dir=ensure_dir(TEMP_DIR),
        )
    )


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: list[str] | None = None,
        env: dict[str, str] | None = None,
        output: str = "",
        profile: bool = False,
        durable: bool | None = None,
        resume: bool | None = None,
        durable_backend: str | None = None,
        durable_redis_prefix: str | None = None,
        quiet: bool = False,
        lock: str | None = None,
        log_format: str = "rich",
        wait_lock: int = 0,
        project: str = "",
        events: bool = False,
        time_window: str = "",
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input or []
        self.env = env or {}
        self.profile = profile
        self.durable = durable
        self.resume = resume
        self.durable_backend = durable_backend
        self.durable_redis_prefix = durable_redis_prefix
        self.quiet = quiet
        self.lock_path = Path(lock).expanduser() if lock else None
        self.log_format = log_format
        self.wait_lock = max(wait_lock, 0)
        self.project_vars: dict[str, str] = {}
        self.events = events
        self.time_window = time_window

        if project:
            self._resolve_project(project)
            self.output = (
                get_tmp_dir(output)
                if output
                else Path(self.project_vars["project_path"])
            )
            self.output.mkdir(parents=True, exist_ok=True)
        else:
            self.output = get_tmp_dir(output)

    def _resolve_project(self, project: str) -> None:
        """Resolve project path and populate project variables."""
        from ofx.commands.project.project_manager import ProjectManager

        project_path = Path(ProjectManager.resolve_path(project))
        if not project_path.exists():
            raise typer.BadParameter(f"Project not found: {project}")

        self.project_vars = {
            "project_name": project_path.name,
            "project_path": str(project_path),
            "project_logs": str(project_path / "logs"),
            "project_scans": str(project_path / "scans"),
            "project_evidence": str(project_path / "evidence"),
            "project_scope": str(project_path / "scope"),
            "project_tools": str(project_path / "tools"),
            "project_exploits": str(project_path / "exploits"),
            "project_hosts": str(project_path / "hosts"),
            "project_osint": str(project_path / "osint"),
            "project_subdomains": str(project_path / "subdomains"),
            "project_targets": str(project_path / "targets"),
            "project_vulns": str(project_path / "vulns"),
            "project_web": str(project_path / "web"),
            "project_certs": str(project_path / "certs"),
        }

    async def run(self):
        import cProfile
        import pstats
        import time

        start_time = time.time()
        lock_fd: int | None = None
        profiler: cProfile.Profile | None = None

        if self.profile:
            logger.info("Profiling enabled (detailed timing data will be collected).")
            profiler = cProfile.Profile()
            profiler.enable()

        try:
            self._configure_logging()
            lock_fd = self._acquire_lock()
            self._process_inputs()

            logger.info("Workflow: %s", self.workflow_name)
            if self.project_vars:
                logger.info(
                    "Project: %s (%s)",
                    self.project_vars["project_name"],
                    self.project_vars["project_path"],
                )
            logger.info("Output: %s", self.output.as_posix())
            if self.input and not self.quiet:
                inputs_table(self.input)

            durable_overrides = self._durable_overrides()

            # Inject CLI time window into vars for WorkflowRunner
            run_vars = dict(self.project_vars) if self.project_vars else {}
            if self.time_window:
                run_vars["_cli_time_window"] = self.time_window
                logger.info("Time window: %s", self.time_window)

            result = await run_workflow(
                workflow=self.workflow_name,
                inputs=self.input,
                env=self.env,
                output_path=self.output,
                workflow_search_paths=get_workflow_search_dirs(),  # type: ignore
                quiet=self.quiet,
                durable_overrides=durable_overrides,
                vars=run_vars or None,
                event_sink_path=(self.output / "events.ndjson") if self.events else None,
            )

            if result.status.value == "completed":
                logger.info("Workflow completed successfully!")
            else:
                logger.error("Workflow failed")
                logger.error(
                    "Error details: %s", result.error or "No error message available."
                )

            # Display execution summary
            if not self.quiet:
                self._print_summary(result, start_time)

            # Save to run history
            self._save_history(result, start_time)

        finally:
            if lock_fd is not None:
                self._release_lock(lock_fd)
            if self.profile and profiler is not None:
                profiler.disable()
                end_time = time.time()

                total_time = end_time - start_time

                stats = pstats.Stats(profiler)
                stats.sort_stats("cumulative")

                profile_file = self.output / "profile.prof"
                profiler.dump_stats(str(profile_file))

                logger.info(
                    "Performance Summary: total_time=%.2fs profile=%s",
                    total_time,
                    profile_file,
                )

                logger.info("Top 10 functions by cumulative time:")
                stats.print_stats(10)

                logger.info("Top 10 functions by total time:")
                stats.print_stats("time", 10)

        return result

    def _print_summary(self, result, start_time: float) -> None:
        """Print a rich execution summary after workflow completion."""
        import time

        from ofx.commands.ui_helpers import execution_summary_panel
        from ofx.settings import get_console

        console = get_console()
        summary = result.outputs.pop("__summary__", None)
        if not summary:
            return

        elapsed = time.time() - start_time
        # Inject elapsed time into summary
        summary["elapsed_seconds"] = round(elapsed, 1)

        panel = execution_summary_panel(summary)
        console.print()
        console.print(panel)

        # Show findings export summary
        findings = result.outputs.pop("__findings_export__", None)
        if findings:
            console.print("  [bold green]📁 Findings exported:[/]")
            for line in findings:
                console.print(f"  {line}")
            console.print()

        # Show output path
        console.print(f"  [dim]Output:[/] {self.output}")
        console.print()

    def _save_history(self, result, start_time: float) -> None:
        """Save run record to history file."""
        from ofx.commands.flow.history import save_run_record

        elapsed = time.time() - start_time
        summary = result.outputs.get("__summary__")

        save_run_record(
            run_id=result.run_id,
            workflow_name=self.workflow_name,
            status=result.status.value,
            error=result.error,
            inputs=getattr(self, "input", None),
            project=self.project_vars.get("project_name", ""),
            output_path=str(self.output),
            elapsed_seconds=elapsed,
            summary=summary,
        )

    def _process_inputs(self):
        from ofx.utils.args import parse_key_value_pairs

        self.input = parse_key_value_pairs(self.preprocess_input)

        # Expand @file references: target=@targets.txt reads file lines
        self._expand_file_refs()

        # Auto-load targets from project targets/ folder when no target is provided
        if "target" not in self.input and self.project_vars:
            targets_dir = Path(self.project_vars.get("project_targets", ""))
            if targets_dir.is_dir():
                targets = self._load_targets_dir(targets_dir)
                if targets:
                    self.input["target"] = targets[0] if len(targets) == 1 else targets
                    logger.info(
                        "Loaded %d target(s) from %s",
                        len(targets),
                        targets_dir,
                    )

        # Validate inputs against workflow dispatch schema
        self._validate_inputs()

    def _expand_file_refs(self) -> None:
        """Expand @file references in input values.

        When a value starts with ``@``, treat the remainder as a file path.
        Read the file, one entry per line (skip blanks and ``#`` comments),
        and replace the value with a single string (one line) or a list.
        """
        for key, value in list(self.input.items()):
            if not isinstance(value, str) or not value.startswith("@"):
                continue
            filepath = Path(value[1:]).expanduser()
            if not filepath.is_file():
                raise typer.BadParameter(
                    f"File not found for input '{key}': {filepath}"
                )
            entries = self._read_target_file(filepath)
            if not entries:
                raise typer.BadParameter(
                    f"File for input '{key}' is empty: {filepath}"
                )
            self.input[key] = entries[0] if len(entries) == 1 else entries
            logger.info("Loaded %d value(s) for '%s' from %s", len(entries), key, filepath)

    def _validate_inputs(self) -> None:
        """Validate inputs against the workflow dispatch schema.

        Checks required inputs are present and coerces types where possible.
        """
        from ofx.utils.workflow_utils import find_workflow

        try:
            wf = find_workflow(self.workflow_name, tuple(get_workflow_search_dirs()))
        except Exception:
            return  # Validation runs best-effort; workflow resolution errors handled later

        if not wf.dispatch or not wf.dispatch.inputs:
            return

        errors: list[str] = []
        for name, spec in wf.dispatch.inputs.items():
            alias = getattr(spec, "alias", None)
            # Resolve alias: if alias was used, map it to the canonical name
            if alias and alias in self.input and name not in self.input:
                self.input[name] = self.input.pop(alias)

            if spec.required and name not in self.input:
                label = f"'{name}'" + (f" (alias: -{alias})" if alias else "")
                errors.append(f"Required input {label} is missing")
                continue

            if name not in self.input:
                # Apply default if not provided
                if spec.default is not None:
                    self.input[name] = spec.default
                continue

            # Type coercion
            value = self.input[name]
            declared_type = getattr(spec, "type", "string") or "string"
            if isinstance(value, str):
                if declared_type == "integer":
                    try:
                        self.input[name] = int(value)
                    except ValueError:
                        errors.append(
                            f"Input '{name}' expects integer, got '{value}'"
                        )
                elif declared_type == "boolean":
                    self.input[name] = value.lower() in ("true", "1", "yes")

        if errors:
            msg = "Input validation failed:\n  " + "\n  ".join(errors)
            raise typer.BadParameter(msg)

    @staticmethod
    def _read_target_file(filepath: Path) -> list[str]:
        """Read a target file, returning unique non-empty, non-comment lines."""
        entries: list[str] = []
        seen: set[str] = set()
        for line in filepath.read_text().splitlines():
            entry = line.strip()
            if entry and not entry.startswith("#") and entry not in seen:
                seen.add(entry)
                entries.append(entry)
        return entries

    @staticmethod
    def _load_targets_dir(targets_dir: Path) -> list[str]:
        """Read all .txt files in a targets directory and return unique targets."""
        targets: list[str] = []
        seen: set[str] = set()
        for txt_file in sorted(targets_dir.glob("*.txt")):
            for line in txt_file.read_text().splitlines():
                entry = line.strip()
                if entry and not entry.startswith("#") and entry not in seen:
                    seen.add(entry)
                    targets.append(entry)
        return targets

    def _durable_overrides(self) -> DurableRunConfig | None:
        if (
            self.durable is None
            and self.resume is None
            and self.durable_backend is None
            and self.durable_redis_prefix is None
        ):
            return None

        config = DurableRunConfig()
        if self.durable is not None:
            config.enabled = self.durable
        if self.resume is not None:
            config.resume = self.resume
        if self.durable_backend is not None:
            config.backend = self.durable_backend
        if self.durable_redis_prefix is not None:
            config.redis_prefix = self.durable_redis_prefix
        return config

    def _configure_logging(self) -> None:
        if self.log_format not in {"rich", "json", "text"}:
            return
        if self.log_format == "rich":
            return

        branding_logger = logging.getLogger(settings.app_branding)
        branding_logger.handlers.clear()
        branding_logger.propagate = False

        handler = logging.StreamHandler()
        if self.log_format == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )

        branding_logger.addHandler(handler)
        branding_logger.setLevel(logging.INFO)

    def _acquire_lock(self) -> int | None:
        if not self.lock_path:
            return None
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.time() + self.wait_lock
        while True:
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:  # pragma: no cover - platform specific
                if time.time() >= deadline:
                    os.close(fd)
                    raise RuntimeError(
                        f"Another workflow run is in progress (lock: {self.lock_path})."
                    ) from exc
                time.sleep(1)
        os.write(fd, str(os.getpid()).encode())
        return fd

    def _release_lock(self, fd: int) -> None:
        try:
            os.close(fd)
        finally:
            if self.lock_path:
                try:
                    self.lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
