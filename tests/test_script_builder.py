"""Tests for session script builder safety and correctness."""

from __future__ import annotations

import pytest

from ofx.cloud.sessions.script_builder import (
    _ps_escape,
    _validate_env_key,
    build_session_script,
)
from ofx.models.step import Step
from ofx.utils.shell import bash_dquote_escape


def _make_step(
    run: str | None = None, script: str | None = None, name: str = "s"
) -> Step:
    data: dict = {"name": name}
    if run is not None:
        data["run"] = run
    elif script is not None:
        data["script"] = script
    return Step.model_validate(data)


# ---------------------------------------------------------------------------
# bash_dquote_escape
# ---------------------------------------------------------------------------
class TestBashDquoteEscape:
    def test_double_quote(self):
        assert bash_dquote_escape('say "hello"') == 'say \\"hello\\"'

    def test_backslash(self):
        assert bash_dquote_escape("a\\b") == "a\\\\b"

    def test_dollar_sign(self):
        assert bash_dquote_escape("$HOME") == "\\$HOME"

    def test_combined(self):
        assert bash_dquote_escape('$HOME\\"') == '\\$HOME\\\\\\"'

    def test_backtick(self):
        assert bash_dquote_escape("`whoami`") == "\\`whoami\\`"


# ---------------------------------------------------------------------------
# _ps_escape
# ---------------------------------------------------------------------------
class TestPsEscape:
    def test_double_quote(self):
        assert _ps_escape('"hello"') == '`"hello`"'

    def test_backtick(self):
        assert _ps_escape("a`b") == "a``b"

    def test_dollar_sign(self):
        assert _ps_escape("$env:PATH") == "`$env:PATH"

    def test_combined(self):
        result = _ps_escape('$HOME`"end')
        assert result == "`$HOME``" + '`"end'


class TestEnvKeyValidation:
    @pytest.mark.parametrize("key", ["TARGET", "TARGET_1", "_TARGET", "a1"])
    def test_valid_env_key(self, key):
        _validate_env_key(key)

    @pytest.mark.parametrize("key", ["1BAD", "BAD-KEY", "BAD KEY", "BAD.KEY", ""])
    def test_invalid_env_key(self, key):
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_key(key)


# ---------------------------------------------------------------------------
# build_session_script (bash) — env var escaping
# ---------------------------------------------------------------------------
class TestBuildBashEnvEscaping:
    def test_dollar_in_env_value(self):
        step = _make_step(run="echo test")
        script = build_session_script(
            [step], session_id="s1", work_dir="/tmp/s", env={"MY_VAR": "$SECRET"}
        )
        # Value should be backslash-escaped so it's not expanded
        assert 'export MY_VAR="\\$SECRET"' in script

    def test_double_quote_in_env_value(self):
        step = _make_step(run="echo test")
        script = build_session_script(
            [step], session_id="s1", work_dir="/tmp/s", env={"X": 'say "hi"'}
        )
        assert 'export X="say \\"hi\\""' in script

    def test_work_dir_with_spaces_escaped_in_bash(self):
        step = _make_step(run="echo hi")
        script = build_session_script([step], session_id="s1", work_dir="/tmp/my dir/s")
        # bash_dquote_escape leaves spaces alone — they're inside double-quotes in the assignment
        assert 'WORK_DIR="/tmp/my dir/s"' in script

    def test_session_id_escaped_in_bash(self):
        step = _make_step(run="echo hi")
        script = build_session_script([step], session_id='s"$1', work_dir="/tmp/s")
        assert 'export SESSION_ID="s\\"\\$1"' in script

    def test_invalid_env_key_raises_bash(self):
        step = _make_step(run="echo hi")
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            build_session_script(
                [step], session_id="s1", work_dir="/tmp/s", env={"BAD-KEY": "x"}
            )


# ---------------------------------------------------------------------------
# build_session_script (bash) — step command uses $WORK_DIR not literal
# ---------------------------------------------------------------------------
class TestBashStepUsesWorkDirVar:
    def test_command_step_uses_work_dir_var(self):
        step = _make_step(run="whoami")
        script = build_session_script([step], session_id="s1", work_dir="/some/path")
        assert 'cd "$WORK_DIR"' in script
        # Should NOT embed the literal path in the step command
        lines = [line for line in script.split("\n") if "whoami" in line]
        assert lines
        assert "/some/path" not in lines[0]

    def test_script_step_uses_work_dir_var(self):
        step = _make_step(script="print('hello')")
        script = build_session_script([step], session_id="s1", work_dir="/some/path")
        lines = [line for line in script.split("\n") if '".ofx_step_0.py"' in line]
        assert lines
        assert "/some/path" not in lines[0]


