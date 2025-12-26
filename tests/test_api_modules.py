"""Comprehensive tests for OFX API modules."""


class TestExploitModule:
    """Test exploit.py utilities."""

    def test_attrib_dict(self):
        from ofx.api.exploit import AttribDict

        d = AttribDict({"name": "test", "value": 123})
        assert d.name == "test"
        assert d.value == 123
        d.new_key = "new_value"
        assert d["new_key"] == "new_value"

    def test_ordered_dict(self):
        # Standard dict maintains insertion order in Python 3.7+
        d = dict()
        d["z"] = 1
        d["a"] = 2
        d["m"] = 3
        keys = list(d.keys())
        assert keys == ["z", "a", "m"]

    def test_ordered_set(self):
        from ofx.api.exploit import OrderedSet

        s = OrderedSet([3, 1, 4, 1, 5, 9, 2, 6, 5])
        assert list(s) == [3, 1, 4, 5, 9, 2, 6]

    def test_urlparse(self):
        from ofx.api.exploit import urlparse

        result = urlparse("http://example.com:8080/path")
        assert result.scheme == "http"
        assert result.hostname == "example.com"
        assert result.port == 8080
        assert result.path == "/path"

    def test_check_port(self):
        from ofx.api.exploit import check_port

        # Test invalid port (should be unreachable)
        result = check_port("192.0.2.1", 99999, timeout=0.1)
        assert result is False

    def test_get_host_ip(self):
        from ofx.api.exploit import get_host_ip

        ip = get_host_ip()
        assert isinstance(ip, str)
        assert len(ip.split(".")) == 4  # IPv4 format

    def test_random_str(self):
        from ofx.api.exploit import random_str

        s1 = random_str(10)
        s2 = random_str(10)
        assert len(s1) == 10
        assert len(s2) == 10
        assert s1 != s2  # Should be random

    def test_get_middle_text(self):
        from ofx.api.exploit import get_middle_text

        text = "Hello [WORLD] from [EARTH]"
        result = get_middle_text(text, "[", "]")
        assert result == "WORLD"

    def test_mosaic(self):
        from ofx.api.exploit import mosaic

        text = "sensitive data 12345"
        result = mosaic(text, ratio=0.5)
        assert len(result) == len(text)
        assert "*" in result

    def test_encoder_bash_payload(self):
        from ofx.api.exploit import encoder_bash_payload

        payload = 'echo "hello"'
        encoded = encoder_bash_payload(payload)
        assert "echo" in encoded
        assert "base64" in encoded or "bash" in encoded

    def test_encoder_powershell_payload(self):
        from ofx.api.exploit import encoder_powershell_payload

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

        # Test empty list
        assert remove_duplicate_string([]) == []


class TestUtilsModule:
    """Test utils.py utilities."""

    def test_str_to_dict(self):
        from ofx.api.utils import str_to_dict

        result = str_to_dict("{'name': 'test', 'value': 123}")
        assert result == {"name": "test", "value": 123}

        # Test invalid input
        result = str_to_dict("invalid")
        assert result == {}

    def test_generate_random_user_agent(self):
        from ofx.api.utils import generate_random_user_agent

        ua1 = generate_random_user_agent()
        assert isinstance(ua1, str)
        assert len(ua1) > 0
        # User agents should contain browser indicators
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
        import asyncio

        from ofx.api.network import reverse_shell

        assert asyncio.iscoroutinefunction(reverse_shell)


class TestHttpServerModule:
    """Test httpserver.py utilities."""

    def test_phttp_server_import(self):
        from ofx.api.httpserver import PHTTPServer

        assert PHTTPServer is not None

    def test_phttp_server_singleton(self):
        from ofx.api.httpserver import PHTTPServer

        # Singleton pattern - should return same instance
        server1 = PHTTPServer(bind_port=9001)
        server2 = PHTTPServer(bind_port=9002)
        assert server1 is server2

    def test_phttp_server_init(self):
        from ofx.api.httpserver import PHTTPServer

        # Singleton pattern returns the same instance
        # Test that we can access the server properties
        server = PHTTPServer(bind_ip="0.0.0.0", bind_port=9003)
        assert hasattr(server, "bind_ip")
        assert hasattr(server, "bind_port")
        assert server.https is False


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
        from ofx.api.shellcode import OSShellcodes

        assert OSShellcodes is not None

    def test_shellcode_base_import(self):
        from ofx.api.shellcode import ShellCode

        assert ShellCode is not None

    def test_shellcode_to_exe_import(self):
        from ofx.api.shellcode import ShellcodeToExe

        assert ShellcodeToExe is not None

    def test_shell_generator_import(self):
        from ofx.api.shellcode import ShellGenerator

        assert ShellGenerator is not None


class TestWebshellModule:
    """Test webshell submodule."""

    def test_webshell_imports(self):
        from ofx.api.webshell import (
            AspShell,
            AspxShell,
            JspShell,
            PhpShell,
            WebShell,
            WebShellClient,
            WebShellCodeFactory,
            generate_webshell,
        )

        assert WebShell is not None
        assert PhpShell is not None
        assert JspShell is not None
        assert AspShell is not None
        assert AspxShell is not None
        assert WebShellCodeFactory is not None
        assert WebShellClient is not None
        assert callable(generate_webshell)

    def test_php_shell_generation(self):
        from ofx.api.webshell import PhpShell

        shell = PhpShell(password="test123")
        code = shell.get_webshell()
        assert "<?php" in code
        assert "test123" in code or "{{PASSWORD}}" not in code

    def test_webshell_factory_operations(self):
        from ofx.api.webshell import WebShellCodeFactory

        # Test run_command
        code = WebShellCodeFactory.run_command("python", "whoami")
        assert "whoami" in code or "subprocess" in code

        # Test read_file
        code = WebShellCodeFactory.read_file("python", "/etc/passwd")
        assert "/etc/passwd" in code or "open" in code

        # Test reverse_shell
        code = WebShellCodeFactory.reverse_shell("bash", "192.168.1.1", 4444)
        assert "192.168.1.1" in code and "4444" in code

    def test_generate_webshell_convenience(self):
        from ofx.api.webshell import generate_webshell

        code = generate_webshell("php", password="secret")
        assert "<?php" in code
        assert "secret" in code or "{{PASSWORD}}" not in code


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
