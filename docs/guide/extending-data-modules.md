# Extending Data Modules

OFX provides extensible data modules for shellcode and webshell generation. This guide explains how to create custom connectors and find the data directories.

## Overview

The data directory contains:

- **shellcode/**: Binary shellcode payloads and connectors
- **webshell/**: Webshell templates, generators, and connectors  
- **site/**: Static documentation site files

## Finding Data Directories

### Programmatic Access

OFX exposes the data directory location through settings:

```python
from ofx.settings import DATA_DIR

# Get the main data directory
print(f"Data directory: {DATA_DIR}")

# Access specific subdirectories
shellcode_dir = DATA_DIR / "shellcode"
webshell_dir = DATA_DIR / "webshell"
```

### File System Location

The data directory is located within the installed package:

```bash
# Find the installation location
python -c "import ofx; from pathlib import Path; print(Path(ofx.__file__).parent / 'data')"

# Typical locations:
# - Virtual env: ~/.venv/lib/python3.12/site-packages/ofx/data
# - User install: ~/.local/lib/python3.12/site-packages/ofx/data
# - System: /usr/lib/python3.12/site-packages/ofx/data
# - Development: /path/to/ofx/src/ofx/data
```

### CLI Helper

Use the Python settings to locate directories:

```bash
# Show data directory location
python -c "from ofx.settings import DATA_DIR; print(DATA_DIR)"

# List shellcode connectors
python -c "from ofx.settings import DATA_DIR; print(list((DATA_DIR / 'shellcode/connectors').glob('*.py')))"

# List webshell generators
python -c "from ofx.settings import DATA_DIR; print(list((DATA_DIR / 'webshell/generators').glob('*.py')))"
```

## Extending Shellcode Connectors

### Base Connector Interface

All shellcode connectors inherit from `ShellcodeConnector`:

```python
from abc import ABC, abstractmethod
from typing import Optional

class ShellcodeConnector(ABC):
    """Abstract base class for shellcode generation connectors."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.available = self.check_available()
    
    @abstractmethod
    def generate(
        self,
        arch: str,
        format: str,
        lhost: Optional[str] = None,
        lport: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """Generate shellcode bytes.
        
        Args:
            arch: Target architecture (x86, x64, arm, etc.)
            format: Output format (raw, hex, base64, etc.)
            lhost: Listener host IP
            lport: Listener port
            **kwargs: Additional connector-specific parameters
            
        Returns:
            Generated shellcode as bytes
        """
        pass
    
    def check_available(self) -> bool:
        """Check if connector dependencies are available."""
        return True
    
    def validate_params(self, arch: str, format: str) -> None:
        """Validate generation parameters."""
        pass
```

### Creating a Custom Connector

Create a new file in `data/shellcode/connectors/`:

```python
# src/ofx/data/shellcode/connectors/custom_connector.py

from typing import Optional
from ofx.data.shellcode.connectors.base import ShellcodeConnector
import subprocess
import shutil

class CustomShellcodeConnector(ShellcodeConnector):
    """Custom shellcode connector using external tool."""
    
    def __init__(self):
        super().__init__(
            name="custom-tool",
            description="Generate shellcode using custom tool"
        )
    
    def check_available(self) -> bool:
        """Check if custom tool is installed."""
        return shutil.which("custom-tool") is not None
    
    def generate(
        self,
        arch: str,
        format: str = "raw",
        lhost: Optional[str] = None,
        lport: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """Generate shellcode using custom tool."""
        
        self.validate_params(arch, format)
        
        # Build command
        cmd = ["custom-tool", "-a", arch]
        
        if lhost and lport:
            cmd.extend(["-l", f"{lhost}:{lport}"])
        
        if format:
            cmd.extend(["-f", format])
        
        # Execute and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True
        )
        
        return result.stdout
    
    def validate_params(self, arch: str, format: str) -> None:
        """Validate parameters."""
        valid_archs = ["x86", "x64", "arm", "arm64"]
        if arch not in valid_archs:
            raise ValueError(f"Invalid arch: {arch}. Must be one of {valid_archs}")
        
        valid_formats = ["raw", "hex", "base64", "c"]
        if format not in valid_formats:
            raise ValueError(f"Invalid format: {format}. Must be one of {valid_formats}")
```

### Registering the Connector

Add your connector to `data/shellcode/connectors/__init__.py`:

```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector
from ofx.data.shellcode.connectors.msfvenom import MsfvenomConnector
from ofx.data.shellcode.connectors.custom_connector import CustomShellcodeConnector

# Export all connectors
__all__ = [
    "ShellcodeConnector",
    "MsfvenomConnector", 
    "CustomShellcodeConnector",
]

# Registry for auto-discovery
CONNECTORS = {
    "msfvenom": MsfvenomConnector,
    "custom-tool": CustomShellcodeConnector,
}
```

## Extending Webshell Connectors

### Base Connector Interface

All webshell connectors inherit from `WebshellConnector`:

```python
from abc import ABC, abstractmethod
from typing import Optional

class WebshellConnector(ABC):
    """Abstract base class for webshell generation connectors."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.available = self.check_available()
    
    @abstractmethod
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell code.
        
        Args:
            language: Target language (php, jsp, aspx, etc.)
            password: Authentication password
            encoder: Encoding/obfuscation method
            secret_header: Optional HTTP header for authentication
            secret_value: Value for secret header
            inline: Generate inline/one-liner code
            **kwargs: Additional connector-specific parameters
            
        Returns:
            Generated webshell code as string
        """
        pass
    
    def check_available(self) -> bool:
        """Check if connector is available."""
        return True
    
    def validate_params(self, language: str, password: str, encoder: str) -> None:
        """Validate generation parameters."""
        pass
```

### Creating a Custom Webshell Connector

Create a new file in `data/webshell/connectors/`:

```python
# src/ofx/data/webshell/connectors/advanced_connector.py

from typing import Optional
from ofx.data.webshell.connectors.base import WebshellConnector
import requests

class AdvancedWebshellConnector(WebshellConnector):
    """Advanced webshell generator with remote templates."""
    
    def __init__(self):
        super().__init__(
            name="advanced-generator",
            description="Advanced webshell with remote template support"
        )
        self.base_url = "https://your-template-server.com/api"
    
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "base64",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell from remote template."""
        
        self.validate_params(language, password, encoder)
        
        # Fetch template from remote server
        template_code = self._fetch_template(language, encoder)
        
        # Apply customizations
        code = self._customize_template(
            template_code,
            password=password,
            secret_header=secret_header,
            secret_value=secret_value,
        )
        
        # Optionally minify/inline
        if inline:
            code = self._minify(code)
        
        return code
    
    def _fetch_template(self, language: str, encoder: str) -> str:
        """Fetch template from remote server."""
        response = requests.get(
            f"{self.base_url}/template",
            params={"lang": language, "encoder": encoder},
            timeout=10
        )
        response.raise_for_status()
        return response.text
    
    def _customize_template(
        self,
        template: str,
        password: str,
        secret_header: Optional[str],
        secret_value: Optional[str],
    ) -> str:
        """Apply customizations to template."""
        code = template.replace("{{PASSWORD}}", password)
        
        if secret_header and secret_value:
            auth_check = f"""
            if ($_SERVER['HTTP_{secret_header.upper().replace('-', '_')}'] !== '{secret_value}') {{
                http_response_code(404);
                exit;
            }}
            """
            code = auth_check + code
        
        return code
    
    def _minify(self, code: str) -> str:
        """Minify code to single line."""
        return " ".join(line.strip() for line in code.splitlines() if line.strip())
    
    def validate_params(self, language: str, password: str, encoder: str) -> None:
        """Validate parameters."""
        valid_languages = ["php", "jsp", "aspx", "asp"]
        if language not in valid_languages:
            raise ValueError(f"Unsupported language: {language}")
        
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters")
```

### Registering the Webshell Connector

Add to `data/webshell/connectors/__init__.py`:

```python
from ofx.data.webshell.connectors.base import WebshellConnector
from ofx.data.webshell.connectors.template import TemplateConnector
from ofx.data.webshell.connectors.advanced_connector import AdvancedWebshellConnector

__all__ = [
    "WebshellConnector",
    "TemplateConnector",
    "AdvancedWebshellConnector",
]

CONNECTORS = {
    "template": TemplateConnector,
    "advanced": AdvancedWebshellConnector,
}
```

## Using Custom Connectors

### In Python Code

```python
from ofx.data.shellcode.connectors import CONNECTORS as shellcode_connectors
from ofx.data.webshell.connectors import CONNECTORS as webshell_connectors

# Use shellcode connector
connector = shellcode_connectors["custom-tool"]()
if connector.available:
    shellcode = connector.generate(
        arch="x64",
        format="raw",
        lhost="192.168.1.100",
        lport=4444
    )
    print(f"Generated {len(shellcode)} bytes")

# Use webshell connector  
connector = webshell_connectors["advanced"]()
webshell = connector.generate(
    language="php",
    password="secret123",
    encoder="base64",
    inline=True
)
print(webshell)
```

### In Workflows

Reference connectors in workflow YAML:

```yaml
jobs:
  generate_payload:
    steps:
      - name: Generate shellcode
        run: |
          from ofx.data.shellcode.connectors import CONNECTORS
          connector = CONNECTORS["custom-tool"]()
          shellcode = connector.generate(
            arch="x64",
            lhost="{{ secrets.lhost }}",
            lport=4444
          )
          with open("payload.bin", "wb") as f:
              f.write(shellcode)
      
      - name: Generate webshell
        run: |
          from ofx.data.webshell.connectors import CONNECTORS
          connector = CONNECTORS["advanced"]()
          code = connector.generate(
            language="php",
            password="{{ secrets.webshell_pass }}"
          )
          print(f"webshell={code}")
        outputs:
          webshell: "{{ step.webshell }}"
```

## Best Practices

### Error Handling

Always validate inputs and handle errors gracefully:

```python
def generate(self, arch: str, **kwargs) -> bytes:
    try:
        self.validate_params(arch, kwargs.get("format", "raw"))
        return self._do_generate(arch, **kwargs)
    except ValueError as e:
        raise ValueError(f"Invalid parameters: {e}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Generation failed: {e.stderr.decode()}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {e}")
```

### Dependency Checking

Check for required tools/libraries:

```python
def check_available(self) -> bool:
    """Check if required dependencies are available."""
    # Check for command-line tools
    if not shutil.which("required-tool"):
        return False
    
    # Check for Python modules
    try:
        import required_module
        return True
    except ImportError:
        return False
```

### Logging

Use logging for debugging:

```python
import logging

logger = logging.getLogger(__name__)

def generate(self, arch: str, **kwargs) -> bytes:
    logger.debug(f"Generating shellcode for {arch}")
    result = self._do_generate(arch, **kwargs)
    logger.info(f"Generated {len(result)} bytes of shellcode")
    return result
```

### Testing

Create tests for your connectors:

```python
# tests/test_custom_connector.py

import pytest
from ofx.data.shellcode.connectors.custom_connector import CustomShellcodeConnector

def test_connector_available():
    connector = CustomShellcodeConnector()
    # Test should adapt based on whether tool is installed
    assert isinstance(connector.available, bool)

def test_generate_shellcode():
    connector = CustomShellcodeConnector()
    if not connector.available:
        pytest.skip("Connector not available")
    
    shellcode = connector.generate(
        arch="x64",
        format="raw",
        lhost="127.0.0.1",
        lport=4444
    )
    assert isinstance(shellcode, bytes)
    assert len(shellcode) > 0

def test_invalid_arch():
    connector = CustomShellcodeConnector()
    with pytest.raises(ValueError):
        connector.generate(arch="invalid", format="raw")
```

## Additional Resources

- [Shellcode API Documentation](../api/exploitation.md#shellcode-generation)
- [Webshell API Documentation](../api/exploitation.md#webshell-apis)
- [Workflow Integration](workflows.md)
- [Template System](templates.md)