# ---------------------------------------------------------------------------
# build_session_script (bash) — inline script with single-quotes
# ---------------------------------------------------------------------------
class TestBashInlineScriptEscape:
    def test_single_quote_in_script(self):
        step = _make_step(script="x = 'hello world'")
        script = build_session_script([step], session_id="s1", work_dir="/tmp/s")
        assert "__OFX_PY_BIN=$(command -v python3 || command -v python)" in script
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_long_script_is_not_embedded_in_exec_command(self):
        long_script = "print('x')\n" * 2000
        step = _make_step(script=long_script)
        script = build_session_script([step], session_id="s1", work_dir="/tmp/s")
        exec_lines = [line for line in script.splitlines() if '"$__OFX_PY_BIN"' in line]
        assert exec_lines
        assert long_script[:40] not in exec_lines[0]
        assert '".ofx_step_0.py"' in exec_lines[0]


class TestTaskStepCommands:
    def test_bash_task_step_builds_task_command(self):
        step = Step.model_validate(
            {
                "name": "t",
                "task": "nmap",
                "with": {"target": "127.0.0.1"},
            }
        )
        script = build_session_script([step], session_id="s1", work_dir="/tmp/s")
        assert 'cd "$WORK_DIR" 2>/dev/null; nmap' in script

    def test_powershell_task_step_builds_task_command(self):
        step = Step.model_validate(
            {
                "name": "t",
                "task": "nmap",
                "with": {"target": "127.0.0.1"},
            }
        )
        script = build_session_script(
            [step], session_id="s1", work_dir="C:\\work", os_type="windows"
        )
        assert 'Set-Location "C:\\work"; nmap' in script


class TestScriptOpsecPayload:
    def test_inline_bundle_payload_is_obfuscated(self):
        from ofx.cloud.sessions.manager import _build_step_bundle_source

        step = _make_step(script='print("SECRET_TOKEN_123")')
        payload = _build_step_bundle_source(step)
        assert "SECRET_TOKEN_123" not in payload
        assert "marshal.loads" in payload or "exec(" in payload


# ---------------------------------------------------------------------------
# build_session_script (powershell) — env var escaping
# ---------------------------------------------------------------------------
class TestBuildPowerShellEnvEscaping:
    def test_dollar_in_ps_env_value(self):
        step = _make_step(run="Write-Output test")
        script = build_session_script(
            [step],
            session_id="s1",
            work_dir="C:\\work",
            env={"MY_VAR": "$secret"},
            os_type="windows",
        )
        assert '$env:MY_VAR = "`$secret"' in script

    def test_backtick_in_ps_env_value(self):
        step = _make_step(run="Write-Output test")
        script = build_session_script(
            [step],
            session_id="s1",
            work_dir="C:\\work",
            env={"X": "a`b"},
            os_type="windows",
        )
        assert '$env:X = "a``b"' in script

    def test_double_quote_in_ps_env_value(self):
        step = _make_step(run="Write-Output test")
        script = build_session_script(
            [step],
            session_id="s1",
            work_dir="C:\\work",
            env={"X": 'say "hi"'},
            os_type="windows",
        )
        assert '$env:X = "say `"hi`""' in script

    def test_invalid_env_key_raises_powershell(self):
        step = _make_step(run="Write-Output test")
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            build_session_script(
                [step],
                session_id="s1",
                work_dir="C:\\work",
                env={"BAD KEY": "x"},
                os_type="windows",
            )


# ---------------------------------------------------------------------------
# build_session_script (powershell) — inline script uses here-string
# ---------------------------------------------------------------------------
class TestPowerShellInlineScriptHereString:
    def test_inline_script_uses_python_temp_file(self):
        step = _make_step(script='print("$var")')
        script = build_session_script(
            [step], session_id="s1", work_dir="C:\\work", os_type="windows"
        )
        assert '$__ofx_py = Join-Path $WORK_DIR ".ofx_step_0.py"' in script
        assert "& py -3 $__ofx_py" in script

    def test_inline_script_keeps_content_literal(self):
        step = _make_step(script="x = '$HOME'")
        script = build_session_script(
            [step], session_id="s1", work_dir="C:\\work", os_type="windows"
        )
        assert '$__ofx_py = Join-Path $WORK_DIR ".ofx_step_0.py"' in script

    def test_script_file_escapes_ps_path(self):
        data = {"name": "sf", "script_file": 'C:\\Temp\\x`"$env:T.ps1'}
        step = Step.model_validate(data)
        script = build_session_script(
            [step], session_id="s1", work_dir='C:\\work`"$env:W', os_type="windows"
        )
        assert 'Set-Location "C:\\work```"`$env:W"' in script
        assert '$__ofx_py = Join-Path $WORK_DIR ".ofx_step_0.py"' in script
