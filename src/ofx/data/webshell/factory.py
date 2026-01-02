"""Factory for generating webshell operation code snippets."""

from .generators import (
    AspGenerator,
    AspxGenerator,
    BashGenerator,
    JspGenerator,
    PerlGenerator,
    PhpGenerator,
    PowerShellGenerator,
    PythonGenerator,
    RubyGenerator,
)


class WebShellFactory:
    """Factory for generating various webshell operation code snippets."""

    _GENERATORS = {
        "python": PythonGenerator,
        "php": PhpGenerator,
        "jsp": JspGenerator,
        "java": JspGenerator,  # Java uses JSP generator
        "aspx": AspxGenerator,
        "asp": AspGenerator,
        "bash": BashGenerator,
        "powershell": PowerShellGenerator,
        "perl": PerlGenerator,
        "ruby": RubyGenerator,
    }

    _REVERSE_SHELL_LANGUAGES = {
        "python",
        "bash",
        "powershell",
        "perl",
        "ruby",
        "php",
        "java",
    }

    _WEBSHELL_LANGUAGES = {"python", "php", "jsp", "java", "aspx", "asp"}

    @staticmethod
    def reverse_shell(language: str, target_ip: str, target_port: int) -> str:
        """Generate reverse shell code."""
        language = language.lower()

        if language not in WebShellFactory._REVERSE_SHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for reverse shells: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._REVERSE_SHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "reverse_shell"):
            raise ValueError(f"No reverse shell generator for language: {language}")

        return generator.reverse_shell(target_ip, target_port)

    @staticmethod
    def read_file(language: str, file_path: str, encoding: str = "utf-8") -> str:
        """Generate code to read file contents."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for file operations: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "read_file"):
            raise ValueError(f"No read_file generator for language: {language}")

        return generator.read_file(file_path, encoding)

    @staticmethod
    def write_file(
        language: str, file_path: str, content: str, encoding: str = "utf-8"
    ) -> str:
        """Generate code to write file contents."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for file operations: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "write_file"):
            raise ValueError(f"No write_file generator for language: {language}")

        return generator.write_file(file_path, content, encoding)

    @staticmethod
    def run_command(language: str, command: str, capture_output: bool = True) -> str:
        """Generate code to execute system commands."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for command execution: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "run_command"):
            raise ValueError(f"No run_command generator for language: {language}")

        return generator.run_command(command, capture_output)

    @staticmethod
    def list_directory(language: str, directory: str = ".") -> str:
        """Generate code to list directory contents."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for directory operations: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "list_directory"):
            raise ValueError(f"No list_directory generator for language: {language}")

        return generator.list_directory(directory)

    @staticmethod
    def download_file(language: str, url: str, save_path: str) -> str:
        """Generate code to download file from URL."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for download operations: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "download_file"):
            raise ValueError(f"No download_file generator for language: {language}")

        return generator.download_file(url, save_path)

    @staticmethod
    def upload_file(language: str, file_path: str, content: str) -> str:
        """Generate code to upload file (base64 encoded content)."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for upload operations: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "upload_file"):
            raise ValueError(f"No upload_file generator for language: {language}")

        return generator.upload_file(file_path, content)

    @staticmethod
    def get_system_info(language: str) -> str:
        """Generate code to get system information."""
        language = language.lower()

        if language not in WebShellFactory._WEBSHELL_LANGUAGES:
            raise ValueError(
                f"Unsupported language for system info: {language}. "
                f"Supported: {', '.join(sorted(WebShellFactory._WEBSHELL_LANGUAGES))}"
            )

        generator = WebShellFactory._GENERATORS.get(language)
        if not generator or not hasattr(generator, "get_system_info"):
            raise ValueError(f"No get_system_info generator for language: {language}")

        return generator.get_system_info()
