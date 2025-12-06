import getpass
import logging
import time
import urllib.parse
from configparser import ConfigParser
from pathlib import Path

from ofx.api.http import requests
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def is_ipv6_address_format(address: str) -> bool:
    return ":" in address and "." not in address


class Shodan:
    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        self.url = "https://api.shodan.io"
        self.headers = {"User-Agent": "curl/7.80.0"}
        self.credits = 0
        self.token = token

        if conf_path is None:
            conf_path = Path.home() / ".local" / "share" / "ofx" / "config.ini"

        self.conf_path = conf_path
        self.parser = ConfigParser()

        if self.conf_path and self.conf_path.exists():
            self.parser.read(self.conf_path)
            try:
                self.token = self.token or self.parser.get("Shodan", "Token")
            except Exception:
                pass

        self.check_token()

    def token_is_available(self) -> bool:
        if self.token:
            try:
                resp = requests.get(
                    f"{self.url}/account/profile?key={self.token}", headers=self.headers
                )
                logger.info(resp.text)
                if resp and resp.status_code == 200 and "member" in resp.json():
                    self.credits = resp.json()["credits"]
                    return True
            except Exception as ex:
                logger.error(str(ex))
        return False

    def check_token(self) -> bool:
        if self.token_is_available():
            return True

        while True:
            new_token = getpass.getpass("Shodan API Token: (input will hidden)")
            self.token = new_token
            if self.token_is_available():
                self.write_conf()
                return True
            else:
                logger.error(
                    "The shodan api token is incorrect, Please enter the correct api token."
                )

    def write_conf(self) -> None:
        if not self.parser.has_section("Shodan"):
            self.parser.add_section("Shodan")
        try:
            self.parser.set("Shodan", "Token", self.token)
            if self.conf_path:
                self.conf_path.parent.mkdir(parents=True, exist_ok=True)
                self.parser.write(open(self.conf_path, "w"))
        except Exception as ex:
            logger.error(str(ex))

    def search(self, dork: str, pages: int = 1) -> set[str]:
        resource = "host"
        dork_encoded = urllib.parse.quote(dork)
        search_result = set()
        try:
            for page in range(1, pages + 1):
                time.sleep(1)
                url = f"{self.url}/shodan/{resource}/search?key={self.token}&query={dork_encoded}&page={page}"
                resp = requests.get(url, headers=self.headers, timeout=60)
                if resp and resp.status_code == 200 and "total" in resp.json():
                    content = resp.json()
                    for match in content["matches"]:
                        ans = match["ip_str"]
                        if "port" in match:
                            if is_ipv6_address_format(ans):
                                ans = f"[{ans}]"
                            ans += ":" + str(match["port"])
                        search_result.add(ans)
                else:
                    logger.error(f"[PLUGIN] Shodan:{resp.text}")
        except Exception as ex:
            logger.error(str(ex))
        return search_result
