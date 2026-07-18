#!/usr/bin/env python3
import requests

from ofx.settings import settings

print(f"EXAMPLE_SCRIPT_OK:{settings.app_branding}")
print(f"REQUESTS_OK:{requests.__version__}")
