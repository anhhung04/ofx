# Evasion API

The Evasion API (`ofx.api.evasion`) provides utilities for obfuscating payloads and commands to bypass Web Application Firewalls (WAFs), Intrusion Detection Systems (IDS), and Antivirus (AV) detection.

---

## Features

- **Multi-language Support**: Obfuscate payloads for PHP, Python, Java, JSP, ASP, ASPX, Bash, PowerShell, and CMD.
- **Dynamic Obfuscation**: Generates randomized obfuscation patterns (e.g., variable renaming, string fragmentation) to vary signatures.
- **Native Integration**: Seamlessly integrated with OFX Webshell Generators.

---

## Usage

### Obfuscating Payloads

The primary entry point is `obfuscate_payload`.

```python
from ofx.api.evasion import obfuscate_payload

# PHP Obfuscation
php_code = "system('whoami');"
obfuscated_php = obfuscate_payload(php_code, "php")
# Result: $x='sys'.'tem'; $x(base64_decode('...'));

# Python Obfuscation
py_code = "import os; os.system('id')"
obfuscated_py = obfuscate_payload(py_code, "python")
# Result: exec(base64.b64decode('...'))
```

### Obfuscating Command Lines

For Windows CMD environments, use `obfuscate_cmd` to insert random carets.

```python
from ofx.api.evasion import obfuscate_cmd

cmd = "powershell -nop -c iex(...)"
safe_cmd = obfuscate_cmd(cmd)
# Result: p^o^w^e^r^s^h^e^ll -n^o^p ...
```

---

## Supported Languages

| Language | Techniques Used |
|----------|----------------|
| **PHP** | Base64 encoding, string fragmentation, variable randomization |
| **Python** | Base64 encoding, exec wrapper |
| **Java/JSP**| String fragmentation, reflection (where applicable) |
| **ASP** | Chr() encoding to hide strings |
| **ASPX** | Base64 encoding |
| **PowerShell** | Base64 encoding (UTF-16LE), `-EncodedCommand` |
| **Bash** | Base64 pipeline (`echo ... | base64 -d | bash`) |
| **CMD** | Caret insertion (`^`) |

---

## API Reference

### `ofx.api.evasion.obfuscate_payload(code: str, language: str) -> str`

Obfuscates a code snippet for the specified language.

- **code**: Source code to obfuscate.
- **language**: Target language identifier (e.g., 'php', 'python').

### `ofx.api.evasion.obfuscate_cmd(command: str) -> str`

Obfuscates a Windows CMD command using caret insertion.

- **command**: Command string to obfuscate.
