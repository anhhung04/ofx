# docs

Serve interactive API documentation server.

## Usage

```bash
ofx docs [options]
```

## Description

Starts a local HTTP server providing interactive API documentation for all OFX modules, functions, and classes. The documentation is auto-generated from docstrings and type hints.

## Options

- `--port <port>` - Server port (default: 8000)
- `--host <host>` - Server host (default: 127.0.0.1)
- `--no-browser` - Don't open browser automatically
- `--reload` - Enable auto-reload on code changes

## Examples

### Start documentation server

```bash
ofx docs
```

Starts server at `http://localhost:8000` and opens in browser.

### Custom port

```bash
ofx docs --port 9000
```

### Public access

```bash
ofx docs --host 0.0.0.0 --port 8080
```

### Development mode with auto-reload

```bash
ofx docs --reload
```

## Documentation Structure

The documentation server provides:

### API Reference
- Function signatures
- Parameter descriptions
- Return types
- Usage examples
- Source code links

### Module Index
- All available modules
- Class hierarchies
- Function listings

### Search
- Full-text search across all documentation
- Filter by module, class, function

### Interactive Examples
- Try API functions in browser
- See live results
- Copy code snippets

## Server Features

- **Auto-generated**: Documentation created from code
- **Type-aware**: Leverages Python type hints
- **Searchable**: Full-text search functionality
- **Responsive**: Works on desktop and mobile
- **Dark mode**: Eye-friendly theme

## Generated Documentation

Documentation includes:

1. **API Modules**: reconnaissance, exploitation, post-exploitation
2. **Core APIs**: HTTP, network, file operations
3. **Utilities**: String manipulation, encoding, helpers
4. **Workflows**: Workflow execution APIs

## See Also

- [API Overview](../../api/overview.md)
