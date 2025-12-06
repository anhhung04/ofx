"""Docker-based assembly compiler for shellcode generation."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class AssemblyCompiler:
    """Compile assembly source files to shellcode using Docker + NASM"""

    def __init__(self):
        """Initialize assembly compiler."""
        # Get data directory containing assembly sources
        self.data_dir = Path(__file__).parent.parent / "data" / "shellcodes"
        if not self.data_dir.exists():
            raise RuntimeError(f"Shellcode data directory not found: {self.data_dir}")

    def _get_source_path(self, os_target: str, arch: str, shell_type: str) -> Path:
        """Get path to assembly source file."""
        # Map architecture names
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
        """Get path to Dockerfile for compilation."""
        arch_dir = arch if arch == "x64" else ""

        if arch_dir:
            dockerfile = self.data_dir / os_target / arch_dir / "Dockerfile"
        else:
            dockerfile = self.data_dir / os_target / "Dockerfile"

        if not dockerfile.exists():
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile}")

        return dockerfile

    def _build_docker_image(self, os_target: str, arch: str) -> str:
        """Build Docker image for compilation."""
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
        """
        Compile assembly source to shellcode using Docker.

        Args:
            os_target: Target OS (linux, windows)
            arch: Architecture (x86, x64)
            shell_type: Shell type (reverse, bind)
            ip: IP address (for reverse shells)
            port: Port number

        Returns:
            Compiled shellcode bytes
        """
        source_file = self._get_source_path(os_target, arch, shell_type)
        image_name = self._build_docker_image(os_target, arch)

        # Convert IP to hex for substitution
        ip_parts = ip.split(".")
        ip_hex = "0x" + "".join([f"{int(p):02x}" for p in ip_parts])

        # Port in network byte order (big-endian)
        port_hex = f"0x{port:04x}"

        logger.info(
            f"Compiling {source_file.name} with IP={ip} ({ip_hex}), PORT={port} ({port_hex})"
        )

        # Create temporary output directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_file = temp_path / "shellcode.bin"

            # Run Docker container to compile
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
                        "/src/compile.sh"
                        if (source_file.parent / "compile.sh").exists()
                        else f"nasm -f bin /src/{source_file.name} -o /output/shellcode.bin",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )

                # Read compiled shellcode
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
        """
        List available assembly source files.

        Returns:
            Dictionary mapping "os/arch" to list of shellcode types
        """
        sources = {}

        for os_dir in self.data_dir.iterdir():
            if not os_dir.is_dir() or os_dir.name == "java":
                continue

            os_name = os_dir.name

            # Check x86 sources
            src_dir = os_dir / "src"
            if src_dir.exists():
                types = [f.stem.replace("_tcp", "") for f in src_dir.glob("*.asm")]
                if types:
                    sources[f"{os_name}/x86"] = types

            # Check x64 sources
            x64_dir = os_dir / "x64" / "src"
            if x64_dir.exists():
                types = [f.stem.replace("_tcp", "") for f in x64_dir.glob("*.asm")]
                if types:
                    sources[f"{os_name}/x64"] = types

        return sources


# Singleton instance
_assembly_compiler: Optional[AssemblyCompiler] = None


def get_assembly_compiler() -> AssemblyCompiler:
    """Get or create assembly compiler singleton."""
    global _assembly_compiler
    if _assembly_compiler is None:
        _assembly_compiler = AssemblyCompiler()
    return _assembly_compiler
