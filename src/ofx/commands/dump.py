import typer
import json
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table

from ofx.models.workflow import *
from ofx.models.job import *
from ofx.models.step import *


NAME = "dump"
HELP = "Dump the workflow configuration and outputs."

app = typer.Typer()


def get_property_type(prop_info: Dict[str, Any]) -> str:
    """Extract property type from schema information."""
    if "type" in prop_info:
        return prop_info["type"]
    elif "anyOf" in prop_info:
        types = [t.get("type", "any") for t in prop_info["anyOf"]]
        return " | ".join(types)
    elif "$ref" in prop_info:
        ref_name = prop_info["$ref"].split("/")[-1]
        return ref_name
    return "any"


def get_property_default(prop_info: Dict[str, Any]) -> str:
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
    schema: Dict[str, Any],
    parent_name: str = "",
    properties_list: List[Dict[str, str]] = None,
    definitions: Dict[str, Any] = None,
) -> List[Dict[str, str]]:
    """
    Extract all properties from a schema into a flat list,
    using dot notation for nested properties.
    """
    if properties_list is None:
        properties_list = []

    if definitions is None and "$defs" in schema:
        definitions = schema.get("$defs", {})

    # Process properties
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for prop_name, prop_info in properties.items():
        full_name = f"{parent_name}.{prop_name}" if parent_name else prop_name

        # Basic property info
        prop_type = get_property_type(prop_info)
        prop_required = "Yes" if prop_name in required else "No"
        prop_default = get_property_default(prop_info)
        prop_desc = prop_info.get("description", "")

        # Handle enum values
        if "enum" in prop_info:
            enum_values = ", ".join([f"'{v}'" for v in prop_info["enum"]])
            prop_desc += f" (Values: {enum_values})"

        # Add to list
        properties_list.append(
            {
                "name": full_name,
                "type": prop_type,
                "required": prop_required,
                "default": prop_default,
                "description": prop_desc,
            }
        )

        # Handle reference to another schema
        if "$ref" in prop_info and definitions:
            ref_name = prop_info["$ref"].split("/")[-1]
            ref_schema = definitions.get(ref_name)
            if ref_schema:
                extract_schema_properties(
                    ref_schema, full_name, properties_list, definitions
                )

        # Handle array items
        elif prop_info.get("type") == "array" and "items" in prop_info:
            items_info = prop_info["items"]
            if "$ref" in items_info and definitions:
                ref_name = items_info["$ref"].split("/")[-1]
                ref_schema = definitions.get(ref_name)
                if ref_schema:
                    extract_schema_properties(
                        ref_schema, f"{full_name}[]", properties_list, definitions
                    )

        # Handle nested object
        elif prop_info.get("type") == "object" and "properties" in prop_info:
            extract_schema_properties(
                prop_info, full_name, properties_list, definitions
            )

        # Handle dictionary
        elif prop_info.get("type") == "object" and "additionalProperties" in prop_info:
            add_props = prop_info["additionalProperties"]
            if isinstance(add_props, dict) and "$ref" in add_props and definitions:
                ref_name = add_props["$ref"].split("/")[-1]
                ref_schema = definitions.get(ref_name)
                if ref_schema:
                    dict_key = f"{full_name}[key]"
                    extract_schema_properties(
                        ref_schema, dict_key, properties_list, definitions
                    )

    return properties_list


def display_schema_table(schema: Dict[str, Any], title: str, console: Console) -> None:
    """
    Display the schema properties in a tabular format with dot notation for nested objects.
    """
    properties_list = extract_schema_properties(schema)

    # Create the table
    table = Table(title=title, expand=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Type", style="green")
    table.add_column("Required", style="red", justify="center")
    table.add_column("Default", style="yellow")
    table.add_column("Description", style="blue", max_width=60, overflow="fold")

    # Add rows to the table
    for prop in properties_list:
        table.add_row(
            prop["name"],
            prop["type"],
            prop["required"],
            prop["default"],
            prop["description"],
        )

    # Display the table
    console.print(table)


@app.command("flow")
def dump_workflow():
    """
    Dump the workflow model schema in JSON or rich formatted table.

    Args:
        format: Output format - 'json' for raw JSON schema or 'table' for formatted table
    """
    schema = Workflow.model_json_schema()
    console = Console()

    console.print("\n[bold]Workflow Model Schema[/]\n", style="cyan")
    display_schema_table(schema, "Workflow Properties", console)
