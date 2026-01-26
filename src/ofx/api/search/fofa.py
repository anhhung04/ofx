"""FOFA search client."""

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
    """FOFA (Cyberspace Assets Retrieval) search engine client.

    FOFA is a search engine for internet-connected assets. This client provides
    automated authentication, credential management, and asset searching capabilities.

    Attributes:
        user: FOFA account email address
        token: FOFA API key
        api_url: Base URL for FOFA API (https://fofa.info/api/v1)
        conf_path: Path to config file storing credentials
        credits: Available search credits (from account info)

    Example:
        >>> fofa = Fofa()
        Fofa user email: user@example.com
        Fofa api key: (input will hidden)
        >>> results = fofa.search('title="login"', pages=2)
        >>> for url in results:
        ...     print(url)
        https://example.com:443
    """

    def __init__(
        self,
        conf_path: Path | None = None,
        user: str | None = None,
        token: str | None = None,
    ):
        """Initialize FOFA client with credential management.

        Loads credentials from config file if available, prompts for input if needed.
        Automatically validates token on initialization.

        Args:
            conf_path: Path to config file (default: ~/.local/share/ofx/config.ini)
            user: FOFA account email (optional, will prompt if not provided)
            token: FOFA API key (optional, will prompt if not provided)
        """
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
        """Verify if current FOFA credentials are valid.

        Makes a test API call to check if user email and API key are correct.

        Returns:
            True if credentials are valid, False otherwise
        """
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
        """Ensure valid FOFA credentials are available.

        If current credentials are invalid, prompts user for email and API key
        until valid credentials are provided. Saves valid credentials to config.

        Returns:
            True when valid credentials are confirmed
        """
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
        """Save FOFA credentials to config file.

        Creates config directory if needed and persists user email and API key
        to config.ini in INI format.
        """
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
        """Search FOFA for assets matching a query.

        Executes a FOFA search query and retrieves matching results across
        multiple pages. Query syntax follows FOFA's query language.

        Args:
            dork: FOFA query string (e.g., 'title="login" && country="US"')
            pages: Number of pages to retrieve (default: 1)
            resource: Return format - 'host' for IP:port, else domain (default: 'host')

        Returns:
            Set of unique URLs/endpoints matching the query

        Example:
            >>> results = fofa.search('port=8080 && protocol="http"', pages=3)
            >>> results
            {'http://192.168.1.1:8080', 'http://10.0.0.1:8080', ...}
        """
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


FofaClient = Fofa

__all__ = ["Fofa", "FofaClient", "is_ipv6_address_format"]
