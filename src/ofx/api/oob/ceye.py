"""CEye OOB client."""

import getpass
import json
import re
import time
from configparser import ConfigParser
from pathlib import Path

from ofx.api._compat import CONFIG_FILE, get_logger
from ofx.api.exploitation.exploit.utils import get_middle_text, random_str
from ofx.api.http import requests

logger = get_logger()


class CEye:
    """CEye Out-of-Band (OOB) interaction platform client.

    CEye is a monitoring platform for detecting blind vulnerabilities
    through DNS and HTTP callbacks. This client provides methods to
    interact with the CEye API for generating unique URLs and verifying
    if they were accessed.

    Attributes:
        url: Base URL for CEye API
        identify: Unique identifier for the CEye account
        token: API authentication token
        conf_path: Path to configuration file storing credentials

    Example:
        >>> ceye = CEye(token='your_api_token')
        >>> payload = ceye.build_request('test', type='dns')
        >>> # Use payload['url'] in your exploit
        >>> if ceye.verify_request(payload['flag'], type='dns'):
        ...     print('DNS callback received!')
    """

    def __init__(self, conf_path: Path | None = None, token: str | None = None):
        """Initialize CEye client with optional configuration.

        Args:
            conf_path: Path to config file (default: ~/.ofx/config.ini)
            token: CEye API token (will prompt if not provided)
        """
        self.url = "http://api.ceye.io/v1"
        self.identify = ""
        self.headers = {"User-Agent": "curl/7.80.0"}
        self.token = token

        if conf_path is None:
            conf_path = CONFIG_FILE

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
        """Check if the current API token is valid.

        Returns:
            True if token is valid and account is accessible, False otherwise

        Example:
            >>> ceye = CEye(token='test_token')
            >>> ceye.token_is_available()
            True
        """
        if self.token:
            try:
                self.headers["Authorization"] = self.token
                resp = requests.get(f"{self.url}/identify", headers=self.headers)
                if resp and resp.status_code == 200 and "identify" in resp.text:
                    self.identify = resp.json()["data"]["identify"]
                    return True
                if resp is not None:
                    logger.info(resp.text)
            except Exception as ex:
                logger.error(str(ex))
        return False

    def check_account(self) -> bool:
        """Verify CEye account credentials.

        Returns:
            True if account is valid
        """
        return self.check_token()

    def check_token(self) -> bool:
        """Validate API token, prompting user if invalid or missing.

        Continuously prompts for a valid token until one is provided.
        Automatically saves valid tokens to configuration file.

        Returns:
            True when a valid token is confirmed
        """
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
        """Save API token to configuration file.

        Creates config file and directories if they don't exist.
        Stores token securely in INI format.
        """
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
        """Check if a specific flag/identifier was accessed via CEye.

        Polls the CEye API to verify if a callback with the given flag
        was received. Retries up to 3 times with 1-second delays.

        Args:
            flag: Unique identifier to search for in callbacks
            type: Type of callback to check ('request', 'http', or 'dns')

        Returns:
            True if callback was detected, False otherwise

        Example:
            >>> ceye.verify_request('abc123', type='dns')
            True
        """
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
        """Extract data exfiltrated through CEye callbacks.

        Searches for callbacks containing the flag and extracts data
        sandwiched between flag occurrences for data exfiltration.

        Args:
            flag: Unique identifier used in the payload
            type: Type of callback ('request', 'http', or 'dns')

        Returns:
            Extracted data string, or False if not found

        Example:
            >>> data = ceye.exact_request('abc123')
            >>> data
            'exfiltrated_password'
        """
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
        """Generate a unique CEye URL for OOB detection or data exfiltration.

        Creates a URL with embedded identifiers that can be used in payloads.
        The generated URL will trigger a callback when accessed.

        Args:
            value: Data to embed in the URL (for exfiltration)
            type: Type of callback ('request'/'http' for HTTP, 'dns' for DNS)

        Returns:
            Dictionary with 'url' (full CEye URL) and 'flag' (unique identifier)

        Example:
            >>> payload = ceye.build_request('test_data', type='dns')
            >>> payload
            {'url': 'ab12test_datacd34.xxxxx.ceye.io', 'flag': 'ab12'}
        """
        ranstr = random_str(4)
        domain = self.getsubdomain()
        url = ""
        if type in ["request", "http"]:
            url = f"http://{ranstr}.{domain}/{ranstr}{value}{ranstr}"
        elif type == "dns":
            clean_value = re.sub(r"\W", "", value)
            url = f"{ranstr}{clean_value}{ranstr}.{domain}"
        return {"url": url, "flag": ranstr}

    def getsubdomain(self) -> str:
        """Get the unique CEye subdomain for this account.

        Returns:
            Full subdomain string (e.g., 'identifier.ceye.io')

        Example:
            >>> ceye.getsubdomain()
            'abc123.ceye.io'
        """
        return f"{self.identify}.ceye.io"


CEyeClient = CEye

__all__ = ["CEye", "CEyeClient"]
