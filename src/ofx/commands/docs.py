"""Documentation server commands for OFX"""
import http.server
import importlib
import inspect
import socketserver
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    ForwardRef,
    List,
    Optional,
    Union,
    get_type_hints,
)

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

app = typer.Typer()
console = Console()

NAME = "docs"
HELP = "Documentation server and API reference"


def discover_api_modules() -> Dict[str, Dict[str, str]]:
    """Auto-discover all API modules from ofx.api package."""
    try:
        api_package = importlib.import_module("ofx.api")
        api_file = api_package.__file__
        if not api_file:
            return {}

        api_path = Path(api_file).parent

        modules: Dict[str, Dict[str, str]] = {}
        for file in api_path.glob("*.py"):
            if file.name == "__init__.py":
                continue

            module_name = file.stem
            module_path = f"ofx.api.{module_name}"

            try:
                mod = importlib.import_module(module_path)
                if hasattr(mod, "__all__") or any(
                    not name.startswith("_") and callable(getattr(mod, name))
                    for name in dir(mod)
                ):
                    doc = inspect.getdoc(mod) or f"{module_name.title()} utilities"
                    modules[module_name] = {
                        "path": module_path,
                        "description": doc.split("\n")[0],
                    }
            except Exception:
                continue

        for subdir in api_path.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                init_file = subdir / "__init__.py"
                if init_file.exists():
                    module_name = subdir.name
                    module_path = f"ofx.api.{module_name}"
                    try:
                        mod = importlib.import_module(module_path)
                        if hasattr(mod, "__all__"):
                            doc = inspect.getdoc(mod) or f"{module_name.title()} module"
                            modules[module_name] = {
                                "path": module_path,
                                "description": doc.split("\n")[0],
                            }
                    except Exception:
                        continue

        return modules
    except Exception:
        return {}


def format_type(type_hint: Any, model_registry: Dict[str, Any]) -> str:
    """Format a type hint into a string, recursively handling nested models."""
    if isinstance(type_hint, str):
        return type_hint
    if isinstance(type_hint, ForwardRef):
        return type_hint.__forward_arg__
    if inspect.isclass(type_hint) and issubclass(type_hint, BaseModel):
        if type_hint.__name__ not in model_registry:
            get_model_schema(type_hint, model_registry)
        return type_hint.__name__
    if hasattr(type_hint, "__origin__"):
        origin = type_hint.__origin__
        args = type_hint.__args__

        if origin is Union and len(args) == 2 and type(None) in args:
            main_arg = next(t for t in args if t is not type(None))
            return f"Optional[{format_type(main_arg, model_registry)}]"

        origin_name = getattr(origin, "__name__", str(origin))
        arg_names = [format_type(arg, model_registry) for arg in args]
        return f"{origin_name}[{', '.join(arg_names)}]"
    if hasattr(type_hint, "_name"):
        return type_hint._name
    return getattr(type_hint, "__name__", str(type_hint))


