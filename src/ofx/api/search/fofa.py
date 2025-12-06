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


class Fofa:
    def __init__(
        self,
        conf_path: Path | None = None,
        user: str | None = None,
        token: str | None = None,
    ):
        self.headers = {"User-Agent": "curl/7.80.0"}
        self.credits = 0
        self.user = user
        self.token = token
        self.api_url = "https://fofa.info/api/v1"

        if conf_path is None:
            conf_path = Path.home() / ".local" / "share" / "ofx" / "config.ini"

        self.conf_path = conf_path
        self.parser = ConfigParser()

        if self.conf_path and self.conf_path.exists():
            self.parser.read(self.conf_path)
            try:
                self.user = self.user or self.parser.get("Fofa", "user")
                self.token = self.token or self.parser.get("Fofa", "token")
            except Exception:
                pass

        self.check_token()

    def token_is_available(self) -> bool:
        if self.token and self.user:
            try:
                resp = requests.get(
                    f"{self.api_url}/info/my?email={self.user}&key={self.token}",
                    headers=self.headers,
                )
                logger.info(resp.text)
                if resp and resp.status_code == 200 and "username" in resp.json():
                    return True
            except Exception as ex:
                logger.error(str(ex))
        return False

    def check_token(self) -> bool:
        if self.token_is_available():
            return True

        while True:
            user = input("Fofa user email: ")
            new_token = getpass.getpass("Fofa api key: (input will hidden) ")
            self.token = new_token
            self.user = user
            if self.token_is_available():
                self.write_conf()
                return True
            else:
                logger.error(
                    "The Fofa user email or api key are incorrect, Please enter the correct one."
                )

    def write_conf(self) -> None:
        if not self.parser.has_section("Fofa"):
            self.parser.add_section("Fofa")
        try:
            self.parser.set("Fofa", "Token", self.token)
            self.parser.set("Fofa", "User", self.user)
            if self.conf_path:
                self.conf_path.parent.mkdir(parents=True, exist_ok=True)
                self.parser.write(open(self.conf_path, "w"))
        except Exception as ex:
            logger.error(str(ex))

    def search(self, dork: str, pages: int = 1, resource: str = "host") -> set[str]:
        if resource == "host":
            resource = "protocol,ip,port"
        else:
            resource = "protocol,host"

        dork_encoded = b64encode(dork.encode()).decode()
        search_result = set()

        try:
            for page in range(1, pages + 1):
                time.sleep(1)
                url = (
                    f"{self.api_url}/search/all?email={self.user}&key={self.token}&qbase64={dork_encoded}&"
                    f"fields={resource}&page={page}"
                )
                resp = requests.get(url, headers=self.headers, timeout=60)
                if resp and resp.status_code == 200 and "results" in resp.json():
                    content = resp.json()
                    for match in content["results"]:
                        if resource == "protocol,ip,port":
                            ip = match[1]
                            if is_ipv6_address_format(ip):
                                ip = f"[{ip}]"
                            search_result.add(f"{match[0]}://{ip}:{match[2]}")
                        else:
                            if "://" not in match[1]:
                                search_result.add(f"{match[0]}://{match[1]}")
                            else:
                                search_result.add(match[1])
                else:
                    logger.error(f"[PLUGIN] Fofa:{resp.text}")
        except Exception as ex:
            logger.error(str(ex))
        return search_result
