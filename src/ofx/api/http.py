import requests

__all__ = ["fetch", "post"]

def fetch(url: str, **kwargs) -> str:
    """Send a GET request to a URL and return the response text.

    Args:
        url: The URL to send the request to
        **kwargs: Additional keyword arguments passed to requests.get()

    Returns:
        The response text

    Example:
        response = fetch("https://api.example.com/data", headers={"Authorization": "Bearer token"})
    """
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response.text


def post(url: str, data: dict | str, **kwargs) -> str:
    """Send a POST request to a URL and return the response text.

    Args:
        url: The URL to send the request to
        data: The data to send, either as a dict (for JSON) or str (for raw data)
        **kwargs: Additional keyword arguments passed to requests.post()

    Returns:
        The response text

    Example:
        response = post("https://api.example.com/data", {"key": "value"}, headers={"Content-Type": "application/json"})
    """
    response = requests.post(
        url,
        json=data if isinstance(data, dict) else None,
        data=data if isinstance(data, str) else None,
        **kwargs,
    )
    response.raise_for_status()
    return response.text
