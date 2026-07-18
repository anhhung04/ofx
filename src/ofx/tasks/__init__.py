"""OFX Tasks — pre-built security tool wrappers with structured output.

Usage in workflows::

    steps:
      - task: nmap
        with:
          target: "192.168.1.0/24"
          ports: "1-1000"
          version_detection: true

Programmatic usage::

    from ofx.tasks import TaskRegistry

    nmap = TaskRegistry.create("nmap")
    cmd, out_file = nmap.build_command("192.168.1.1", ports="1-1000")
"""

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import (
    OUTPUT_TYPE_MAP,
    Certificate,
    Confidence,
    Domain,
    Exploit,
    Ip,
    OutputType,
    Port,
    Record,
    Severity,
    Subdomain,
    Tag,
    Url,
    UserAccount,
    Vulnerability,
)
from ofx.tasks.registry import TaskRegistry

__all__ = [
    "Task",
    "OptDef",
    "TaskRegistry",
    "OutputType",
    "OUTPUT_TYPE_MAP",
    "Ip",
    "Port",
    "Subdomain",
    "Url",
    "Vulnerability",
    "Tag",
    "Record",
    "Domain",
    "Certificate",
    "Exploit",
    "UserAccount",
    "Severity",
    "Confidence",
]
