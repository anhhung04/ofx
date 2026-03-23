import json
import logging
from pathlib import Path
from typing import Annotated, Any

import typer

from ofx.commands.ui_helpers import print_success
from ofx.settings import BASE_DATA_DIR, ensure_dir, get_console, settings

NAME = "dump"
HELP = "Dump the workflow configuration and outputs."

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

logger = logging.getLogger(settings.app_branding)


def get_property_type(
    prop_info: dict[str, Any], definitions: dict[str, Any] = None
) -> str:
    """Extract property type from schema information."""
    if definitions is None:
        definitions = {}
    if "type" in prop_info:
        t = prop_info["type"]
        if t == "any":
            return "Any"
        if t == "object":
            if "additionalProperties" in prop_info:
                add_props = prop_info["additionalProperties"]
                if isinstance(add_props, dict):
                    if "$ref" in add_props:
                        ref_name = add_props["$ref"].split("/")[-1]
                        value_type = get_property_type(add_props, definitions)
                        return f"dict[str, {value_type}]"
                    else:
                        return "dict[str, Any]"
                elif add_props is True:
                    return "dict[str, Any]"
                else:
                    return "dict[str, Any]"
            return "dict[str, Any]"
        if t == "array":
            if "items" in prop_info:
                item_type = get_property_type(prop_info["items"], definitions)
                return f"array[{item_type}]"
            return "array"
        return t
    elif "anyOf" in prop_info:
        types = [get_property_type(t, definitions) for t in prop_info["anyOf"]]
        return " | ".join(types)
    elif "$ref" in prop_info:
        ref_name = prop_info["$ref"].split("/")[-1]
        return ref_name
    return "Any"


def get_property_default(prop_info: dict[str, Any]) -> str:
    """Get the default value of a property as a string."""
    if "default" in prop_info:
        default_value = prop_info["default"]
        if default_value is None:
            return "None"
        elif isinstance(default_value, str) and not default_value:
            return '""'
        else:
            return str(default_value)
    return ""


def extract_schema_properties(
    schema: dict[str, Any],
    parent_name: str = "",
    properties_list: list[dict[str, str]] = None,
    definitions: dict[str, Any] = None,
) -> list[dict[str, str]]:
    """Extract all properties from a schema into a flat list,"""
    if definitions is None:
        definitions = {}
    if properties_list is None:
        properties_list = []
    if not definitions and "$defs" in schema:
        definitions = schema.get("$defs", {})

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for prop_name, prop_info in properties.items():
        full_name = f"{parent_name}.{prop_name}" if parent_name else prop_name

        prop_type = get_property_type(prop_info, definitions)
        prop_required = "Yes" if prop_name in required else "No"
        prop_default = get_property_default(prop_info)
        prop_desc = prop_info.get("description", "")

        if "enum" in prop_info:
            enum_values = ", ".join([f"'{v}'" for v in prop_info["enum"]])
            prop_desc += f" (Values: {enum_values})"

        properties_list.append(
            {
                "name": full_name,
                "type": prop_type,
                "required": prop_required,
                "default": prop_default,
                "description": prop_desc,
            }
        )

        if "$ref" in prop_info and definitions:
            ref_name = prop_info["$ref"].split("/")[-1]
            ref_schema = definitions.get(ref_name)
            if ref_schema:
                extract_schema_properties(
                    ref_schema, full_name, properties_list, definitions
                )

        elif prop_info.get("type") == "array" and "items" in prop_info:
            items_info = prop_info["items"]
            if "$ref" in items_info and definitions:
                ref_name = items_info["$ref"].split("/")[-1]
                ref_schema = definitions.get(ref_name)
                if ref_schema:
                    extract_schema_properties(
                        ref_schema, f"{full_name}[]", properties_list, definitions
                    )

        elif prop_info.get("type") == "object" and "properties" in prop_info:
            extract_schema_properties(
                prop_info, full_name, properties_list, definitions
            )

        elif prop_info.get("type") == "object" and "additionalProperties" in prop_info:
            add_props = prop_info["additionalProperties"]
            if isinstance(add_props, dict) and "$ref" in add_props and definitions:
                ref_name = add_props["$ref"].split("/")[-1]
                ref_schema = definitions.get(ref_name)
                if ref_schema:
                    extract_schema_properties(
                        ref_schema, full_name, properties_list, definitions
                    )

    return properties_list


