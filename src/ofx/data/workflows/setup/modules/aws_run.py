"""Provision an AWS EC2 instance via the aws CLI (with dry-run support)."""
import subprocess


def run(ctx):
    name = str(ctx.inputs.get("instance_name", ""))
    region = str(ctx.inputs.get("region", "us-east-1"))
    image = str(ctx.inputs.get("image", ""))
    size = str(ctx.inputs.get("size", "t3.small"))
    key = str(ctx.inputs.get("ssh_key_name", ""))
    sg = str(ctx.inputs.get("security_group", ""))
    dry = "true" if ctx.inputs.get("dry_run", True) else "false"
    cmd = f"""set -euo pipefail NAME="{name}" REGION="{region}" IMAGE="{image}" SIZE="{size}" KEY="{key}" SG="{sg}" DRY="{dry}" if [ -z "$IMAGE" ] || [ "$IMAGE" = "ubuntu-22-04-x64" ]; then echo "ERROR: AWS provisioning requires an AMI ID in --image" echo "Example: ami-0abcdef1234567890" exit 0 fi CMD="aws ec2 run-instances --region $REGION --image-id $IMAGE --instance-type $SIZE --tag-specifications ResourceType=instance,Tags=[{{Key=Name,Value=$NAME}}] --user-data file:///tmp/ofx-cloud-init.yml" if [ -n "$KEY" ]; then CMD="$CMD --key-name $KEY"; fi if [ -n "$SG" ]; then CMD="$CMD --security-group-ids $SG"; fi echo "AWS command: $CMD" if [ "$DRY" = "true" ]; then echo "Dry run enabled; not provisioning" echo "instance_id=" echo "public_ip=" echo "ssh_command=ssh ubuntu@PUBLIC_IP" exit 0 fi OUT=$(eval "$CMD") IID=$(printf '%s' "$OUT" | jq -r '.Instances[0].InstanceId // empty') echo "instance_id=$IID" echo "Instance ID: $IID" if [ -n "$IID" ]; then aws ec2 wait instance-running --region "$REGION" --instance-ids "$IID" IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text) echo "public_ip=$IP" echo "ssh_command=ssh ubuntu@$IP" echo "Public IP: $IP" fi"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
