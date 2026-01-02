import logging
import random
import socket
import ssl
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from ofx.api.exploit import check_port, get_host_ip, get_host_ipv6
from ofx.settings import settings

__all__ = ["PHTTPServer"]

logger = logging.getLogger(settings.app_branding)


class PHTTPSingleton(type):
    """Metaclass implementing the Singleton pattern for HTTP server.

    Ensures only one instance of PHTTPServer exists.
    """

    _instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


class BaseRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler with logging.

    Extends SimpleHTTPRequestHandler to provide custom logging
    through the OFX logging system.
    """

    def do_GET(self):
        SimpleHTTPRequestHandler.do_GET(self)

    def do_HEAD(self):
        SimpleHTTPRequestHandler.do_HEAD(self)

    def log_message(self, format, *args):
        logger.info(
            f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
        )


class HTTPServerV6(HTTPServer):
    """HTTP server that uses IPv6 addressing."""

    address_family = socket.AF_INET6


class HTTPServerV4(HTTPServer):
    """HTTP server that uses IPv4 addressing."""

    address_family = socket.AF_INET


class PHTTPServer(threading.Thread, metaclass=PHTTPSingleton):
    """Threaded HTTP/HTTPS server with SSL support.

    A singleton HTTP server that runs in a separate thread and supports
    both HTTP and HTTPS protocols with automatic certificate generation.

    Example:
        >>> server = PHTTPServer(bind_ip='0.0.0.0', bind_port=8080)
        >>> server.start()
        >>> # Server is now running at http://0.0.0.0:8080
        >>> server.stop()
    """

    def __init__(
        self,
        bind_ip: str = "0.0.0.0",
        bind_port: int = 6666,
        is_ipv6: bool = False,
        use_https: bool = False,
        certfile: Path | None = None,
        requestHandler=BaseRequestHandler,
    ):
        """Initialize HTTP server.

        Args:
            bind_ip: IP address to bind to (default: '0.0.0.0')
            bind_port: Port to bind to (default: 6666)
            is_ipv6: Use IPv6 addressing (default: False)
            use_https: Enable HTTPS with SSL (default: False)
            certfile: Path to SSL certificate file (auto-generated if None)
            requestHandler: Custom request handler class
        """
        threading.Thread.__init__(self)
        self.bind_ip = bind_ip
        self.bind_port = int(bind_port)
        self.is_ipv6 = is_ipv6
        self.https = use_https

        if self.https:
            self.scheme = "https"
            if certfile is None:
                certfile = (
                    Path.home() / ".local" / "share" / "ofx" / "tmp" / "cacert.pem"
                )
            self._gen_cert(certfile)
        else:
            self.scheme = "http"

        self.certfile = certfile
        self.server_locked = False
        self.server_started = False
        self.requestHandler = requestHandler

        if ":" in bind_ip:
            ipv6 = get_host_ipv6()
            if not ipv6:
                logger.error("Your machine may not support ipv6")
                raise RuntimeError("IPv6 not supported")
            self.host_ip = ipv6
            self.httpserver = HTTPServerV6
            self.is_ipv6 = True
        else:
            self.is_ipv6 = False
            self.host_ip = get_host_ip()
            self.httpserver = HTTPServerV4

        self.url = f"{self.scheme}://{self.bind_ip}:{self.bind_port}"
        if self.is_ipv6:
            self.url = f"{self.scheme}://[{self.bind_ip}]:{self.bind_port}"

        self.__flag = threading.Event()
        self.__flag.set()
        self.__running = threading.Event()
        self.__running.set()

    def _gen_cert(self, filepath: Path) -> None:
        """Generate a self-signed SSL certificate for HTTPS.

        Creates a 2048-bit RSA key and X.509 certificate valid for 365 days,
        with localhost and *.localhost as Subject Alternative Names.

        Args:
            filepath: Path where the PEM-encoded certificate and key will be saved

        Note:
            The generated certificate is self-signed and will trigger browser
            warnings. For production use, obtain a properly signed certificate.
        """
        import datetime

        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        filepath.parent.mkdir(parents=True, exist_ok=True)

        key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OFX"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.DNSName("*.localhost"),
                    ]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )

        with open(filepath, "wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            f.write(cert.public_bytes(serialization.Encoding.PEM))

    def start(self, daemon: bool = True) -> None:
        """Start the HTTP/HTTPS server in a background thread.

        Checks port availability, starts the server thread, and waits for
        the server to become ready (up to 10 retry attempts).

        Args:
            daemon: Run as daemon thread that exits when main program exits (default: True)

        Raises:
            Logs error if port is already occupied and returns without starting

        Example:
            >>> server = PHTTPServer(bind_ip='0.0.0.0', bind_port=8080)
            >>> server.start()
            [INFO] Starting httpd on http://0.0.0.0:8080
            >>> # Server is now running in background
        """
        if self.server_locked:
            logger.info(f"Httpd serve has been started on {self.url}")
            return

        self.check_ip = self.host_ip
        if self.bind_ip == "0.0.0.0":
            self.check_ip = "127.0.0.1"
        elif self.bind_ip == "::":
            self.check_ip = "::1"

        if check_port(self.check_ip, self.bind_port):
            logger.error(
                f"Port {self.bind_port} has been occupied, start Httpd serve failed!"
            )
            return

        self.server_locked = True
        self.setDaemon(daemon)
        threading.Thread.start(self)

        logger.info(f"Detect {self.scheme} server is runing or not...")
        detect_count = 10
        while detect_count:
            try:
                if check_port(self.check_ip, self.bind_port):
                    break
            except Exception as ex:
                logger.error(str(ex))
            time.sleep(random.random())
            detect_count -= 1

    def run(self) -> None:
        """Internal server loop executed in background thread.

        Initializes HTTPServer instance, wraps socket with SSL if HTTPS is enabled,
        and runs the server's serve_forever() loop. Handles cleanup on exit.

        Warning:
            This method is called automatically by threading.Thread.start().
            Do not call directly. Use start() method instead.
        """
        try:
            while self.__running.is_set():
                time.sleep(1)
                self.__flag.wait()
                if not self.server_started:
                    self.httpd = self.httpserver(
                        (self.bind_ip, self.bind_port), self.requestHandler
                    )
                    logger.info(f"Starting httpd on {self.url}")
                    if self.https:
                        if self.certfile:
                            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                            context.load_cert_chain(str(self.certfile))
                            self.httpd.socket = context.wrap_socket(
                                self.httpd.socket, server_side=True
                            )
                        else:
                            logger.error("You must provide certfile to use https")
                            break
                    thread = threading.Thread(target=self.httpd.serve_forever)
                    thread.setDaemon(True)
                    thread.start()
                    self.server_started = True
                    self.__flag.clear()
            self.httpd.shutdown()
            self.httpd.server_close()
            logger.info(f"Stop httpd server on {self.url}")
        except Exception as ex:
            if hasattr(self, "httpd"):
                self.httpd.shutdown()
                self.httpd.server_close()
            logger.error(str(ex))

    def pause(self) -> None:
        """Pause the HTTP server without terminating the thread.

        Temporarily halts request handling while keeping the thread alive.
        Use resume() to restart request handling.

        Example:
            >>> server.pause()
            >>> # Server stops accepting requests
            >>> server.resume()
            >>> # Server resumes accepting requests
        """
        self.__flag.clear()

    def resume(self) -> None:
        """Resume a paused HTTP server to continue handling requests.

        Restarts request handling after a pause() call.
        """
        self.__flag.set()

    def stop(self) -> None:
        """Stop the HTTP server and release all resources.

        Performs graceful shutdown: signals thread to exit, waits 1-3 seconds
        for cleanup, and closes server socket.

        Example:
            >>> server.stop()
            [INFO] Stop httpd server on http://0.0.0.0:8080
        """
        self.__flag.set()
        self.__running.clear()
        time.sleep(random.randint(1, 3))
