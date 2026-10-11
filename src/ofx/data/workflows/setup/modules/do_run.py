"""Provision a DigitalOcean droplet via the doctl CLI (with dry-run support)."""
import subprocess


def run(ctx):
    name = str(ctx.inputs.get("instance_name", ""))
    region = str(ctx.inputs.get("region", "us-east-1"))
    size = str(ctx.inputs.get("size", "t3.small"))
    image = str(ctx.inputs.get("image", ""))
    key = str(ctx.inputs.get("ssh_key_name", ""))
    dry = "true" if ctx.inputs.get("dry_run", True) else "false"
    bootstrap = "true" if ctx.inputs.get("bootstrap_tools", True) else "false"
    cmd = rf"""set -euo pipefail NAME="{name}" REGION="{region}" SIZE="{size}" IMAGE="{image}" KEY="{key}" DRY="{dry}" if [ "$SIZE" = "t3.small" ]; then SIZE="s-1vcpu-1gb"; fi CMD="doctl compute droplet create $NAME --region $REGION --size $SIZE --image $IMAGE --wait --format ID,PublicIPv4 --no-header" if [ -n "$KEY" ]; then CMD="$CMD --ssh-keys $KEY"; fi if [ "{bootstrap}" = "true" ]; then cat <<\EOF package_update: true packages: - git - curl - wget - unzip - jq - python3 - python3-pip - nmap runcmd: - mkdir -p /opt/ofx - echo 'OFX DigitalOcean bootstrap complete' EOF CMD="$CMD --user-data-file /tmp/ofx-do-cloud-init.yml" fi echo "DigitalOcean command: $CMD" if [ "$DRY" = "true" ]; then echo "Dry run enabled; not provisioning" echo "droplet_id=" echo "public_ip=" echo "ssh_command=ssh root@PUBLIC_IP" exit 0 fi OUT=$(eval "$CMD") DID=$(printf '%s' "$OUT" | awk '{{print $1}}') IP=$(printf '%s' "$OUT" | awk '{{print $2}}') echo "droplet_id=$DID" echo "public_ip=$IP" echo "ssh_command=ssh root@$IP" echo "Droplet ID: $DID" echo "Public IP: $IP" """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
