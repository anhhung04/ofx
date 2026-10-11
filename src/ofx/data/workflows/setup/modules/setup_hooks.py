"""Build a .pre-commit-config.yaml and install hooks when pre-commit is present."""
import pathlib
import subprocess

import yaml


def run(ctx):
    repo_root = pathlib.Path(str(ctx.inputs.get("repo_root", "")))
    precommit_config = repo_root / ".pre-commit-config.yaml"
    gitleaks_config = str(ctx.inputs.get("gitleaks_config", ""))
    scan_mode = str(ctx.inputs.get("scan_mode", "pre-commit"))

    # Detect if pre-commit is available
    precommit_cmd = None
    for cmd in ["pre-commit"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True)
            precommit_cmd = cmd
            break
        except FileNotFoundError:
            pass

    # Build .pre-commit-config.yaml
    hooks_config = {
        "repos": [
            {
                "repo": "https://github.com/gitleaks/gitleaks",
                "rev": "v8.18.0",
                "hooks": [
                    {
                        "id": "gitleaks",
                        "args": ["--verbose"]
                        + (["--config", gitleaks_config] if gitleaks_config else []),
                    }
                ],
            },
            {
                "repo": "https://github.com/trufflesecurity/trufflehog",
                "rev": "v3.67.0",
                "hooks": [
                    {
                        "id": "trufflehog",
                        "args": [
                            "git",
                            "file://.",
                            "--since-commit",
                            "HEAD",
                            "--fail",
                            "--no-update",
                        ],
                    }
                ],
            },
        ]
    }

    precommit_config.write_text(
        yaml.dump(hooks_config, default_flow_style=False, sort_keys=False)
    )

    hooks_count = len(hooks_config["repos"])
    ctx.add_outputs(hooks_installed=hooks_count, config_path=str(precommit_config))
    print(f"Pre-commit hooks installed: {hooks_count}")

    # Install hooks if pre-commit is available
    if precommit_cmd:
        try:
            subprocess.run(
                [precommit_cmd, "install", "--hook-type", scan_mode],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
            )
            print(f"pre-commit hooks installed for: {scan_mode}")
        except Exception as e:
            print(f"Note: pre-commit tool not available ({e})")
            print("Hooks config written but not auto-installed")
            print("Run manually: pip install pre-commit && pre-commit install")
    else:
        print("Install pre-commit manually: pip install pre-commit")
