"""Execution engine for modules: command, script and shell-function helpers.

Kept import-free on purpose: :mod:`ofx.runner` re-exports
:class:`~ofx.modules.execution.command.CommandRunner` and
:class:`~ofx.modules.execution.command.ScriptRunner` and bootstraps the
runner package, so eager imports here would re-enter the runner during
import (the command modules themselves import ``ofx.runner.*`` submodules).
"""

__all__: list[str] = []
