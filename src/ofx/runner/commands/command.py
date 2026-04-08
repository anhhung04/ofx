"""Command and script runners for executing shell commands and Python scripts"""

import asyncio
import builtins
import contextlib
import io
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from ofx.models.command import Command, Script
from ofx.runner.channels import ChannelStore
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
    RunResult,
)
from ofx.settings import DEFAULT_SHELL, settings


def exec_script_in_process(
    script,
    working_directory,
    job_model,
    step_model,
    workflow_model,
    ctx_model,
    inputs,
    secrets,
    channels_dir,
    outputs_file=None,
):
    """Execute script in a separate process with channel communication"""
    store = ChannelStore(channels_dir)

    # Make RUNNER_OUTPUTS / OFX_OUTPUTS available inside scripts
    if outputs_file:
        os.environ["RUNNER_OUTPUTS"] = outputs_file
        os.environ["OFX_OUTPUTS"] = outputs_file

    def _add_outputs(**kwargs):
        """Write key=value pairs to the OFX_OUTPUTS file.

        Lists and dicts are serialized as JSON. All other values
        are converted to strings.
        """
        if not outputs_file:
            return
        import json as _json

        with open(outputs_file, "a") as f:
            for k, v in kwargs.items():
                if isinstance(v, (dict, list)):
                    f.write(f"{k}={_json.dumps(v)}\n")
                else:
                    f.write(f"{k}={v}\n")

    from ofx.runner.execution.findings_export import export_typed_outputs

    # ── ASM integration helpers ──────────────────────────────────
    def _asm_targets(scope: str = "", effective: bool = True, target_type: str = "") -> list[str]:
        """Pull target values from an ASM scope.

        Returns a list of target strings (domains, IPs, etc.).

        Usage in script::

            targets = asm_targets("my-scope")
            for t in targets:
                print(t)
        """
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
            scope_id = _asm_resolve(client, scope)
            if effective:
                raw = client.effective_targets(scope_id)
                return [t.value for t in raw if not t.excluded and (not target_type or t.target_type == target_type)]
            raw_t = client.list_targets(scope_id)
            return [t.value for t in raw_t if t.enabled and (not target_type or t.target_type == target_type)]
        except Exception:
            return []

    def _asm_push(items: list, scope: str = "", source: str = "ofx") -> int:
        """Push typed output dicts to an ASM scope.

        Returns count of imported assets.

        Usage in script::

            count = asm_push([
                {"_type": "subdomain", "host": "sub.example.com"},
                {"_type": "ip", "ip": "1.2.3.4"},
            ], scope="my-scope")
            print(f"Pushed {count} assets")
        """
        try:
            from ofx.asm.config import get_asm_client
            from ofx.asm.export import batch_convert
            client = get_asm_client()
            scope_id = _asm_resolve(client, scope)
            assets, _ = batch_convert(items, source=source)
            if not assets:
                return 0
            result = client.import_generic(scope_id, assets)
            return result.get("imported", 0)
        except Exception:
            return 0

    def _asm_scopes() -> list[dict]:
        """List all ASM scopes.

        Returns a list of scope dicts with id, name, scope_type, group.

        Usage in script::

            for s in asm_scopes():
                print(f"{s['name']} ({s['id']})")
        """
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
            return [s.model_dump() for s in client.list_scopes()]
        except Exception:
            return []

    def _asm_scope_assets(scope: str = "", asset_type: str = "", limit: int = 1000) -> list[dict]:
        """List assets from an ASM scope.

        Returns a list of asset dicts.

        Usage in script::

            assets = asm_scope_assets("my-scope", asset_type="subdomain")
            for a in assets:
                print(a["value"])
        """
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
            scope_id = _asm_resolve(client, scope)
            assets, _ = client.list_assets(scope_id, limit=limit, asset_type=asset_type)
            return [a.model_dump() for a in assets]
        except Exception:
            return []

    def _asm_add_targets(targets: list[str], scope: str = "") -> int:
        """Add targets to an ASM scope (auto-detect types).

        Returns count of imported targets.

        Usage in script::

            count = asm_add_targets(["example.com", "10.0.0.1"], scope="my-scope")
            print(f"Added {count} targets")
        """
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
            scope_id = _asm_resolve(client, scope)
            result = client.bulk_import_targets(scope_id, targets, auto_detect=True)
            return result.imported
        except Exception:
            return 0

    def _asm_resolve(client, scope_ref: str) -> str:
        if not scope_ref:
            from ofx.asm.config import get_asm_config
            scope_ref = get_asm_config().default_scope
        if not scope_ref:
            raise ValueError("No ASM scope specified and no default configured")
        if len(scope_ref) >= 32 and "-" in scope_ref:
            return scope_ref
        found = client.find_scope(scope_ref)
        if found:
            return found.id
        raise ValueError(f"ASM scope '{scope_ref}' not found")

    globals_dict = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "os": os,
        "__job__": job_model,
        "__step__": step_model,
        "__workflow__": workflow_model,
        "__inputs__": inputs,
        "__ctx__": ctx_model,
        "__secrets__": secrets,
        "add_outputs": _add_outputs,
        "publish": lambda channel, data: store.publish(channel, data),
        "subscribe": lambda channel: store.subscribe(channel),
        "wait_for": lambda channel, condition, timeout=60: store.wait_for(
            channel, condition, timeout=timeout
        ),
        "export_typed_outputs": export_typed_outputs,
        # ASM integration
        "asm_targets": _asm_targets,
        "asm_push": _asm_push,
        "asm_scopes": _asm_scopes,
        "asm_scope_assets": _asm_scope_assets,
        "asm_add_targets": _asm_add_targets,
    }

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    exit_code = 0
    original_cwd = os.getcwd()

    try:
        os.chdir(working_directory)
        with (
            contextlib.redirect_stdout(stdout_capture),
            contextlib.redirect_stderr(stderr_capture),
        ):
            exec(script, globals_dict)
    except Exception as e:
        exit_code = 1
        stderr_capture.write(str(e))
    finally:
        os.chdir(original_cwd)

    stdout = stdout_capture.getvalue()
    stderr = stderr_capture.getvalue()

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }


