"""Generate a Docker Compose lab configuration (custom or from target list)."""

from __future__ import annotations

import pathlib
import shutil

import yaml

LAB_NETWORK = "lab-net"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_HOST_PORT_START = 18000

_TARGETS = {
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


def _copy_custom_compose(source: pathlib.Path, lab_dir: pathlib.Path) -> pathlib.Path:
    compose_path = lab_dir / "docker-compose.yml"
    shutil.copy(source, compose_path)
    return compose_path


def run(ctx):
    lab_dir = pathlib.Path(str(ctx.inputs.get("lab_dir", "")).strip())
    if not str(lab_dir) or not lab_dir.is_dir():
        raise RuntimeError(f"lab_dir is missing or not a directory: {lab_dir}")

    compose_file_input = str(ctx.inputs.get("compose_file", "")).strip()
    if compose_file_input:
        source = pathlib.Path(compose_file_input).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"custom compose file not found: {source}")
        compose_path = _copy_custom_compose(source, lab_dir)
        ctx.add_outputs(
            compose_path=str(compose_path), target_list="custom", endpoints=""
        )
        print(f"Using custom compose file: {source}")
        print(f"Compose file: {compose_path}")
        return

    targets = [
        item.strip()
        for item in str(ctx.inputs.get("targets", "juice-shop,dvwa")).split(",")
        if item.strip()
    ]
    if not targets:
        raise ValueError("targets must list at least one lab target")
    unknown = [item for item in targets if item not in _TARGETS]
    if unknown:
        raise ValueError(
            "unknown lab target(s): "
            + ", ".join(unknown)
            + "; supported: "
            + ", ".join(sorted(_TARGETS))
        )

    expose = bool(ctx.inputs.get("expose_ports", True))
    bind_host = str(ctx.inputs.get("bind_host", "")).strip() or DEFAULT_BIND_HOST
    host_port_start = int(
        str(ctx.inputs.get("host_port_start", "")).strip() or DEFAULT_HOST_PORT_START
    )
    network_subnet = str(ctx.inputs.get("network", "172.20.0.0/24")).strip()

    services: dict[str, dict] = {}
    endpoints: list[str] = []
    host_port = host_port_start
    for target in targets:
        info = _TARGETS[target]
        service: dict = {
            "image": info["image"],
            "networks": {LAB_NETWORK: {}},
            "restart": "unless-stopped",
        }
        if expose:
            service["ports"] = [f"{bind_host}:{host_port}:{info['port']}"]
            endpoints.append(f"{target}=http://{bind_host}:{host_port}")
            host_port += 1
        services[target] = service

    compose = {
        "version": "3.9",
        "services": services,
        "networks": {
            LAB_NETWORK: {
                "driver": "bridge",
                "ipam": {"config": [{"subnet": network_subnet}]},
            }
        },
    }

    compose_path = lab_dir / "docker-compose.yml"
    compose_path.write_text(
        yaml.dump(compose, default_flow_style=False, sort_keys=False)
    )

    target_desc = ", ".join(f"{item} ({_TARGETS[item]['desc']})" for item in targets)
    ctx.add_outputs(
        compose_path=str(compose_path),
        target_list=target_desc,
        endpoints="\n".join(endpoints),
    )
    print(f"Generated lab with: {target_desc}")
    print(f"Compose file: {compose_path}")
    for endpoint in endpoints:
        print(f"  {endpoint}")
