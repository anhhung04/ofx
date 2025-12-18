import base64
import json
import logging
import random
import time
from uuid import uuid4

from Cryptodome.Cipher import AES, PKCS1_OAEP
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA

from ofx.api.exploit import random_str
from ofx.api.http import requests
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class Interactsh:
    """Interactsh Out-of-Band (OOB) interaction client.

    Interactsh is an open-source tool for detecting out-of-band interactions
    (DNS, HTTP, SMTP, etc.). This client automatically handles RSA/AES encryption,
    registration, and polling for callbacks.

    Attributes:
        domain: Unique domain for this session (e.g., 'xxx.oast.me')
        server: Interactsh server hostname (default: 'oast.me')
        token: Optional authentication token for private servers
        correlation_id: Unique identifier for polling results

    Example:
        >>> interactsh = Interactsh()
        >>> url, flag = interactsh.build_request(method='http')
        >>> # Use url in your payload
        >>> time.sleep(2)
        >>> if interactsh.verify(flag):
        ...     print('Callback received!')
    """

    def __init__(self, server: str = "", token: str = ""):
        """Initialize Interactsh client with automatic registration.

        Generates RSA keys, creates unique domain, and registers with server.

        Args:
            server: Interactsh server hostname (default: 'oast.me')
            token: Optional authentication token for private servers
        """
        rsa = RSA.generate(2048)
        self.public_key = rsa.publickey().exportKey()
        self.private_key = rsa.exportKey()

        self.server = server.lstrip(".")
        self.server = self.server or "oast.me"

        self.token = token

        self.headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            self.headers["Authorization"] = self.token

        self.secret = str(uuid4())
        self.encoded = base64.b64encode(self.public_key).decode("utf8")
        guid = uuid4().hex.ljust(33, "a")
        guid = "".join(
            i if i.isdigit() else chr(ord(i) + random.randint(0, 20)) for i in guid
        )
        self.domain = f"{guid}.{self.server}"
        self.correlation_id = self.domain[:20]

        self.session = requests.session()
        self.session.headers = self.headers
        self.register()

    def register(self) -> None:
        """Register this client with the Interactsh server.

        Sends public key and correlation ID to establish encrypted session.
        Called automatically during initialization.

        Raises:
            Logs error if registration fails or authentication is invalid
        """
        data = {
            "public-key": self.encoded,
            "secret-key": self.secret,
            "correlation-id": self.correlation_id,
        }
        msg = f"[PLUGIN] Interactsh: Can not initiate {self.server} DNS callback client"
        try:
            res = self.session.post(
                f"http://{self.server}/register",
                headers=self.headers,
                json=data,
                verify=False,
            )
            if res.status_code == 401:
                logger.error("[PLUGIN] Interactsh: auth error")
            elif "success" not in res.text:
                logger.error(msg)
        except Exception:
            logger.error(msg)

    def poll(self) -> list[dict]:
        """Poll the Interactsh server for new interaction callbacks.

        Retrieves and decrypts all pending interactions for this session.
        Retries up to 3 times on failure.

        Returns:
            List of decrypted interaction data dictionaries, each containing:
            - protocol: Type of interaction ('dns', 'http', etc.)
            - full-id: Complete identifier including flag
            - raw-request: Raw request data
            - timestamp: When interaction occurred

        Example:
            >>> results = interactsh.poll()
            >>> for interaction in results:
            ...     print(interaction['protocol'], interaction['full-id'])
        """
        count = 3
        result = []
        while count:
            try:
                url = f"http://{self.server}/poll?id={self.correlation_id}&secret={self.secret}"
                res = self.session.get(url, headers=self.headers, verify=False).json()
                aes_key, data_list = res["aes_key"], res["data"]
                for i in data_list:
                    decrypt_data = self.decrypt_data(aes_key, i)
                    result.append(decrypt_data)
                return result
            except Exception:
                count -= 1
                time.sleep(1)
                continue
        return []

    def decrypt_data(self, aes_key: str, data: str) -> dict:
        """Decrypt interaction data using RSA and AES.

        Uses RSA private key to decrypt the AES key, then uses AES to
        decrypt the interaction data.

        Args:
            aes_key: Base64-encoded RSA-encrypted AES key
            data: Base64-encoded AES-encrypted interaction data

        Returns:
            Decrypted interaction data as dictionary
        """
        private_key = RSA.importKey(self.private_key)
        cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)
        aes_plain_key = cipher.decrypt(base64.b64decode(aes_key))
        decode = base64.b64decode(data)
        bs = AES.block_size
        iv = decode[:bs]
        cryptor = AES.new(key=aes_plain_key, mode=AES.MODE_CFB, IV=iv, segment_size=128)
        plain_text = cryptor.decrypt(decode)
        return json.loads(plain_text[16:])

    def build_request(self, length: int = 10, method: str = "http") -> tuple[str, str]:
        """Generate a unique URL for OOB interaction detection.

        Creates a URL with a random flag that will trigger a callback when accessed.

        Args:
            length: Length of random flag to generate (default: 10)
            method: URL scheme ('http', 'https', or '' for DNS only)

        Returns:
            Tuple of (full_url, flag) where flag can be used to verify the callback

        Example:
            >>> url, flag = interactsh.build_request(length=8, method='https')
            >>> url
            'https://abc12345.xxxxxxxx.oast.me'
            >>> flag
            'abc12345'
        """
        flag = random_str(length).lower()
        url = f"{flag}.{self.domain}"
        if method.startswith("http"):
            url = f"{method}://{url}"
        return url, flag

    def verify(self, flag: str, get_result: bool = False) -> bool | tuple[bool, list]:
        """Check if a specific flag was triggered in any interaction.

        Polls for new interactions and searches for the given flag.

        Args:
            flag: Unique identifier to search for
            get_result: If True, return full interaction data

        Returns:
            - If get_result=False: Boolean indicating if flag was found
            - If get_result=True: Tuple of (found, all_interactions)

        Example:
            >>> url, flag = interactsh.build_request()
            >>> # ... use url in exploit ...
            >>> found, interactions = interactsh.verify(flag, get_result=True)
            >>> if found:
            ...     print('Vulnerable!', interactions)
        """
        result = self.poll()
        for item in result:
            if flag.lower() in item["full-id"].lower():
                return (True, result) if get_result else True
        return (False, result) if get_result else False
