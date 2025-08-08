import logging
from typing import Type
from typer import Exit

logger = logging.getLogger("ofx")


class BaseCommandHandler:
    async def run(self):
        raise NotImplementedError("Subclasses should implement this method.")


async def command_handler(HandlerClass: Type, *args, **kwargs):
    """
    Decorator to handle async commands with a specific handler class.

    Args:
        HandlerClass (Type): The handler class to instantiate and run.
        *args: Positional arguments for the handler.
        **kwargs: Keyword arguments for the handler.
    """
    try:
        handler = HandlerClass(*args, **kwargs)
        await handler.run()
    except Exception as e:
        logger.error(e)
        raise Exit(code=1)
