# Templates

Jinja2 uses `{{ ... }}` for variables. `${{ ... }}` is also accepted, but it keeps a literal `$` in the rendered output.

## What you can reference

- Inputs: `{{ inputs.target }}`
- Secrets: `{{ secrets.API_KEY }}` (masked)
- Context: `{{ ctx.run_id }}`, `{{ ctx.output_path }}`

## Shell Helper Functions

These functions are available as actual shell functions prepended to your commands:

| Function | Bash (Linux/macOS) | PowerShell (Windows) |
|----------|-------------------|---------------------|
| `fapt <pkg>` | `apt-get install` | `winget install` |
| `pip_install <pkg>` | Python pip | Python pip |
| `uv_install <pkg>` | uv tool install | uv tool install |
| `go_install <pkg>` | go install | go install |
| `cargo_install <pkg>` | cargo install | cargo install |
| `npm_install <pkg>` | npm install -g | npm install -g |
| `static_install <url> [name]` | curl + chmod | Invoke-WebRequest |

**Usage (direct shell function calls):**
```yaml
- run: |
    fapt python3
    go_install github.com/projectdiscovery/httpx/cmd/httpx
    $OFX_TOOLS_BIN_DIR/httpx -u https://{{ inputs.target }}
```

## Template Variables

### Path Variables
```yaml
{{ tools_dir }}         # Tool installation directory
{{ tools_bin_dir }}     # Tool binary directory
{{ temp_dir }}          # Temporary directory
{{ python }}            # Python executable path
{{ sudo }}              # "sudo" if available, empty string otherwise
```

### Platform Detection
```yaml
{{ is_windows }}        # true/false
{{ platform }}          # "windows" or "unix"

# Conditional commands
{% if is_windows %}
  dir
{% else %}
  ls -la
{% endif %}
```

## Support Functions

### File Utilities
```yaml
{{ file_read('/path/to/file') }}              # Read file content
{{ file_write('/path/to/file', 'content') }}  # Write to file
{{ file_append('/path/to/file', 'content') }} # Append to file
{{ file_lines('/path/to/file') }}             # Read file as list of lines
{{ file_exists('/path/to/file') }}            # Check if file exists
{{ is_file('/path') }}                        # Check if path is file
{{ is_dir('/path') }}                         # Check if path is directory
```

### Path Utilities
```yaml
{{ join_path(tools_dir, 'bin', 'tool') }}     # Join path components
{{ basename('/path/to/file.txt') }}           # Get filename: "file.txt"
{{ dirname('/path/to/file.txt') }}            # Get directory: "/path/to"
{{ glob('*.txt', '/path/to/dir') }}           # List matching files
{{ cwd() }}                                    # Current working directory
{{ home() }}                                   # User home directory
```

### String Encoding
```yaml
{{ b64encode('hello world') }}                # Base64 encode
{{ b64decode('aGVsbG8gd29ybGQ=') }}           # Base64 decode
{{ url_encode('hello world') }}               # URL encode: "hello%20world"
{{ url_decode('hello%20world') }}             # URL decode
{{ hex_encode('hello') }}                     # Hex encode: "68656c6c6f"
{{ hex_decode('68656c6c6f') }}                # Hex decode
```

### Hash Functions
```yaml
{{ md5('password') }}                         # MD5 hash
{{ sha1('password') }}                        # SHA1 hash
{{ sha256('password') }}                      # SHA256 hash
```

### Random Generators
```yaml
{{ random_string(8) }}                        # Random alphanumeric string
{{ random_string(16, 'hex') }}                # Random hex string
{{ random_int(1, 100) }}                      # Random integer
{{ random_port() }}                           # Random port (1024-65535)
{{ uuid() }}                                  # UUID v4
{{ token(32) }}                               # URL-safe token
```

### Network Utilities
```yaml
{{ local_ip() }}                              # Local IP address
{{ is_port_open('127.0.0.1', 80) }}          # Check if port is open
```

### Date/Time
```yaml
{{ now() }}                                   # Current datetime
{{ now('%Y-%m-%d') }}                         # Formatted datetime
{{ timestamp() }}                             # Unix timestamp
```

### JSON
```yaml
{{ to_json({'key': 'value'}) }}               # Object to JSON string
{{ from_json('{"key": "value"}') }}           # JSON string to object
```

### Regex
```yaml
{{ regex_match('^[0-9]+$', '123') }}          # Match at start
{{ regex_search('[0-9]+', 'abc123def') }}     # Search anywhere
{{ regex_findall('[0-9]+', 'a1b2c3') }}       # Find all matches
{{ regex_sub('[0-9]', 'X', 'a1b2') }}         # Replace matches
```

## Quick Examples

```yaml
- name: Scan with encoded payload
  run: |
    PAYLOAD="{{ b64encode(inputs.payload) }}"
    curl -X POST -d "$PAYLOAD" https://{{ inputs.target }}

- name: Generate temp file with unique name
  run: |
    OUTPUT="{{ join_path(temp_dir, random_string(8) + '.txt') }}"
    echo "Results" > "$OUTPUT"

- name: Platform-aware command
  run: |
    {% if is_windows %}
    netstat -an | findstr LISTEN
    {% else %}
    netstat -tlnp
    {% endif %}

- name: Get local IP for reverse shell
  run: |
    echo "Callback: {{ local_ip() }}:{{ random_port() }}"
```

## Tips

- In shell commands, prefer `{{ ... }}` to avoid `$` expansion
- Quote template values in shell commands: `"{{ inputs.ports }}"`
- Shell functions like `fapt`, `go_install` are called directly (not as Jinja templates)
- Template functions like `b64encode()`, `local_ip()` are used with `{{ }}`

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Jobs & Steps](jobs-steps.md) - Using templates in jobs and steps
- [Secrets & Inputs](secrets-inputs.md) - Managing inputs and secrets
