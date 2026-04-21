import ast
import socket
import urllib.parse
from typing import Any

from ofx.api._compat import get_logger

logger = get_logger()

__all__ = [
    "url2ip",
    "str_to_dict",
    "generate_random_user_agent",
    "minimum_version_required",
]


def url2ip(url: str, with_port: bool = False) -> str | tuple[str, int]:
    """Convert a URL to an IP address with optional port.

    Resolves the hostname in a URL to its IP address and extracts the port.
    Defaults to port 443 for HTTPS and 80 for HTTP if not specified.

    Args:
        url: URL string to convert (e.g., 'http://example.com:8080')
        with_port: Return tuple of (ip, port) if True, else just ip

    Returns:
        IP address string, or tuple of (ip, port) if with_port=True

    Example:
        >>> url2ip('http://example.com')
        '93.184.216.34'
        >>> url2ip('https://example.com:8443', with_port=True)
        ('93.184.216.34', 8443)
    """
    url_parsed = (
        urllib.parse.urlparse(url)
        if "://" in url
        else urllib.parse.urlparse(f"http://{url}")
    )
    hostname = url_parsed.hostname or url

    if url_parsed.port:
        ret = socket.gethostbyname(hostname), url_parsed.port
    elif not url_parsed.port and url_parsed.scheme == "https":
        ret = socket.gethostbyname(hostname), 443
    else:
        ret = socket.gethostbyname(hostname), 80

    return ret if with_port else ret[0]


def str_to_dict(value: str) -> dict[str, Any]:
    """Convert a string representation of a dictionary to an actual dict.

    Uses ast.literal_eval to safely parse the string.

    Args:
        value: String representation of a dictionary

    Returns:
        Parsed dictionary, or empty dict on error

    Example:
        >>> str_to_dict("{'name': 'test', 'value': 123}")
        {'name': 'test', 'value': 123}
    """
    try:
        return ast.literal_eval(value)
    except ValueError as e:
        logger.error(f"conv string failed : {e}")
        return {}


def generate_random_user_agent() -> str:
    """Generate a random realistic user agent string.

    Uses Faker library to generate user agent strings that mimic
    real browsers for web scraping and testing.

    Returns:
        Random user agent string

    Example:
        >>> ua = generate_random_user_agent()
        >>> ua
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...'
    """
    try:
        from faker import Faker

        return Faker().user_agent()
    except ImportError:
        print("warning: faker not installed, using default user agent")
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def minimum_version_required(version: str, current_version: str) -> bool:
    """Check if current version meets minimum version requirement.

    Compares semantic version strings (e.g., '1.2.3') to determine
    if the current version is greater than or equal to the required version.

    Args:
        version: Minimum required version string
        current_version: Current version string to check

    Returns:
        True if current_version >= version, False otherwise

    Example:
        >>> minimum_version_required('1.2.0', '1.3.0')
        True
        >>> minimum_version_required('2.0.0', '1.9.9')
        False
    """

    def parse_version(v: str) -> tuple:
        return tuple(map(int, v.split(".")))

    try:
        return parse_version(current_version) >= parse_version(version)
    except ValueError:
        print(f"error: invalid version format: {version} or {current_version}")
        return False
