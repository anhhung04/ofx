"""JSON utilities for OFX framework."""

import json
from enum import Enum

class EnumEncoder(json.JSONEncoder):
    """Custom JSON encoder for Enums"""

    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)
