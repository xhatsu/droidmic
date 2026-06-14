"""mDNS discovery service advertiser for DroidMic server."""

import logging
import socket
from typing import Optional

from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

logger = logging.getLogger("droidmic.discovery")

class DroidMicServiceAdvertiser:
    """Advertises the DroidMic server on the local network via mDNS."""

    def __init__(self, port: int, use_tls: bool = False, cert_fingerprint: str = ""):
        self.port = port
        self.use_tls = use_tls
        self.cert_fingerprint = cert_fingerprint
        self.zeroconf: Optional[AsyncZeroconf] = None
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

    async def async_start(self) -> None:
        """Start advertising the service asynchronously."""
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
            self.zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
            await self.zeroconf.async_register_service(self.service_info)
            logger.info("mDNS: Advertising service '%s' at %s:%d", 
                        self.service_info.name, ip_addr, self.port)
        except Exception:
            logger.exception("Failed to start mDNS service advertisement")
            if self.zeroconf:
                await self.zeroconf.async_close()
                self.zeroconf = None

    async def async_stop(self) -> None:
        """Stop advertising the service asynchronously."""
        if self.zeroconf is not None and self.service_info is not None:
            try:
                await self.zeroconf.async_unregister_service(self.service_info)
            except Exception:
                pass
            finally:
                await self.zeroconf.async_close()
                self.zeroconf = None
                self.service_info = None
            logger.info("mDNS: Stopped service advertisement")
