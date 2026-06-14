"""mDNS discovery service advertiser for DroidMic server."""

import logging
import socket
from typing import Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf

logger = logging.getLogger("droidmic.discovery")

class DroidMicServiceAdvertiser:
    """Advertises the DroidMic server on the local network via mDNS."""

    def __init__(self, port: int, use_tls: bool = False, cert_fingerprint: str = ""):
        self.port = port
        self.use_tls = use_tls
        self.cert_fingerprint = cert_fingerprint
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None

    def _get_local_ip(self) -> str:
        """Get the primary local IP address of this machine."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def start(self) -> None:
        """Start advertising the service."""
        if self.zeroconf is not None:
            return

        ip_addr = self._get_local_ip()
        hostname = socket.gethostname()

        desc = {
            b"version": b"1.0",
            b"tls": b"true" if self.use_tls else b"false",
        }
        
        if self.cert_fingerprint:
            desc[b"fingerprint"] = self.cert_fingerprint.encode("utf-8")

        self.service_info = ServiceInfo(
            "_droidmic._tcp.local.",
            f"{hostname}._droidmic._tcp.local.",
            addresses=[socket.inet_aton(ip_addr)],
            port=self.port,
            properties=desc,
            server=f"{hostname}.local.",
        )

        try:
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            self.zeroconf.register_service(self.service_info)
            logger.info("mDNS: Advertising service '%s' at %s:%d", 
                        self.service_info.name, ip_addr, self.port)
        except Exception:
            logger.exception("Failed to start mDNS service advertisement")
            if self.zeroconf:
                self.zeroconf.close()
                self.zeroconf = None

    def stop(self) -> None:
        """Stop advertising the service."""
        if self.zeroconf is not None and self.service_info is not None:
            try:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
            except Exception:
                pass
            finally:
                self.zeroconf = None
                self.service_info = None
            logger.info("mDNS: Stopped service advertisement")