def display_schema_tree(schema: dict[str, Any], title: str, console) -> None:
    """Display the schema properties in a hierarchical tree format."""
    from rich.tree import Tree

    tree = Tree(f"[bold]{title}[/]")
    definitions = schema.get("$defs", {})

    def add_prop(node, prop_name, prop_info, required_list, parent_name=""):
        full_name = f"{parent_name}.{prop_name}" if parent_name else prop_name
        prop_type = get_property_type(prop_info, definitions)
        prop_required = "Yes" if prop_name in required_list else "No"
        prop_default = get_property_default(prop_info)
        prop_desc = prop_info.get("description", "")
        if "enum" in prop_info:
            enum_values = ", ".join([f"'{v}'" for v in prop_info["enum"]])
            prop_desc += f" (Values: {enum_values})"
        label = f"[cyan]{prop_name}[/]: [green]{prop_type}[/] (Req: {prop_required}, Def: {prop_default})"
        if prop_desc:
            label += f" - {prop_desc}"
        child_node = node.add(label)

        if "$ref" in prop_info and definitions:
            ref_name = prop_info["$ref"].split("/")[-1]
            ref_schema = definitions.get(ref_name)
            if ref_schema:
                add_schema(child_node, ref_schema, full_name)
        elif prop_info.get("type") == "array" and "items" in prop_info:
            items_info = prop_info["items"]
            if "$ref" in items_info and definitions:
                ref_name = items_info["$ref"].split("/")[-1]
                ref_schema = definitions.get(ref_name)
                if ref_schema:
                    add_schema(child_node, ref_schema, f"{full_name}[]")
            elif items_info.get("type") == "object":
                add_schema(child_node, items_info, f"{full_name}[]")
        elif prop_info.get("type") == "object":
            if "properties" in prop_info:
                add_schema(child_node, prop_info, full_name)
            elif "additionalProperties" in prop_info:
                add_props = prop_info["additionalProperties"]
                if isinstance(add_props, dict) and "$ref" in add_props and definitions:
                    ref_name = add_props["$ref"].split("/")[-1]
                    ref_schema = definitions.get(ref_name)
                    if ref_schema:
                        add_schema(child_node, ref_schema, full_name)

    def add_schema(node, schema, parent_name=""):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for prop_name, prop_info in properties.items():
            add_prop(node, prop_name, prop_info, required, parent_name)

    add_schema(tree, schema)
    console.print(tree)


@app.command("flow")
def dump_workflow():
    """
    Display the OFX workflow model schema as a rich, human-readable tree.

    This command prints a detailed tree of all workflow properties, including nested fields, types, required status, default values, and descriptions. Useful for exploring the structure and requirements of OFX workflow definitions.
    """
    console = get_console()
    from ofx.models.workflow import Workflow

    schema = Workflow.model_json_schema()

    console.print("\n[bold]Workflow Model Schema[/]\n", style="cyan")
    display_schema_tree(schema, "Workflow Properties", console)


@app.command("job")
def dump_job():
    """
    Display the OFX job model schema as a rich, human-readable tree.

    This command prints a detailed tree of all job properties, including nested fields, types, required status, default values, and descriptions. Useful for exploring the structure and requirements of OFX job definitions.
    """
    console = get_console()
    from ofx.models.job import Job

    schema = Job.model_json_schema()

    console.print("\n[bold]Job Model Schema[/]\n", style="cyan")
    display_schema_tree(schema, "Job Properties", console)


@app.command("step")
def dump_step():
    """
    Display the OFX step model schema as a rich, human-readable tree.

    This command prints a detailed tree of all step properties, including nested fields, types, required status, default values, and descriptions. Useful for exploring the structure and requirements of OFX step definitions.
    """
    console = get_console()
    from ofx.models.step import Step

    schema = Step.model_json_schema()

    console.print("\n[bold]Step Model Schema[/]\n", style="cyan")
    display_schema_tree(schema, "Step Properties", console)


@app.command("schema")
def export_schema(
    output: Annotated[
        str,
        typer.Option(
            "-o",
            "--output",
            help="Output file path for the JSON schema (default: workflow_schema.json in data dir)",
        ),
    ] = "",
):
    """
    Export the OFX workflow model schema as a JSON file.

    By default, writes the full JSON schema for workflows to 'workflow_schema.json' in the data directory. You can specify a custom output path with -o/--output. This schema is suitable for validation, tooling, or integration with editors and CI systems.
    """

    from ofx.models.workflow import Workflow

    if not output:
        output = (ensure_dir(BASE_DATA_DIR) / "workflow_schema.json").as_posix()
    output_path = Path(output)
    schema = Workflow.model_json_schema()
    if not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2))

    print_success(
        "Schema Export",
        "Schema exported successfully",
        details={
            "File": str(output_path),
            "Hint": "Use this schema for validation and IDE support",
        },
    )
