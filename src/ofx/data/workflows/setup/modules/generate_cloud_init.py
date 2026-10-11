"""Generate a cloud-init user-data file for bootstrap tooling."""
from pathlib import Path


def run(ctx):
    bootstrap = bool(ctx.inputs.get("bootstrap_tools", True))
    content = "#cloud-config\n"
    if bootstrap:
        content += """
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
    else:
        content += "packages: []\n"

    path = Path("/tmp/ofx-cloud-init.yml")
    path.write_text(content)
    ctx.add_outputs(user_data=str(path))
    print(f"Cloud-init written: {path}")
