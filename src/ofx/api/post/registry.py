"""Registry pattern for post-exploitation runner discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Type

if TYPE_CHECKING:
    from .base import PostRunnerBase

__all__ = ["RunnerRegistry"]


class RunnerRegistry:
    """Registry for post-exploitation runners.
    
    Provides dynamic registration and discovery of runner implementations.
    Use the @register decorator to add new runner types.
    
    Example:
        >>> @RunnerRegistry.register("custom")
        ... class CustomRunner(PostRunnerBase):
        ...     def run(self, command: str) -> str:
        ...         return custom_execute(command)
        ...
        >>> RunnerRegistry.list_runners()
        ['ssh', 'webshell', 'winrm', 'smbexec', 'wmiexec', 'custom']
        >>> runner = RunnerRegistry.create("custom", host="target")
    """
    
    _runners: dict[str, Type[PostRunnerBase]] = {}
    
    @classmethod
    def register(cls, name: str) -> Callable[[Type[PostRunnerBase]], Type[PostRunnerBase]]:
        """Decorator to register a runner class.
        
        Args:
            name: Unique identifier for the runner type
            
        Returns:
            Decorator function
            
        Example:
            >>> @RunnerRegistry.register("myrunner")
            ... class MyRunner(PostRunnerBase):
            ...     pass
        """
        def decorator(runner_cls: Type[PostRunnerBase]) -> Type[PostRunnerBase]:
            cls._runners[name] = runner_cls
            return runner_cls
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type[PostRunnerBase] | None:
        """Get a runner class by name.
        
        Args:
            name: Runner identifier
            
        Returns:
            Runner class or None if not found
        """
        return cls._runners.get(name)
    
    @classmethod
    def list_runners(cls) -> list[str]:
        """List all registered runner names.
        
        Returns:
            List of runner identifiers
        """
        return list(cls._runners.keys())
    
    @classmethod
    def create(cls, name: str, **kwargs) -> PostRunnerBase:
        """Factory method to instantiate a runner by name.
        
        Args:
            name: Runner identifier
            **kwargs: Arguments passed to runner constructor
            
        Returns:
            Instantiated runner
            
        Raises:
            ValueError: If runner name is not registered
            
        Example:
            >>> runner = RunnerRegistry.create("ssh", host="192.168.1.1", user="root")
        """
        runner_cls = cls.get(name)
        if runner_cls is None:
            available = ", ".join(cls.list_runners()) or "none"
            raise ValueError(f"Unknown runner: {name!r}. Available: {available}")
        return runner_cls(**kwargs)
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a runner from the registry.
        
        Args:
            name: Runner identifier to remove
        """
        cls._runners.pop(name, None)
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered runners."""
        cls._runners.clear()
