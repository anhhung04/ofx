from async_typer import AsyncTyper
from ofx.commands.flow.run import FlowRunHandler
from ofx.utils.command import command_handler

app = AsyncTyper()

NAME = "flow"

HELP = "Manage and run workflows in the OFX system"


@app.async_command()
async def run(workflow_name: str):
    await command_handler(FlowRunHandler, workflow_name)
