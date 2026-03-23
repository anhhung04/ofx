"""API documentation command for OFX."""

import importlib
import inspect
from pathlib import Path
from typing import (
    Annotated,
    Any,
    ForwardRef,
    Union,
    get_type_hints,
)

import typer
from pydantic import BaseModel

app = typer.Typer()


def discover_api_modules() -> dict[str, dict[str, str]]:
    """Auto-discover all API modules from ofx.api package."""
    try:
        api_package = importlib.import_module("ofx.api")
        api_file = api_package.__file__
        if not api_file:
            return {}

        api_path = Path(api_file).parent
        modules: dict[str, dict[str, str]] = {}

        for file in api_path.glob("*.py"):
            if file.name == "__init__.py":
                continue
            _try_register_module(f"ofx.api.{file.stem}", file.stem, modules)

        for subdir in api_path.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_") and (subdir / "__init__.py").exists():
                _try_register_module(f"ofx.api.{subdir.name}", subdir.name, modules, require_all=True)

        return modules
    except Exception:
        return {}


def _try_register_module(
    module_path: str, name: str, registry: dict, *, require_all: bool = False
) -> None:
    """Try to import and register an API module."""
    try:
        mod = importlib.import_module(module_path)
        if require_all and not hasattr(mod, "__all__"):
            return
        if hasattr(mod, "__all__") or any(
            not n.startswith("_") and callable(getattr(mod, n)) for n in dir(mod)
        ):
            doc = inspect.getdoc(mod) or f"{name.title()} utilities"
            registry[name] = {"path": module_path, "description": doc.split("\n")[0]}
    except Exception:
        pass


def format_type(type_hint: Any, model_registry: dict[str, Any]) -> str:
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
    model: Any, model_registry: dict[str, Any]
) -> list[dict[str, Any]]:
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


def _extract_params(sig: inspect.Signature, type_hints: dict, model_schemas: dict, *, skip: set[str] | None = None) -> list[dict[str, Any]]:
    """Extract parameter info from a function/method signature."""
    skip = skip or set()
    parameters = []
    for param_name, param in sig.parameters.items():
        if param_name in skip or param_name == "return":
            continue
        param_hint = type_hints.get(param_name, Any)
        param_type = format_type(param_hint, model_schemas)

        if param.kind == param.VAR_KEYWORD:
            parameters.append({"name": f"**{param_name}", "type": "Any", "default": "", "required": False})
        elif param.kind == param.VAR_POSITIONAL:
            parameters.append({"name": f"*{param_name}", "type": "Any", "default": "", "required": False})
        else:
            default = "" if param.default is param.empty else str(param.default)
            parameters.append({
                "name": param_name,
                "type": param_type,
                "default": default,
                "required": param.default is param.empty and param.kind != param.VAR_POSITIONAL,
            })
    return parameters


def _resolve_type_hints(func: Any) -> dict:
    """Safely resolve type hints for a callable."""
    try:
        return get_type_hints(func)
    except Exception:
        return getattr(func, "__annotations__", {})


def _normalize_doc_and_example(doc: str) -> tuple[str, str | None]:
    """Split docstring into normalized description and optional example."""
    parts = doc.split("Example:")
    description = "\n".join(
        line for line in (line.strip() for line in parts[0].strip().split("\n")) if line
    )
    example: str | None = None
    if len(parts) > 1:
        example = "\n".join(
            line for line in (line.strip() for line in parts[1].strip().split("\n")) if line
        )
    return description, example


def _print_data_directories(console: Any, base_data_dir: str, data_dir: str) -> None:
    from rich.panel import Panel

    console.print()
    console.print(
        Panel(
            f"[bold cyan]User Data:[/bold cyan] [dim]{base_data_dir}[/dim]\n"
            f"  workflows/    - Custom workflow definitions\n"
            f"  secrets/      - Secure credential storage\n"
            f"  secrets.enc   - Encrypted secrets store\n\n"
            f"[bold cyan]Built-in Data:[/bold cyan] [dim]{data_dir}[/dim]\n"
            f"  shellcode/    - Shellcode templates\n"
            f"  webshells/    - Webshell templates\n"
            f"  exploits/     - Exploit modules\n\n"
            f"[dim]Extend OFX by adding custom workflows and data files to these directories.[/dim]",
            title="[bold]📁 Data Directories[/bold]",
            border_style="cyan",
        )
    )
    console.print()


