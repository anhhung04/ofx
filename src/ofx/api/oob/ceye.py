import getpass
import json
import logging
import re
import time
from configparser import ConfigParser
from pathlib import Path

from ofx.api.exploit import get_middle_text, random_str
from ofx.api.http import requests
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class CEye:
    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        self.url = "http://api.ceye.io/v1"
        self.identify = ""
        self.headers = {"User-Agent": "curl/7.80.0"}
        self.token = token

        if conf_path is None:
            conf_path = Path.home() / ".local" / "share" / "ofx" / "config.ini"

        self.conf_path = conf_path
        self.parser = ConfigParser()

        if self.conf_path and self.conf_path.exists():
            self.parser.read(self.conf_path)
            try:
                self.token = self.token or self.parser.get("CEye", "token")
            except Exception:
                pass

        self.check_token()

    def token_is_available(self) -> bool:
        if self.token:
            try:
                self.headers["Authorization"] = self.token
                resp = requests.get(f"{self.url}/identify", headers=self.headers)
                if resp and resp.status_code == 200 and "identify" in resp.text:
                    self.identify = resp.json()["data"]["identify"]
                    return True
                else:
                    logger.info(resp.text)
            except Exception as ex:
                logger.error(str(ex))
        return False

    def check_account(self) -> bool:
        return self.check_token()

    def check_token(self) -> bool:
        if self.token_is_available():
            return True

        while True:
            self.token = getpass.getpass("CEye API token: (input will hidden)")
            if self.token_is_available():
                self.write_conf()
                return True
            else:
                logger.error(
                    "The CEye api token is incorrect, Please enter the correct api token."
                )

    def write_conf(self) -> None:
        if not self.parser.has_section("CEye"):
            self.parser.add_section("CEye")
        try:
            self.parser.set("CEye", "token", self.token)
            if self.conf_path:
                self.conf_path.parent.mkdir(parents=True, exist_ok=True)
                self.parser.write(open(self.conf_path, "w"))
        except Exception as ex:
            logger.error(str(ex))

    def verify_request(self, flag: str, type: str = "request") -> bool:
        ret_val = False
        counts = 3
        url = f"{self.url}/records?token={self.token}&type={type}&filter={flag}"
        while counts:
            try:
                time.sleep(1)
                resp = requests.get(url)
                if resp and resp.status_code == 200 and flag in resp.text:
                    ret_val = True
                    break
            except Exception as ex:
                logger.warning(ex)
                time.sleep(1)
            counts -= 1
        return ret_val

    def exact_request(self, flag: str, type: str = "request") -> str | bool:
        counts = 3
        url = f"{self.url}/records?token={self.token}&type={type}&filter={flag}"
        while counts:
            try:
                time.sleep(1)
                resp = requests.get(url)
                if resp and resp.status_code == 200 and flag in resp.text:
                    data = json.loads(resp.text)
                    for item in data["data"]:
                        name = item.get("name", "")
                        pro = flag
                        suffix = flag
                        t = get_middle_text(name, pro, suffix, greedy=False)
                        if t:
                            return t
                    break
            except Exception as ex:
                logger.warning(ex)
                time.sleep(1)
            counts -= 1
        return False

    def build_request(self, value: str, type: str = "request") -> dict[str, str]:
        ranstr = random_str(4)
        domain = self.getsubdomain()
        url = ""
        if type in ["request", "http"]:
            url = f"http://{ranstr}.{domain}/{ranstr}{value}{ranstr}"
        elif type == "dns":
            url = f"{ranstr}{re.sub(r'\W', '', value)}{ranstr}.{domain}"
        return {"url": url, "flag": ranstr}

    def getsubdomain(self) -> str:
        return f"{self.identify}.ceye.io"
