"""OFX Profiles — reusable option presets with time window enforcement.

Profiles provide named configuration sets (rate limits, scan intensity,
time windows) that can be applied to workflows, jobs, or tasks.

Usage in workflows::

    defaults:
      profile: stealth

    jobs:
      scan:
        steps:
          - task: nmap
            with:
              target: "{{ inputs.target }}"

CLI management::

    ofx flow profile list
    ofx flow profile show stealth
    ofx flow profile add aggressive --set rate_limit=0 --set time_window.enabled=false
    ofx flow profile remove aggressive
"""

from ofx.profiles.manager import ProfileManager, get_profile_manager
from ofx.profiles.models import OFXProfile, TimeWindow

__all__ = [
    "OFXProfile",
    "TimeWindow",
    "ProfileManager",
    "get_profile_manager",
]