def _print_list_usage(console: Any) -> None:
    console.print("\n⚠️ No module specified.")
    console.print("\nUse one of the following options:")
    console.print("  • [cyan]--list[/cyan] or [cyan]-l[/cyan] to list all available modules")
    console.print(
        "  • [cyan]--module MODULE[/cyan] or [cyan]-m MODULE[/cyan] to view specific module documentation"
    )
    console.print("\nExample:")
    console.print("  [dim]$ ofx docs --list[/dim]")
    console.print("  [dim]$ ofx docs --module webshell[/dim]")


def _print_module_list(console: Any, modules: dict[str, str], descriptions: dict[str, str]) -> None:
    from rich.table import Table

    console.print("\n[bold blue]Available API Modules:[/bold blue]")
    table = Table(
        show_header=True,
        header_style="bold magenta",
        expand=True,
        border_style="cyan",
    )
    table.add_column("Module", style="cyan", no_wrap=True)
    table.add_column("Description", style="green")
    for mod_name in sorted(modules.keys()):
        table.add_row(mod_name, descriptions.get(mod_name, ""))
    console.print(table)
    console.print(f"\n[dim]Total: {len(modules)} modules[/dim]")
    console.print("\nUse [cyan]--module MODULE[/cyan] to view detailed documentation")


def get_method_info(cls, method_name: str) -> dict[str, Any] | None:
    """Get detailed information about a specific class method."""
    try:
        method = getattr(cls, method_name)
        if not callable(method):
            return None

        sig = inspect.signature(method)
        type_hints = _resolve_type_hints(method)
        model_schemas: dict = {}
        parameters = _extract_params(sig, type_hints, model_schemas, skip={"self", "cls"})

        return {
            "name": method_name,
            "type": "method",
            "doc": inspect.getdoc(method) or "",
            "parameters": parameters,
            "return_type": format_type(type_hints.get("return", Any), model_schemas),
            "models": model_schemas,
            "class_name": cls.__name__,
        }
    except Exception:
        return None


def get_module_functions(module) -> list[dict[str, Any]]:
    """Get all public functions from a module with their documentation."""
    functions = []

    all_names = getattr(module, "__all__", None)

    func_lookup = dict(inspect.getmembers(module, inspect.isfunction))
    class_lookup = dict(inspect.getmembers(module, inspect.isclass))

    if all_names is not None:
        for name in all_names:
            if name in func_lookup:
                func = func_lookup[name]
                sig = inspect.signature(func)
                type_hints = _resolve_type_hints(func)
                model_schemas: dict = {}
                parameters = _extract_params(sig, type_hints, model_schemas)

                functions.append({
                    "name": name,
                    "type": "function",
                    "doc": inspect.getdoc(func) or "",
                    "parameters": parameters,
                    "return_type": format_type(type_hints.get("return", Any), model_schemas),
                    "models": model_schemas,
                })

            elif name in class_lookup:
                cls = class_lookup[name]
                doc = inspect.getdoc(cls) or ""

                try:
                    if hasattr(cls, "__init__"):
                        init_func = cls.__init__
                        sig = inspect.signature(init_func)
                        type_hints = _resolve_type_hints(init_func)
                        model_schemas = {}
                        parameters = _extract_params(sig, type_hints, model_schemas, skip={"self"})

                        methods = []
                        for method_name, method in inspect.getmembers(cls, inspect.isfunction):
                            if method_name.startswith("_") and method_name not in ("__init__", "__call__"):
                                continue
                            if method_name == "__init__":
                                continue
                            method_doc = inspect.getdoc(method) or ""
                            try:
                                inspect.signature(method)
                                method_type_hints = get_type_hints(method)
                                method_return_type = format_type(method_type_hints.get("return", Any), {})
                            except Exception:
                                method_return_type = "Any"
                            methods.append({
                                "name": method_name,
                                "doc": method_doc.split("\n")[0] if method_doc else "",
                                "return_type": method_return_type,
                            })

                        functions.append({
                            "name": name,
                            "type": "class",
                            "doc": doc,
                            "parameters": parameters,
                            "methods": methods,
                            "models": model_schemas,
                        })
                except Exception:
                    functions.append({
                        "name": name, "type": "class", "doc": doc,
                        "parameters": [], "methods": [], "models": {},
                    })

    return sorted(functions, key=lambda x: x["name"])


