import typer
import inspect
from typing import (
    List,
    Dict,
    Any,
    get_type_hints,
    ForwardRef,
    Union,
    Annotated,
    Optional,
)
import importlib
from pathlib import Path
from rich.tree import Tree
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.console import Console
from rich.syntax import Syntax
from pydantic import BaseModel

app = typer.Typer()

NAME = "api"
HELP = "Interact with the OFX API."


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

    model_registry[model.__name__] = []  # Placeholder to prevent recursion loops

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


def get_module_functions(module) -> List[Dict[str, Any]]:
    """Get all public functions from a module with their documentation."""
    functions = []

    # Get functions from __all__ if available
    all_names = getattr(module, "__all__", None)

    # Create lookup of functions in the module
    func_lookup = dict(inspect.getmembers(module, inspect.isfunction))

    # If __all__ is defined, use only functions from __all__
    if all_names is not None:
        for name in all_names:
            if name in func_lookup:
                func = func_lookup[name]
                doc = inspect.getdoc(func) or ""
                sig = inspect.signature(func)
                try:
                    type_hints = get_type_hints(func)
                except Exception:
                    # If type hints can't be resolved, fall back to annotations
                    type_hints = getattr(func, "__annotations__", {})

                # Process parameters
                parameters = []
                model_schemas = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "return":
                        continue

                    param_hint = type_hints.get(param_name, Any)
                    param_type = format_type(param_hint, model_schemas)

                    # Special handling for **kwargs
                    if param.kind == param.VAR_KEYWORD:
                        parameters.append(
                            {
                                "name": f"**{param_name}",
                                "type": "Any",
                                "default": "",
                                "required": False,
                            }
                        )
                    # Special handling for *args
                    elif param.kind == param.VAR_POSITIONAL:
                        parameters.append(
                            {
                                "name": f"*{param_name}",
                                "type": "Any",
                                "default": "",
                                "required": False,
                            }
                        )
                    # Normal parameters
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

                # Get return type
                return_type_hint = type_hints.get("return", Any)
                return_type = format_type(return_type_hint, model_schemas)

                functions.append(
                    {
                        "name": name,
                        "doc": doc,
                        "parameters": parameters,
                        "return_type": return_type,
                        "models": model_schemas,
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
        required = "[green]✓[/green]" if param["required"] else "[red]✗[/red]"
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
        required = "[green]✓[/green]" if field["required"] else "[red]✗[/red]"
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
    """Create a tree structure for functions in a category."""
    tree = Tree(f"[bold blue]{category}")

    if not functions:
        tree.add("[yellow]No public functions available in this module[/yellow]")
        return tree

    for func in functions:
        # Create function node
        func_name = (
            f"[bold cyan]{func['name']}[/bold cyan] -> [green]{func['return_type']}"
        )

        if not full_detail:
            tree.add(func_name)
            continue

        func_tree = tree.add(func_name)

        # Add description
        if func["doc"]:
            # Split into description and examples
            parts = func["doc"].split("Example:")
            description = parts[0].strip()
            example = parts[1].strip() if len(parts) > 1 else None

            # Clean up the description by removing indentation
            description_lines = [line.strip() for line in description.split("\n")]
            description = "\n".join(line for line in description_lines if line)

            # Add description
            func_tree.add(
                Panel(
                    Text(description, style="white"),
                    title="Description",
                    border_style="blue",
                )
            )

            # Add example if present
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

        # Add parameters
        if func["parameters"]:
            func_tree.add(
                Panel(
                    format_parameters(func["parameters"]),
                    title="Parameters",
                    border_style="yellow",
                )
            )

        # Add models
        if func["models"]:
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
def docs(
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
    List documentation for the OFX API in a beautiful format.

    Displays function signatures, descriptions, parameters, and examples in a rich
    tree structure. Can optionally save the output to a file.
    """
    console = Console()

    # Import all API modules
    modules = {
        "creds": "ofx.api.creds",
        "file": "ofx.api.file",
        "http": "ofx.api.http",
        "strings": "ofx.api.strings",
    }

    descriptions = {
        "creds": "Credential and host management operations",
        "file": "File handling and path manipulation utilities",
        "http": "HTTP request and response handling",
        "strings": "String manipulation and formatting utilities",
    }

    if list_modules:
        console.print("\n[bold blue]Available API Modules:[/bold blue]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Module", style="cyan")
        table.add_column("Description", style="green")

        for mod_name in sorted(modules.keys()):
            table.add_row(mod_name, descriptions[mod_name])

        console.print(table)
        console.print(
            "\nUse [cyan]--module[/cyan] option to view detailed documentation for a specific module"
        )
        return

    imported_modules = {}
    for name, module_path in modules.items():
        try:
            imported_modules[name] = importlib.import_module(module_path)
        except ImportError as e:
            console.print(
                f"[red]Error:[/red] Failed to import module '{name}': {str(e)}"
            )
            raise typer.Exit(1)

    if module:
        if module not in modules:
            console.print(f"[red]Error:[/red] Module '{module}' not found")
            raise typer.Exit(1)
        imported_modules = {module: imported_modules[module]}

    try:
        for mod_name, mod in imported_modules.items():
            functions = get_module_functions(mod)

            if function:
                functions = [f for f in functions if f["name"] == function]
                if not functions:
                    console.print(
                        f"[red]Error:[/red] Function '{function}' not found in module '{mod_name}'"
                    )
                    continue

            # Show full detail if a function is specified, or if no module is specified.
            # Otherwise (module specified, no function), show summary.
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
