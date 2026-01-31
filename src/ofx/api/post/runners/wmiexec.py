"""WMIExec-based post-exploitation runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..base import PostRunnerBase
from ..registry import RunnerRegistry

__all__ = ["PostWMIExec"]


@RunnerRegistry.register("wmiexec")
@dataclass
class PostWMIExec(PostRunnerBase):
    """Post-exploitation runner over WMI exec (Impacket).
    
    Requires the optional `impacket` package.
    
    Args:
        target: Target hostname or IP
        username: Windows username
        password: Windows password
        domain: Windows domain (optional)
        
    Example:
        >>> wmi = PostWMIExec("192.168.1.100", "admin", "P@ssw0rd!", domain="CORP")
        >>> wmi.run("whoami")
        'corp\\admin'
    """
    
    target: str
    username: str
    password: str
    domain: str = ""
    _wmi_module: Any = field(default=None, init=False, repr=False)
    
    def __post_init__(self) -> None:
        try:
            from impacket.examples import wmiexec as wmiexec_module
            self._wmi_module = wmiexec_module
        except Exception as exc:  # pragma: no cover - import gate
            raise ImportError(
                "WMIExec support requires the 'impacket' package. "
                "Install it with: pip install impacket"
            ) from exc
    
    def run(self, command: str) -> str:
        """Execute a command via WMI exec.
        
        Args:
            command: Windows command to execute
            
        Returns:
            Command output
        """
        executor = self._wmi_module.WMIEXEC(
            command, self.username, self.password, self.domain, self.target
        )
        return executor.run()
