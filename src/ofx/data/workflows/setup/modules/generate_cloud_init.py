"""Generate a cloud-init user-data file for bootstrap tooling."""

from __future__ import annotations

import pathlib

_BOOTSTRAP_CLOUD_CONFIG = """
package_update: true
packages:
  - git
  - curl
  - wget
  - unzip
  - jq
  - python3
  - python3-pip
  - nmap
  - nginx
runcmd:
  - mkdir -p /opt/ofx
  - echo 'OFX cloud bootstrap complete' > /opt/ofx/bootstrap.log
"""


def run(ctx):
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the cloud-init file")

    content = "#cloud-config\n"
    if bool(ctx.inputs.get("bootstrap_tools", True)):
        content += _BOOTSTRAP_CLOUD_CONFIG
    else:
        content += "packages: []\n"

    path = pathlib.Path(run_dir) / "cloud-init.yml"
    path.write_text(content)
    path.chmod(0o600)
    ctx.add_outputs(user_data=str(path))
    print(f"Cloud-init written: {path}")
