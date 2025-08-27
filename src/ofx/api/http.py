import requests


def fetch(url: str, **kwargs) -> str:
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response.text


def post(url: str, data: dict | str, **kwargs) -> str:
    response = requests.post(
        url,
        json=data if isinstance(data, dict) else None,
        data=data if isinstance(data, str) else None,
        **kwargs,
    )
    response.raise_for_status()
    return response.text
