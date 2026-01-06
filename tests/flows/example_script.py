#!/usr/bin/env python3
from ofx.settings import settings
import requests

# Demonstrate importing ofx internals and an external dependency
print(f"EXAMPLE_SCRIPT_OK:{settings.app_branding}")
print(f"REQUESTS_OK:{requests.__version__}")