class CommandRunner(BaseRunner[Command]):
    _shell_cache: dict[str, str] = {}

    def __init__(
        self,
        command_model: Command,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        logger: logging.Logger | None = None,
    ):
        """Optimized command runner with caching."""
        super().__init__(command_model, ctx, parent, None, logger=logger)
        self._outputs_file: Path | None = None

    async def _do_run(self) -> None:
        """Execute a shell command and capture output"""
        outputs: dict[str, Any] = {}
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)

        if not self.model.shell or not Path(self.model.shell).exists():
            raise RuntimeError(f"Shell not found: {self.model.shell}") from None

        executor = CommandExecutor(self.model, self.ctx.envs)
        executor.prepare_outputs_file()
        self._outputs_file = executor.outputs_file
        result = None

        try:
            result = await executor.execute()
            executor.raise_for_status(result.exit_code, result.stderr)
        except TimeoutError:
            raise RuntimeError(
                f"Command timed out after {self.model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Command error: {str(e)}") from e
        finally:
            if result is None:
                result = CommandExecutionResult(
                    exit_code=None, stdout="", stderr="", outputs={}
                )
            outputs.update(
                {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            outputs.update(result.outputs)
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)
            await executor.capture_outputs_file(
                self,
                RunnerRegistryKeys.OUTPUTS,
                lambda msg: self._log_debug(msg),
            )

    async def _pre_run(self) -> None:
        self.model.shell = self._resolve_shell()

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Command failed: {self._error}")
        self._log_debug(
            f"cmd result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _resolve_shell(self) -> str:
        """Resolve shell path from hierarchy or use default /bin/bash"""
        if self.model.shell:
            return self.model.shell

        parent = getattr(self, "parent", None)
        if parent and getattr(parent, "parent", None):
            grandparent = parent.parent
            grandparent_model = getattr(grandparent, "model", None)
            if grandparent_model:
                defaults = getattr(grandparent_model, "defaults", None)
                if defaults and hasattr(defaults, "run"):
                    parent_shell = getattr(defaults.run, "shell", None)
                    if parent_shell:
                        return parent_shell

        return DEFAULT_SHELL


class ScriptRunner(BaseRunner[Script]):
    async def _do_run(self) -> None:
        """Execute a Python script using exec"""
        try:
            result = await asyncio.wait_for(
                self._exec_script(), timeout=self.model.timeout_minutes * 60
            )
            outputs = {
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }

            # Parse outputs file (like CommandExecutor does for run: steps)
            outputs_file_path = self.ctx.envs.get("RUNNER_OUTPUTS")
            if outputs_file_path:
                outputs_file = Path(outputs_file_path)
                if outputs_file.exists():
                    try:
                        content = outputs_file.read_text().strip()
                        if content:
                            for line in content.splitlines():
                                line = line.strip()
                                if line and "=" in line:
                                    k, v = line.split("=", 1)
                                    k, v = k.strip(), v.strip()
                                    if k:
                                        outputs[k] = v
                                        self._log_debug(f"Captured output: {k}={v}")
                    except Exception as e:
                        self._log_debug(f"Failed to parse RUNNER_OUTPUTS: {e}")
                    finally:
                        try:
                            outputs_file.unlink(missing_ok=True)
                        except Exception as e:
                            self._log_debug(f"Failed to remove outputs file: {e}")

            await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
            status = (
                RunnerStatus.COMPLETED
                if result["exit_code"] == 0
                else RunnerStatus.FAILED
            )
            error = result["stderr"] if status == RunnerStatus.FAILED else None
            self._result = RunResult(
                name=self.name,
                run_id=self.run_id,
                status=status,
                error=error,
                outputs=outputs,
            )
            if status != RunnerStatus.COMPLETED:
                raise RuntimeError(error or "Script execution failed")
        except TimeoutError as timeout_exc:
            raise RuntimeError(
                f"Script timed out after {self.model.timeout_minutes} minutes"
            ) from timeout_exc

    async def _exec_script(self):
        """Run the script execution in a separate process"""
        # Use shared channels directory for inter-job communication
        channels_dir = settings.channels_dir
        outputs_file = self.ctx.envs.get("RUNNER_OUTPUTS")

        with ProcessPoolExecutor() as executor:
            future = executor.submit(
                exec_script_in_process,
                self.model.script,
                str(self.model.working_directory),
                self.parent.parent.model
                if self.parent and self.parent.parent
                else None,
                self.parent.model if self.parent else None,
                self.parent.parent.parent.model
                if self.parent and self.parent.parent and self.parent.parent.parent
                else None,
                self.ctx,
                self.ctx.inputs,
                self.ctx.secrets,
                channels_dir,
                outputs_file,
            )
            result = await asyncio.get_running_loop().run_in_executor(None, future.result)
            return result

    async def _pre_run(self) -> None:
        """Pre-run hook"""
        pass

    async def _post_run(self) -> None:
        if self._error:
            self._log_error(f"Script failed: {self._error}")
        self._log_debug(
            f"script result: \n---\n{await self.get_result()}\n---\n with context: \n---\n{self.ctx}\n---"
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
