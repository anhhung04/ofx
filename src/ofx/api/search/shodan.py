"""Shodan search client."""

import getpass
import logging
import time
import urllib.parse
from configparser import ConfigParser
from pathlib import Path

from ofx.api.http import requests
from ofx.settings import CONFIG_FILE, settings

logger = logging.getLogger(settings.app_branding)


def is_ipv6_address_format(address: str) -> bool:
    return ":" in address and "." not in address


class Shodan:
    """Shodan search engine client for internet-connected device discovery.

    Shodan is a search engine for finding specific devices connected to the internet.
    This client provides automated authentication, credential management, and search
    capabilities with credit tracking.

    Attributes:
        token: Shodan API key
        url: Base URL for Shodan API (https://api.shodan.io)
        conf_path: Path to config file storing credentials
        credits: Available search credits from account

    Example:
        >>> shodan = Shodan()
        Shodan API Token: (input will hidden)
        >>> results = shodan.search('port:22 country:"US"', pages=1)
        >>> for host in results:
        ...     print(host)
        192.168.1.1:22
    """

    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        """Initialize Shodan client with credential management.

        Loads API token from config file if available, prompts for input if needed.
        Automatically validates token on initialization.

        Args:
            conf_path: Path to config file (default: ~/.ofx/config.ini)
            token: Shodan API key (optional, will prompt if not provided)
        """
        self.url = "https://api.shodan.io"
        self.headers = {"User-Agent": "curl/7.80.0"}
        self.credits = 0
        self.token = token

        if conf_path is None:
            conf_path = CONFIG_FILE

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
        """Verify if current Shodan API token is valid.

        Makes a test API call to check if token is correct and retrieves
        available search credits.

        Returns:
            True if token is valid, False otherwise
        """
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
        """Ensure valid Shodan API token is available.

        If current token is invalid, prompts user for API token until valid
        credentials are provided. Saves valid token to config.

        Returns:
            True when valid token is confirmed
        """
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
        """Save Shodan API token to config file.

        Creates config directory if needed and persists API token to config.ini
        in INI format.
        """
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
        """Search Shodan for hosts matching a query.

        Executes a Shodan search query and retrieves matching hosts across
        multiple pages. Query syntax follows Shodan's search filters.

        Args:
            dork: Shodan query string (e.g., 'port:80 country:"US" apache')
            pages: Number of pages to retrieve (default: 1)

        Returns:
            Set of unique IP:port combinations matching the query

        Example:
            >>> results = shodan.search('product:"MySQL" country:"CN"', pages=2)
            >>> results
            {'192.168.1.1:3306', '[2001:db8::1]:3306', ...}
        """
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


ShodanClient = Shodan

__all__ = ["Shodan", "ShodanClient", "is_ipv6_address_format"]
