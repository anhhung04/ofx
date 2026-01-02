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
    """ZoomEye cyberspace search engine client.

    ZoomEye (知道创宇) is a Chinese cyberspace search engine for discovering
    internet-connected devices. Supports both domestic (api.zoomeye.org) and
    international (api.zoomeye.ai) endpoints.

    Attributes:
        token: ZoomEye API key
        url: Base URL for ZoomEye API (zoomeye.org or zoomeye.ai)
        conf_path: Path to config file storing credentials
        points: Available search points
        zoomeye_points: ZoomEye-specific points balance
        plan: Subscription plan type (free, developer, etc.)

    Example:
        >>> zoomeye = ZoomEye()
        ZoomEye Url: https://api.zoomeye.org
        ZoomEye API token: (input will hidden)
        >>> results = zoomeye.search('app:"Apache httpd"', pages=2)
        >>> for url in results:
        ...     print(url)
        http://192.168.1.1:80
    """

    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        """Initialize ZoomEye client with credential management.

        Loads API token and server URL from config file if available, prompts
        for input if needed. Automatically validates token on initialization.

        Args:
            conf_path: Path to config file (default: ~/.local/share/ofx/config.ini)
            token: ZoomEye API key (optional, will prompt if not provided)
        """
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
        """Verify if current ZoomEye API token is valid.

        Makes a test API call to check if token is correct and retrieves
        subscription plan details and available points.

        Returns:
            True if token is valid, False otherwise
        """
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
        """Ensure valid ZoomEye credentials are available.

        If current credentials are invalid, prompts user for API URL and token
        until valid credentials are provided. Guides users to select correct
        server (mainland China vs international). Saves valid credentials to config.

        Returns:
            True when valid credentials are confirmed
        """
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
        """Save ZoomEye credentials to config file.

        Creates config directory if needed and persists API token and server URL
        to config.ini in INI format.
        """
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
        """Search ZoomEye for assets matching a query.

        Executes a ZoomEye search query and retrieves matching results across
        multiple pages. Query syntax follows ZoomEye's query language.

        Args:
            dork: ZoomEye query string (e.g., 'app:"nginx" +country:"CN"')
            pages: Number of pages to retrieve (default: 2)
            pagesize: Results per page, max 20 (default: 20)
            search_type: IP version filter - 'v4' or 'v6' (default: 'v4')

        Returns:
            Set of unique URLs/endpoints matching the query

        Example:
            >>> results = zoomeye.search('device:"router"', pages=3, search_type='v4')
            >>> results
            {'http://192.168.1.1:80', 'https://10.0.0.1:443', ...}
        """
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
