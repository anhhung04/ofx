from ofx.api.evasion import obfuscate_cmd, obfuscate_payload
from ofx.api.exploitation.webshell.generators.aspx import AspxGenerator
from ofx.api.exploitation.webshell.generators.jsp import JspGenerator
from ofx.api.exploitation.webshell.generators.php import PhpGenerator
from ofx.api.exploitation.webshell.generators.python import PythonGenerator


def test_evasion():
    print("Testing Evasion API:")
    php = obfuscate_payload("echo 'test';", "php")
    print(f"PHP Obfuscated: {php[:50]}...")
    assert "eval" in php

    python = obfuscate_payload("print('test')", "python")
    print(f"Python Obfuscated: {python[:50]}...")
    assert "b64decode" in python

    cmd = obfuscate_cmd("whoami")
    print(f"CMD Obfuscated: {cmd}")
    assert "^" in cmd


def test_generators():
    print("\nTesting Generators:")

    # PHP
    php_cmd = PhpGenerator.run_command("whoami")
    print(f"PHP Run Command: {php_cmd}")
    assert "base64_decode" in php_cmd

    php_persis = PhpGenerator.persistence("cron", "touch /tmp/pwned")
    print(f"PHP Persistence: {php_persis}")
    assert "crontab" in php_persis

    # Python
    py_cmd = PythonGenerator.run_command("whoami")
    print(f"Python Run Command: {py_cmd}")
    assert "subprocess" in py_cmd

    # ASPX
    aspx_cmd = AspxGenerator.run_command("whoami")
    print(f"ASPX Run Command: {aspx_cmd}")
    assert "FromBase64String" in aspx_cmd

    # JSP
    jsp_cmd = JspGenerator.run_command("whoami")
    print(f"JSP Run Command: {jsp_cmd}")
    assert "Base64.getDecoder()" in jsp_cmd


if __name__ == "__main__":
    try:
        test_evasion()
        test_generators()
        print("\nAll Tests Passed!")
    except Exception as e:
        print(f"\nTest Failed: {e}")
        import traceback

        traceback.print_exc()
