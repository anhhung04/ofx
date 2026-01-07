"""Remote webshell connectors for HTTP APIs and file-based generation."""

import logging
from pathlib import Path

import requests

from ofx.data.webshell.connectors.base import WebshellConnector

logger = logging.getLogger(__name__)


class RemoteHTTPConnector(WebshellConnector):
    """HTTP API-based webshell generator.

    Connects to remote webshell generation services via HTTP API.

    Example:
        >>> connector = RemoteHTTPConnector(
        ...     base_url='https://webshell-api.example.com',
        ...     api_key='your-api-key'
        ... )
        >>> shell = connector.generate('php', password='x', encoder='base64')
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        endpoint: str = '/api/v1/generate',
        timeout: int = 30,
    ):
        """Initialize HTTP connector.

        Args:
            base_url: Base URL of API (e.g., 'https://api.example.com')
            api_key: Optional API key for authentication
            endpoint: API endpoint path (default: '/api/v1/generate')
            timeout: Request timeout in seconds
        """
        base_url = base_url.rstrip('/')

        super().__init__(
            name=f"remote-http-{base_url.split('//')[1].split(':')[0].split('/')[0]}",
            description=f"HTTP API connector to {base_url}"
        )
        self.base_url = base_url
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout

    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: str | None = None,
        secret_value: str | None = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell via HTTP API.

        Makes POST request to configured endpoint with generation parameters.

        Returns:
            Generated webshell code

        Raises:
            RuntimeError: If API request fails
        """
        self.validate_params(language, password, encoder)

        url = f"{self.base_url}{self.endpoint}"

        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        headers['Content-Type'] = 'application/json'

        payload = {
            'language': language,
            'password': password,
            'encoder': encoder,
            'inline': inline,
        }

        if secret_header and secret_value:
            payload['secret_header'] = secret_header
            payload['secret_value'] = secret_value

        payload.update(kwargs.get('custom_params', {}))

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            if 'code' in result:
                return result['code']
            elif 'webshell' in result:
                return result['webshell']
            else:
                raise RuntimeError(f"Unexpected API response format: {result}") from None

        except requests.RequestException as e:
            raise RuntimeError(f"HTTP API request failed: {e}") from e

    def _check_availability(self) -> bool:
        """Check if API is reachable."""
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code in (200, 404)
        except Exception:
            return False


class FileConnector(WebshellConnector):
    """File-based webshell connector.

    Loads webshells from local or network file paths.
    Supports template variables: {{PASSWORD}}, {{ENCODER}}, etc.

    Example:
        >>> connector = FileConnector(template_dir='/opt/webshells')
        >>> shell = connector.generate('php', password='x')
    """

    def __init__(self, template_dir: str):
        """Initialize file connector.

        Args:
            template_dir: Directory containing webshell template files
        """
        self.template_dir = Path(template_dir)

        super().__init__(
            name=f"file-{self.template_dir.name}",
            description=f"File-based connector from {template_dir}"
        )

    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: str | None = None,
        secret_value: str | None = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell from file template.

        Looks for files named: <language>_<encoder>.ext or <language>.ext
        Example: php_base64.php, jsp.jsp

        Returns:
            Generated webshell code

        Raises:
            RuntimeError: If template file not found
        """
        self.validate_params(language, password, encoder)

        extensions = {
            'php': 'php',
            'jsp': 'jsp',
            'java': 'jsp',
            'asp': 'asp',
            'aspx': 'aspx',
        }
        ext = extensions.get(language.lower(), language.lower())

        template_file = self.template_dir / f"{language}_{encoder}.{ext}"
        if not template_file.exists():
            template_file = self.template_dir / f"{language}.{ext}"

        if not template_file.exists():
            raise RuntimeError(
                f"Template file not found: {template_file} or "
                f"{self.template_dir}/{language}_{encoder}.{ext}"
            )

        try:
            code = template_file.read_text()

            code = code.replace('{{PASSWORD}}', password)
            code = code.replace('{{ENCODER}}', encoder)

            if secret_header and secret_value:
                code = code.replace('{{SECRET_HEADER}}', secret_header)
                code = code.replace('{{SECRET_VALUE}}', secret_value)

            if inline:
                code = code.replace('\n', ' ').replace('\t', ' ')
                code = ' '.join(code.split())

            return code

        except Exception as e:
            raise RuntimeError(f"Failed to read template file: {e}") from e

    def _check_availability(self) -> bool:
        """Check if template directory exists."""
        return self.template_dir.exists() and self.template_dir.is_dir()

    def get_supported_languages(self) -> list:
        """Get languages based on available template files."""
        if not self.template_dir.exists():
            return []

        languages = set()
        for file in self.template_dir.glob('*'):
            if file.is_file():
                name = file.stem.split('_')[0]
                languages.add(name)

        return sorted(languages)
