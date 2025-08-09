import typer
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ofx.models.workflow import *
from ofx.models.job import *
from ofx.models.step import *


NAME = "dump"
HELP = "Dump the workflow configuration and outputs."

app = typer.Typer()


@app.command("flow")
def dump_workflow():
    print(Workflow.model_json_schema())
