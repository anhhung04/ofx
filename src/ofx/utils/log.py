import logging
import time
from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

class RightAlignedHandler(RichHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_stream_block = False

    def emit(self, record):
        if not self.console:
            return super().emit(record)

        full_raw_msg = self.format(record)
        lines = full_raw_msg.splitlines()

        for raw_line in lines:
            line_plain = Text.from_markup(raw_line).plain
            
            is_header = any(x in line_plain for x in ["===stdout===", "===stderr==="])
            is_footer = "============" in line_plain

            if is_header:
                self.in_stream_block = True
                self._print_with_metadata(raw_line, line_plain, record.levelname)
                continue

            if is_footer:
                self.in_stream_block = False
                self._print_with_metadata(raw_line, line_plain, record.levelname)
                continue

            # Logic for content vs. normal logs
            if self.in_stream_block:
                # Content inside the block: No metadata, no highlight, no markup
                self.console.print(raw_line, highlight=False, markup=False)
            else:
                # Normal log outside blocks
                self._print_with_metadata(raw_line, line_plain, record.levelname)

    def _print_with_metadata(self, raw_line, plain_line, levelname):
        """Helper to pad and append Level | Time to the right."""
        timestamp = time.strftime("[%X]")
        metadata = f"{levelname} | {timestamp}"
        
        width = self.console.width
        padding_size = width - len(plain_line) - len(metadata) - 1
        
        if padding_size > 0:
            padding = " " * padding_size
            self.console.print(f"{raw_line}{padding}[dim]{metadata}[/dim]", markup=True)
        else:
            self.console.print(f"{raw_line} [dim]{metadata}[/dim]", markup=True)

def reload_logging_config(settings):
    from ofx.settings import RICH_THEME
    branding = settings.app_branding
    logger = logging.getLogger(branding)
    
    for handler in logger.handlers[:]:
        if handler.name == f"{branding}.console":
            logger.removeHandler(handler)

    console = Console(theme=RICH_THEME)
    log_handler = RightAlignedHandler(
        console=console,
        rich_tracebacks=settings.debug,
        show_time=False,
        show_level=False,
        markup=True
    )
    log_handler.set_name(f"{branding}.console")
    
    level = logging.DEBUG if settings.debug else logging.INFO
    logger.setLevel(level)
    logger.addHandler(log_handler)