def get_model_schema(
    model: Any, model_registry: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Get the schema of a Pydantic model and update the model registry."""
    if (
        not inspect.isclass(model)
        or not issubclass(model, BaseModel)
        or model.__name__ in model_registry
    ):
        return []

    model_registry[model.__name__] = []

    schema = []
    for name, field in model.model_fields.items():
        field_type_str = format_type(field.annotation, model_registry)

        field_info = {
            "name": name,
            "type": field_type_str,
            "required": field.is_required(),
            "default": field.get_default(),
            "description": field.description or "",
        }
        schema.append(field_info)

    model_registry[model.__name__] = schema
    return schema


def get_method_info(cls, method_name: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific class method."""
    try:
        method = getattr(cls, method_name)
        if not callable(method):
            return None

        doc = inspect.getdoc(method) or ""
        sig = inspect.signature(method)

        try:
            type_hints = get_type_hints(method)
        except Exception:
            type_hints = getattr(method, "__annotations__", {})

        parameters = []
        model_schemas = {}
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls", "return"):
                continue

            param_hint = type_hints.get(param_name, Any)
            param_type = format_type(param_hint, model_schemas)

            if param.kind == param.VAR_KEYWORD:
                parameters.append(
                    {
                        "name": f"**{param_name}",
                        "type": "Any",
                        "default": "",
                        "required": False,
                    }
                )
            elif param.kind == param.VAR_POSITIONAL:
                parameters.append(
                    {
                        "name": f"*{param_name}",
                        "type": "Any",
                        "default": "",
                        "required": False,
                    }
                )
            else:
                default = "" if param.default is param.empty else str(param.default)
                parameters.append(
                    {
                        "name": param_name,
                        "type": param_type,
                        "default": default,
                        "required": param.default is param.empty,
                    }
                )

        return_type_hint = type_hints.get("return", Any)
        return_type = format_type(return_type_hint, model_schemas)

        return {
            "name": method_name,
            "type": "method",
            "doc": doc,
            "parameters": parameters,
            "return_type": return_type,
            "models": model_schemas,
            "class_name": cls.__name__,
        }
    except Exception:
        return None


def get_module_functions(module) -> List[Dict[str, Any]]:
    """Get all public functions from a module with their documentation."""
    functions = []

    all_names = getattr(module, "__all__", None)

    func_lookup = dict(inspect.getmembers(module, inspect.isfunction))
    class_lookup = dict(inspect.getmembers(module, inspect.isclass))

    if all_names is not None:
        for name in all_names:
            if name in func_lookup:
                func = func_lookup[name]
                doc = inspect.getdoc(func) or ""
                sig = inspect.signature(func)
                try:
                    type_hints = get_type_hints(func)
                except Exception:
                    type_hints = getattr(func, "__annotations__", {})

                parameters = []
                model_schemas = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "return":
                        continue

                    param_hint = type_hints.get(param_name, Any)
                    param_type = format_type(param_hint, model_schemas)

                    if param.kind == param.VAR_KEYWORD:
                        parameters.append(
                            {
                                "name": f"**{param_name}",
                                "type": "Any",
                                "default": "",
                                "required": False,
                            }
                        )
                    elif param.kind == param.VAR_POSITIONAL:
                        parameters.append(
                            {
                                "name": f"*{param_name}",
                                "type": "Any",
                                "default": "",
                                "required": False,
                            }
                        )
                    else:
                        default = (
                            "" if param.default is param.empty else str(param.default)
                        )
                        parameters.append(
                            {
                                "name": param_name,
                                "type": param_type,
                                "default": default,
                                "required": param.default is param.empty
                                and param.kind != param.VAR_POSITIONAL,
                            }
                        )

                return_type_hint = type_hints.get("return", Any)
                return_type = format_type(return_type_hint, model_schemas)

                functions.append(
                    {
                        "name": name,
                        "type": "function",
                        "doc": doc,
                        "parameters": parameters,
                        "return_type": return_type,
                        "models": model_schemas,
                    }
                )

            elif name in class_lookup:
                cls = class_lookup[name]
                doc = inspect.getdoc(cls) or ""

                methods = []
                try:
                    if hasattr(cls, "__init__"):
                        init_func = cls.__init__
                        sig = inspect.signature(init_func)
                        try:
                            type_hints = get_type_hints(init_func)
                        except Exception:
                            type_hints = getattr(init_func, "__annotations__", {})

                        parameters = []
                        model_schemas = {}
                        for param_name, param in sig.parameters.items():
                            if param_name in ("self", "return"):
                                continue

                            param_hint = type_hints.get(param_name, Any)
                            param_type = format_type(param_hint, model_schemas)

                            if param.kind == param.VAR_KEYWORD:
                                parameters.append(
                                    {
                                        "name": f"**{param_name}",
                                        "type": "Any",
                                        "default": "",
                                        "required": False,
                                    }
                                )
                            elif param.kind == param.VAR_POSITIONAL:
                                parameters.append(
                                    {
                                        "name": f"*{param_name}",
                                        "type": "Any",
                                        "default": "",
                                        "required": False,
                                    }
                                )
                            else:
                                default = (
                                    ""
                                    if param.default is param.empty
                                    else str(param.default)
                                )
                                parameters.append(
                                    {
                                        "name": param_name,
                                        "type": param_type,
                                        "default": default,
                                        "required": param.default is param.empty,
                                    }
                                )

                        for method_name, method in inspect.getmembers(
                            cls, inspect.isfunction
                        ):
                            if not method_name.startswith("_") or method_name in (
                                "__init__",
                                "__call__",
                            ):
                                if method_name == "__init__":
                                    continue
                                method_doc = inspect.getdoc(method) or ""

                                try:
                                    method_sig = inspect.signature(method)
                                    method_type_hints = get_type_hints(method)
                                    return_type_hint = method_type_hints.get(
                                        "return", Any
                                    )
                                    method_return_type = format_type(
                                        return_type_hint, {}
                                    )
                                except Exception:
                                    method_return_type = "Any"

                                methods.append(
                                    {
                                        "name": method_name,
                                        "doc": method_doc.split("\n")[0]
                                        if method_doc
                                        else "",
                                        "return_type": method_return_type,
                                    }
                                )

                        functions.append(
                            {
                                "name": name,
                                "type": "class",
                                "doc": doc,
                                "parameters": parameters,
                                "methods": methods,
                                "models": model_schemas,
                            }
                        )
                except Exception:
                    functions.append(
                        {
                            "name": name,
                            "type": "class",
                            "doc": doc,
                            "parameters": [],
                            "methods": [],
                            "models": {},
                        }
                    )

    return sorted(functions, key=lambda x: x["name"])


def format_parameters(params: List[Dict[str, Any]]) -> Table:
    """Format parameters into a rich Table."""
    table = Table(
        show_header=True, header_style="bold magenta", title="Function Parameters"
    )
    table.add_column("Parameter", style="cyan", justify="left")
    table.add_column("Type", style="green", justify="left")
    table.add_column("Required", style="yellow", justify="center", width=10)
    table.add_column("Default", style="blue", justify="left")

    for param in params:
        required = "[green][OK][/green]" if param["required"] else "[red][FAIL][/red]"
        default = param["default"] if param["default"] else "[dim]-[/dim]"
        table.add_row(param["name"], param["type"], required, default)

    return table


def format_model(schema: List[Dict[str, Any]]) -> Table:
    """Format a model schema into a rich Table."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", justify="left")
    table.add_column("Type", style="green", justify="left")
    table.add_column("Required", style="yellow", justify="center", width=10)
    table.add_column("Default", style="blue", justify="left")
    table.add_column("Description", style="white", justify="left")

    for field in schema:
        required = "[green][OK][/green]" if field["required"] else "[red][FAIL][/red]"
        default = (
            str(field["default"]) if field["default"] is not None else "[dim]-[/dim]"
        )
        table.add_row(
            field["name"], field["type"], required, default, field["description"]
        )

    return table


def create_function_tree(
    functions: List[Dict[str, Any]], category: str, full_detail: bool = True
) -> Tree:
    """Create a tree structure for functions and classes in a category."""
    tree = Tree(f"[bold blue]{category}")

    if not functions:
        tree.add(
            "[yellow]No public functions or classes available in this module[/yellow]"
        )
        return tree

    for func in functions:
        if func.get("type") == "class":
            func_name = (
                f"[bold magenta]{func['name']}[/bold magenta] [dim](class)[/dim]"
            )
        elif func.get("type") == "method":
            class_name = func.get("class_name", "")
            func_name = f"[bold magenta]{class_name}.{func['name']}[/bold magenta] -> [green]{func.get('return_type', 'Any')}"
        else:
            func_name = f"[bold cyan]{func['name']}[/bold cyan] -> [green]{func.get('return_type', 'Any')}"

        if not full_detail:
            tree.add(func_name)
            continue

        func_tree = tree.add(func_name)

        if func["doc"]:
            parts = func["doc"].split("Example:")
            description = parts[0].strip()
            example = parts[1].strip() if len(parts) > 1 else None

            description_lines = [line.strip() for line in description.split("\n")]
            description = "\n".join(line for line in description_lines if line)

            func_tree.add(
                Panel(
                    Text(description, style="white"),
                    title="Description",
                    border_style="blue",
                )
            )

            if example:
                example_lines = [line.strip() for line in example.split("\n")]
                example = "\n".join(line for line in example_lines if line)
                func_tree.add(
                    Panel(
                        Syntax(example, "python", theme="monokai"),
                        title="Example",
                        border_style="green",
                    )
                )

        if func["parameters"]:
            if func.get("type") == "class":
                param_title = "__init__ Parameters"
            elif func.get("type") == "method":
                param_title = "Method Parameters"
            else:
                param_title = "Parameters"

            func_tree.add(
                Panel(
                    format_parameters(func["parameters"]),
                    title=param_title,
                    border_style="yellow",
                )
            )

        if func.get("type") == "class" and func.get("methods"):
            methods_table = Table(
                show_header=True, header_style="bold magenta", title="Public Methods"
            )
            methods_table.add_column("Method", style="cyan", justify="left")
            methods_table.add_column("Returns", style="green", justify="left")
            methods_table.add_column("Description", style="white", justify="left")

            for method in func["methods"]:
                return_type = method.get("return_type", "Any")
                methods_table.add_row(method["name"], return_type, method["doc"])

            func_tree.add(
                Panel(
                    methods_table,
                    title="Methods",
                    border_style="green",
                )
            )

        if func.get("models"):
            model_tree = Tree("Models")
            func_tree.add(model_tree)
            for model_name, schema in func["models"].items():
                model_tree.add(
                    Panel(
                        format_model(schema),
                        title=f"[bold]{model_name}[/bold]",
                        border_style="cyan",
                    )
                )

    return tree


@app.command()
def api(
    module: Annotated[
        Optional[str],
        typer.Option("--module", "-m", help="Optional API module name to document"),
    ] = None,
    function: Annotated[
        Optional[str],
        typer.Option(
            "--function", "-f", help="The specific function to display details for"
        ),
    ] = None,
    list_modules: Annotated[
        bool, typer.Option("--list", "-l", help="List all available API modules")
    ] = False,
):
    """
    Display OFX API documentation in a beautiful format.

    Shows function signatures, descriptions, parameters, and examples
    for all available Red Team APIs.
    """
    discovered = discover_api_modules()
    modules = {name: info["path"] for name, info in discovered.items()}
    descriptions = {name: info["description"] for name, info in discovered.items()}

    if list_modules:
        console.print("\n[bold blue]Available API Modules:[/bold blue]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Module", style="cyan", no_wrap=True)
        table.add_column("Description", style="green")

        for mod_name in sorted(modules.keys()):
            table.add_row(mod_name, descriptions.get(mod_name, ""))

        console.print(table)
        console.print(f"\n[dim]Total: {len(modules)} modules[/dim]")
        console.print(
            "\nUse [cyan]--module MODULE[/cyan] to view detailed documentation"
        )
        return

    if not module:
        console.print("\n[yellow]No module specified.[/yellow]")
        console.print("\nUse one of the following options:")
        console.print(
            "  • [cyan]--list[/cyan] or [cyan]-l[/cyan] to list all available modules"
        )
        console.print(
            "  • [cyan]--module MODULE[/cyan] or [cyan]-m MODULE[/cyan] to view specific module documentation"
        )
        console.print("\nExample:")
        console.print("  [dim]$ ofx docs api --list[/dim]")
        console.print("  [dim]$ ofx docs api --module webshell[/dim]")
        return

    imported_modules = {}
    if module not in modules:
        console.print(f"[red]Error:[/red] Module '{module}' not found")
        console.print(f"\nAvailable modules: {', '.join(sorted(modules.keys()))}")
        console.print("\nUse [cyan]--list[/cyan] to see all modules with descriptions")
        raise typer.Exit(1)

    try:
        imported_modules[module] = importlib.import_module(modules[module])
    except ImportError as e:
        console.print(f"[red]Error:[/red] Failed to import module '{module}': {str(e)}")
        raise typer.Exit(1)

    try:
        for mod_name, mod in imported_modules.items():
            functions = get_module_functions(mod)

            if function:
                if "." in function:
                    class_name, method_name = function.split(".", 1)

                    class_func = next(
                        (
                            f
                            for f in functions
                            if f["name"] == class_name and f.get("type") == "class"
                        ),
                        None,
                    )
                    if not class_func:
                        console.print(
                            f"[red]Error:[/red] Class '{class_name}' not found in module '{mod_name}'"
                        )
                        continue

                    cls = getattr(mod, class_name, None)
                    if not cls:
                        console.print(
                            f"[red]Error:[/red] Could not load class '{class_name}'"
                        )
                        continue

                    method_info = get_method_info(cls, method_name)
                    if not method_info:
                        console.print(
                            f"[red]Error:[/red] Method '{method_name}' not found in class '{class_name}'"
                        )
                        available_methods = [
                            m["name"] for m in class_func.get("methods", [])
                        ]
                        if available_methods:
                            console.print(
                                f"Available methods: {', '.join(available_methods)}"
                            )
                        continue

                    functions = [method_info]
                else:
                    functions = [f for f in functions if f["name"] == function]
                    if not functions:
                        console.print(
                            f"[red]Error:[/red] Function or class '{function}' not found in module '{mod_name}'"
                        )
                        continue

            show_details = function is not None or module is None

            tree = create_function_tree(
                functions, f"ofx.api.{mod_name}", full_detail=show_details
            )

            console.print(
                Panel(
                    f"API Documentation for [bold]ofx.api.{mod_name}[/bold]",
                    style="bold white on blue",
                )
            )
            console.print("\n")
            console.print(tree)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8888, "--port", "-p", help="Port to bind to"),
):
    """
    Serve the documentation using Python HTTP server.
    
    Serves pre-built static HTML/CSS/JS files.
    """
    try:
        package_dir = Path(__file__).parent.parent
        site_dir = package_dir / "data" / "site"
        
        index_file = site_dir / "index.html"
        if not index_file.exists():
            console.print(f"[red][ERROR] index.html not found in {site_dir}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[cyan]Documentation available at http://{host}:{port}[/cyan]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")
        
        # Create HTTP server handler
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(site_dir), **kwargs)
        
        # Start server
        with socketserver.TCPServer((host, port), Handler) as httpd:
            httpd.serve_forever()
        
    except KeyboardInterrupt:
        httpd.server_close()
        console.print("\n[yellow]Documentation server stopped[/yellow]")
    except OSError as e:
        if "Address already in use" in str(e):
            console.print(f"[red][ERROR] Port {port} is already in use[/red]")
            console.print(f"Try a different port: [cyan]ofx docs serve --port {port + 1}[/cyan]")
        else:
            console.print(f"[red][ERROR] Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red][ERROR] Error: {e}[/red]")
        raise typer.Exit(1)
