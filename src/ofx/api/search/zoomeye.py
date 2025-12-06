import getpass
import logging
import time
from base64 import b64encode
from configparser import ConfigParser
from pathlib import Path

from ofx.api.http import requests
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def is_ipv6_address_format(address: str) -> bool:
    return ":" in address and "." not in address


class ZoomEye:
    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        self.url = None
        self.headers = {
            "User-Agent": "curl/7.80.0",
            "Content-Type": "application/json",
        }
        self.token = token
        self.points = None
        self.zoomeye_points = None
        self.plan = None

        if conf_path is None:
            conf_path = Path.home() / ".local" / "share" / "ofx" / "config.ini"

        self.conf_path = conf_path
        self.parser = ConfigParser()

        if self.conf_path and self.conf_path.exists():
            self.parser.read(self.conf_path)
            try:
                self.token = self.token or self.parser.get("ZoomEye", "token")
                self.url = self.url or self.parser.get("ZoomEye", "url")
            except Exception:
                pass

        self.check_token()

    def token_is_available(self) -> bool:
        if self.token:
            try:
                self.headers["API-KEY"] = self.token
                resp = requests.post(f"{self.url}/v2/userinfo", headers=self.headers)
                if resp and resp.status_code == 200 and "plan" in resp.text:
                    content = resp.json()
                    self.plan = content["data"]["subscription"]["plan"]
                    self.points = content["data"]["subscription"]["points"]
                    self.zoomeye_points = content["data"]["subscription"][
                        "zoomeye_points"
                    ]
                    return True
                else:
                    logger.info(resp.text)
                    return False
            except Exception as ex:
                logger.error(str(ex))
        return False

    def check_token(self) -> bool:
        if self.token and self.url:
            if self.token_is_available():
                return True

        while True:
            logger.info(
                "Users in mainland China should use https://api.zoomeye.org, "
                "while other users should use https://api.zoomeye.ai."
            )
            self.url = input("ZoomEye Url:").rstrip("/")
            self.token = getpass.getpass("ZoomEye API token: (input will hidden)")
            if self.token_is_available():
                self.write_conf()
                return True
            else:
                logger.error(
                    "The ZoomEye api token is incorrect, Please enter the correct api token."
                )

    def write_conf(self) -> None:
        if not self.parser.has_section("ZoomEye"):
            self.parser.add_section("ZoomEye")
        try:
            self.parser.set("ZoomEye", "token", self.token)
            self.parser.set("ZoomEye", "url", self.url)
            if self.conf_path:
                self.conf_path.parent.mkdir(parents=True, exist_ok=True)
                self.parser.write(open(self.conf_path, "w"))
        except Exception as ex:
            logger.error(str(ex))

    def search(
        self, dork: str, pages: int = 2, pagesize: int = 20, search_type: str = "v4"
    ) -> set[str]:
        search_result = set()

        try:
            for page in range(1, pages + 1):
                time.sleep(1)
                url = f"{self.url}/v2/search"
                data = {
                    "qbase64": b64encode(dork.encode("utf-8")).decode("utf-8"),
                    "page": page,
                    "pagesize": pagesize,
                    "sub_type": search_type,
                    "fields": "ip,port,domain,service,honeypot",
                }

                resp = requests.post(url, headers=self.headers, timeout=60, json=data)
                content = resp.json()
                if (
                    resp
                    and resp.status_code == 200
                    and content.get("code", None) == 60000
                ):
                    for match in content["data"]:
                        if match["domain"]:
                            url_result = match["domain"]
                            if "://" not in url_result:
                                url_result = f"http://{url_result}"
                        else:
                            ip = match["ip"]
                            port = match["port"]
                            if is_ipv6_address_format(ip):
                                ip = f"[{ip}]"
                            if port == 443:
                                url_result = f"https://{ip}:{port}"
                            else:
                                url_result = f"http://{ip}:{port}"
                        search_result.add(url_result)
                else:
                    logger.error(f"[PLUGIN] ZoomEye:{resp.text}")
        except Exception as ex:
            logger.error(str(ex))
        return search_result
