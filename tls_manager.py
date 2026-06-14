"""TLS certificate management for DroidMic."""

import hashlib
import logging
import os
import ssl
from pathlib import Path

# Try importing cryptography, if not available we'll log an error
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import datetime
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from config import TLS_CERT_DIR, TLS_CERT_FILE, TLS_KEY_FILE

logger = logging.getLogger("droidmic.tls")

class TLSManager:
    """Manages self-signed TLS certificates for encrypted WSS transport."""

    def __init__(self):
        self.cert_dir = Path(os.path.expanduser(TLS_CERT_DIR))
        self.cert_path = self.cert_dir / TLS_CERT_FILE
        self.key_path = self.cert_dir / TLS_KEY_FILE
        
        self.cert_fingerprint: str = ""
        self.ssl_context: ssl.SSLContext | None = None

    def initialize(self) -> bool:
        """Initialize TLS: generate certs if needed, then load them.
        
        Returns True if successful, False if TLS could not be initialized.
        """
        if not HAS_CRYPTO and not (self.cert_path.exists() and self.key_path.exists()):
            logger.error("TLS requested but 'cryptography' library is not installed.")
            logger.error("Please run: pip install cryptography")
            return False

        self.cert_dir.mkdir(parents=True, exist_ok=True)

        if not self.cert_path.exists() or not self.key_path.exists():
            logger.info("No TLS certificates found. Generating new self-signed certificate...")
            self._generate_self_signed_cert()
        else:
            logger.info("Loaded existing TLS certificates from %s", self.cert_dir)

        self._calculate_fingerprint()
        
        try:
            # We don't verify the client, just encrypt the transport
            # The PIN pairing handles client authentication
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(str(self.cert_path), str(self.key_path))
            return True
        except Exception as e:
            logger.error("Failed to load SSL context: %s", e)
            return False

    def _generate_self_signed_cert(self):
        """Generate a secure, self-signed RSA 2048-bit certificate."""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Generate public certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"DroidMic Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"droidmic.local"),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            # Valid for 10 years
            datetime.datetime.utcnow() + datetime.timedelta(days=3650)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost"), x509.DNSName(u"droidmic.local")]),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        # Write key
        with open(self.key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Write cert
        with open(self.cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
            
        logger.info("Successfully generated new TLS certificate.")

    def _calculate_fingerprint(self):
        """Calculate the SHA-256 fingerprint of the certificate."""
        if not self.cert_path.exists():
            return
            
        with open(self.cert_path, "rb") as f:
            cert_data = f.read()
            
        if HAS_CRYPTO:
            # Parse PEM to get just the cert bytes
            cert = x509.load_pem_x509_certificate(cert_data)
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            fingerprint = hashlib.sha256(der_bytes).hexdigest().upper()
            # Format as AA:BB:CC...
            self.cert_fingerprint = ":".join(fingerprint[i:i+2] for i in range(0, len(fingerprint), 2))
        else:
            # Fallback if cryptography isn't available (should only happen if certs pre-exist)
            logger.warning("Cryptography not available, skipping precise fingerprint calculation.")
            self.cert_fingerprint = "UNKNOWN"
            
    def get_fingerprint(self) -> str:
        return self.cert_fingerprint
        
    def get_ssl_context(self) -> ssl.SSLContext | None:
        return self.ssl_context