def format_parameters(params: list[dict[str, Any]]):
    """Format parameters into a rich Table."""
    from rich.table import Table

    table = Table(
        show_header=True,
        header_style="bold magenta",
        title="Function Parameters",
        expand=True,
        border_style="cyan",
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


def format_model(schema: list[dict[str, Any]]):
    """Format a model schema into a rich Table."""
    from rich.table import Table

    table = Table(
        show_header=True, header_style="bold magenta", expand=True, border_style="cyan"
    )
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
    functions: list[dict[str, Any]], category: str, full_detail: bool = True
):
    """Create a tree structure for functions and classes in a category."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text
    from rich.tree import Tree

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
            description, example = _normalize_doc_and_example(func["doc"])

            func_tree.add(
                Panel(
                    Text(description, style="white"),
                    title="Description",
                    border_style="blue",
                )
            )

            if example:
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
            from rich.table import Table

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
def show_api(
    module: Annotated[
        str,
        typer.Option("--module", "-m", help="Optional API module name to document"),
    ] = "",
    function: Annotated[
        str,
        typer.Option(
            "--function", "-f", help="The specific function to display details for"
        ),
    ] = "",
    list_modules: Annotated[
        bool, typer.Option("--list", "-l", help="List all available API modules")
    ] = False,
):
    """
    Display OFX API documentation in a beautiful format.

    Shows function signatures, descriptions, parameters, and examples
    for all available Red Team APIs.
    """
    from rich.panel import Panel

    from ofx.settings import BASE_DATA_DIR, DATA_DIR, get_console

    console = get_console()

    if not module and not list_modules:
        _print_data_directories(console, str(BASE_DATA_DIR), str(DATA_DIR))

    discovered = discover_api_modules()
    modules = {name: info["path"] for name, info in discovered.items()}
    descriptions = {name: info["description"] for name, info in discovered.items()}

    if list_modules:
        _print_module_list(console, modules, descriptions)
        return

    if not module:
        _print_list_usage(console)
        return

    imported_modules = {}
    if module not in modules:
        console.print(f"❌ Module '{module}' not found")
        console.print(f"\nAvailable modules: {', '.join(sorted(modules.keys()))}")
        console.print("\nUse [cyan]--list[/cyan] to see all modules with descriptions")
        raise typer.Exit(1)

    try:
        imported_modules[module] = importlib.import_module(modules[module])
    except ImportError as e:
        console.print(f"❌ Failed to import module '{module}': {str(e)}")
        raise typer.Exit(1) from e

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
                            f"❌ Class '{class_name}' not found in module '{mod_name}'"
                        )
                        continue

                    cls = getattr(mod, class_name, None)
                    if not cls:
                        console.print(f"❌ Could not load class '{class_name}'")
                        continue

                    method_info = get_method_info(cls, method_name)
                    if not method_info:
                        console.print(
                            f"❌ Method '{method_name}' not found in class '{class_name}'"
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
                            f"❌ Function or class '{function}' not found in module '{mod_name}'"
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
        console.print(f"❌ {str(e)}")
        raise typer.Exit(1) from e
