"""Connector registry and auto-discovery system for webshell generators.

This module manages the registration and discovery of webshell connectors.
All connector implementations are in data/webshell/connectors/ for consistency
and user extensibility.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Optional

from ofx.data.webshell.connectors.base import WebshellConnector
from ofx.data.webshell.connectors.template import TemplateConnector
from ofx.settings import DATA_DIR, settings

logger = logging.getLogger(settings.app_branding)


class ConnectorRegistry:
    """Registry for managing webshell connectors.

    Maintains a registry of available connectors and provides methods
    for discovering, registering, and retrieving them.

    All connectors (built-in and user-defined) are discovered from
    data/webshell/connectors/ directory.
    """

    def __init__(self):
        """Initialize connector registry."""
        self._connectors: dict[str, type] = {}
        self._instances: dict[str, WebshellConnector] = {}
        self._user_connector_paths: list[Path] = []
        self._initial_discovery_done = False

    def register_connector_class(self, connector_class: type) -> None:
        """Register a connector class.

        Args:
            connector_class: Connector class (not instance)
        """
        temp_instance = connector_class()
        name = temp_instance.name

        self._connectors[name] = connector_class
        logger.debug(f"Registered connector: {name} ({connector_class.__name__})")

    def register_connector_instance(self, connector: WebshellConnector) -> None:
        """Register a connector instance directly.

        Useful for connectors that require initialization parameters.

        Args:
            connector: Initialized connector instance
        """
        self._instances[connector.name] = connector
        logger.debug(f"Registered connector instance: {connector.name}")

    def get_connector(self, name: str) -> WebshellConnector | None:
        """Get a connector by name.

        Returns a cached instance if available, otherwise creates a new one.

        Args:
            name: Connector name (e.g., 'template', 'remote-http')

        Returns:
            Connector instance or None if not found
        """        # Ensure discovery has happened
        if not self._initial_discovery_done:
            self.discover_connectors()
                # Check instance cache first
        if name in self._instances:
            return self._instances[name]

        # Create new instance from class
        if name in self._connectors:
            connector_class = self._connectors[name]
            instance = connector_class()
            self._instances[name] = instance
            return instance

        logger.warning(f"Connector '{name}' not found in registry")
        return None

    def get_available_connectors(self) -> list[WebshellConnector]:
        """Get all currently available connectors.

        Returns:
            List of connector instances that are available (dependencies met)
        """
        if not self._initial_discovery_done:
            self.discover_connectors()

        available = []

        # Check all registered classes
        for name, connector_class in self._connectors.items():
            if name not in self._instances:
                self._instances[name] = connector_class()

            connector = self._instances[name]
            if connector.is_available():
                available.append(connector)

        # Check registered instances
        for connector in self._instances.values():
            if connector.name not in self._connectors and connector.is_available():
                available.append(connector)

        return available

    def list_all_connectors(self) -> list[str]:
        """List all registered connector names.

        Returns:
            List of connector names
        """
        all_names = set(self._connectors.keys())
        all_names.update(self._instances.keys())
        return sorted(all_names)

    def add_user_connector_path(self, path: Path | str) -> None:
        """Add a directory to search for user connectors.

        Args:
            path: Directory path containing connector Python files
        """
        path = Path(path)
        if path.exists() and path.is_dir():
            self._user_connector_paths.append(path)
            logger.info(f"Added user connector path: {path}")
        else:
            logger.warning(f"Connector path does not exist: {path}")

    def discover_connectors(self) -> int:
        """Auto-discover connectors from data/webshell/connectors directory.

        Scans the connector directory for Python files and attempts
        to load WebshellConnector subclasses from them.

        Returns:
            Number of connectors discovered
        """
        if self._initial_discovery_done:
            return 0

        discovered_count = 0

        # Default connector directory
        connector_dir = DATA_DIR / "webshell" / "connectors"
        if connector_dir not in self._user_connector_paths:
            self._user_connector_paths.insert(0, connector_dir)

        for connector_path in self._user_connector_paths:
            if not connector_path.exists():
                connector_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created connector directory: {connector_path}")
                continue

            # Find all Python files
            for py_file in connector_path.glob("*.py"):
                if py_file.name.startswith("_") or py_file.name == "__init__.py":
                    continue

                try:
                    discovered_count += self._load_connector_from_file(py_file)
                except Exception as e:
                    logger.warning(f"Failed to load connector from {py_file}: {e}")

        self._initial_discovery_done = True
        logger.info(f"Discovered {discovered_count} connector(s)")
        return discovered_count

    def _load_connector_from_file(self, py_file: Path) -> int:
        """Load connector classes from a Python file.

        Args:
            py_file: Path to Python file

        Returns:
            Number of connectors loaded from this file
        """
        module_name = f"ofx.data.webshell.connectors.{py_file.stem}"

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not load module spec from {py_file}")
            return 0

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        try:
            base_module = sys.modules.get('ofx.data.webshell.connectors.base')
            if base_module is None:
                base_path = py_file.parent / "base.py"
                if base_path.exists():
                    base_spec = importlib.util.spec_from_file_location(
                        'ofx.data.webshell.connectors.base', base_path
                    )
                    if base_spec and base_spec.loader:
                        base_module = importlib.util.module_from_spec(base_spec)
                        sys.modules['ofx.data.webshell.connectors.base'] = base_module
                        base_spec.loader.exec_module(base_module)

            if base_module and hasattr(base_module, 'WebshellConnector'):
                WebshellConnectorBase = base_module.WebshellConnector
            else:
                logger.warning("Could not find WebshellConnector base class")
                return 0
        except Exception as e:
            logger.warning(f"Failed to load base connector class: {e}")
            return 0

        loaded_count = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            if (
                isinstance(attr, type)
                and issubclass(attr, WebshellConnectorBase)
                and attr is not WebshellConnectorBase
            ):
                try:
                    self.register_connector_class(attr)
                    loaded_count += 1
                    logger.info(f"Loaded connector '{attr.__name__}' from {py_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to register {attr.__name__}: {e}")

        return loaded_count

    def clear_cache(self) -> None:
        """Clear the connector instance cache."""
        self._instances.clear()
        logger.debug("Cleared connector instance cache")

    def get_best_available_connector(self) -> WebshellConnector | None:
        """Get the best available connector.

        Prefers template connector if available, otherwise returns first available.

        Returns:
            Best available connector or None if none available
        """
        if not self._initial_discovery_done:
            self.discover_connectors()

        # Try template first
        template = self.get_connector('template')
        if template and template.is_available():
            return template

        # Fall back to any available connector
        available = self.get_available_connectors()
        if available:
            return available[0]

        return None


# Global registry instance
_global_registry = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    """Get the global connector registry."""
    return _global_registry


def get_connector(name: str) -> WebshellConnector | None:
    """Get a connector by name from the global registry."""
    return _global_registry.get_connector(name)


def get_available_connectors() -> list[WebshellConnector]:
    """Get all available connectors from the global registry."""
    return _global_registry.get_available_connectors()


def get_template_connector() -> WebshellConnector:
    """Get the template connector.

    Convenience function for the default connector.

    Returns:
        TemplateConnector instance

    Raises:
        RuntimeError: If template connector not available
    """
    connector = _global_registry.get_connector('template')
    if connector is None:
        raise RuntimeError("Template connector not registered")
    return connector


__all__ = [
    "ConnectorRegistry",
    "get_registry",
    "get_connector",
    "get_available_connectors",
    "get_template_connector",
]
