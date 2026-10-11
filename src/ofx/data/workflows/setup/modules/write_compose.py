"""Generate a Docker Compose lab configuration (custom or from target list)."""
import pathlib
import shutil

import yaml


def run(ctx):
    lab_dir = pathlib.Path(str(ctx.inputs.get("lab_dir", "")))
    compose_file_input = str(ctx.inputs.get("compose_file", ""))

    if compose_file_input and pathlib.Path(compose_file_input).exists():
        compose_path = pathlib.Path(compose_file_input)
        shutil.copy(compose_path, lab_dir / "docker-compose.yml")
        ctx.add_outputs(
            compose_path=str(lab_dir / "docker-compose.yml"), target_list="custom"
        )
        print(f"Using custom compose file: {compose_path}")
    else:
        targets = [
            t.strip()
            for t in str(ctx.inputs.get("targets", "juice-shop,dvwa")).split(",")
            if t.strip()
        ]
        network_subnet = str(ctx.inputs.get("network", "172.20.0.0/24"))
        expose = bool(ctx.inputs.get("expose_ports", True))

        services = {}
        target_info = {
            "juice-shop": {
                "image": "bkimminich/juice-shop:latest",
                "port": 3000,
                "desc": "OWASP Juice Shop",
            },
            "dvwa": {
                "image": "vulnerables/web-dvwa:latest",
                "port": 80,
                "desc": "Damn Vulnerable Web App",
            },
            "metasploitable2": {
                "image": "tleemcjr/metasploitable2:latest",
                "port": 80,
                "desc": "Metasploitable 2",
            },
            "mutillidae": {
                "image": "citizenstig/nowasp:latest",
                "port": 80,
                "desc": "Mutillidae",
            },
            "webgoat": {
                "image": "webgoat/goatandwolf:latest",
                "port": 8080,
                "desc": "WebGoat",
            },
            "vulnbank": {
                "image": "vulnbank/vulnbank:latest",
                "port": 8080,
                "desc": "VulnBank",
            },
        }

        for target in targets:
            info = target_info.get(target)
            if info:
                services[target] = {
                    "image": info["image"],
                    "container_name": f"{target}",
                    "networks": {"lab-net": {}},
                    "restart": "unless-stopped",
                }
                if expose:
                    services[target]["ports"] = [
                        f"{info['port']}:{info['port']}"
                    ]

        compose = {
            "version": "3.9",
            "services": services,
            "networks": {
                "lab-net": {
                    "driver": "bridge",
                    "ipam": {"config": [{"subnet": network_subnet}]},
                }
            },
        }

        compose_path = lab_dir / "docker-compose.yml"
        compose_path.write_text(
            yaml.dump(compose, default_flow_style=False, sort_keys=False)
        )

        target_desc = ", ".join(
            f"{t} ({target_info[t]['desc']})" for t in targets if t in target_info
        )
        ctx.add_outputs(compose_path=str(compose_path), target_list=target_desc)
        print(f"Generated lab with: {target_desc}")
        print(f"Compose file: {compose_path}")
