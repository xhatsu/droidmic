"""PIN pairing authentication manager for DroidMic."""

import json
import logging
import os
import secrets
from pathlib import Path

from config import TLS_CERT_DIR

logger = logging.getLogger("droidmic.pairing")

class PairingManager:
    """Manages PIN-based device pairing and persistent storage of paired devices."""

    def __init__(self):
        self.data_dir = Path(os.path.expanduser(TLS_CERT_DIR))
        self.paired_devices_file = self.data_dir / "paired_devices.json"
        
        # Load paired devices: { "device_id": {"name": "Pixel", "paired_at": timestamp} }
        self.paired_devices: dict = {}
        self._load_paired_devices()
        
        self.current_pin: str | None = None
        self.pairing_in_progress = False

    def _load_paired_devices(self) -> None:
        """Load the list of paired devices from disk."""
        if self.paired_devices_file.exists():
            try:
                with open(self.paired_devices_file, "r") as f:
                    self.paired_devices = json.load(f)
                logger.info("Loaded %d paired devices.", len(self.paired_devices))
            except Exception as e:
                logger.error("Failed to load paired devices: %s", e)
                self.paired_devices = {}
        else:
            self.paired_devices = {}

    def _save_paired_devices(self) -> None:
        """Save the list of paired devices to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.paired_devices_file, "w") as f:
                json.dump(self.paired_devices, f, indent=2)
        except Exception as e:
            logger.error("Failed to save paired devices: %s", e)

    def is_device_paired(self, device_id: str) -> bool:
        """Check if a device is already paired."""
        return device_id in self.paired_devices

    def generate_pin(self, device_name: str) -> str:
        """Generate a random 6-digit PIN for a new pairing attempt."""
        # Use secrets module for cryptographic randomness
        self.current_pin = "".join(str(secrets.randbelow(10)) for _ in range(6))
        self.pairing_in_progress = True
        
        print("\n" + "="*50)
        print("  🔑 NEW DEVICE PAIRING REQUEST")
        print("="*50)
        print(f"  Device Name: {device_name}")
        print(f"  Enter this PIN on your device: {self.current_pin}")
        print("="*50 + "\n")
        
        return self.current_pin

    def verify_pin(self, device_id: str, device_name: str, pin: str) -> bool:
        """Verify the PIN provided by the client."""
        if not self.pairing_in_progress or self.current_pin is None:
            logger.warning("PIN verification attempted but no pairing is in progress.")
            return False
            
        if secrets.compare_digest(pin, self.current_pin):
            # Success! Save device
            import time
            self.paired_devices[device_id] = {
                "name": device_name,
                "paired_at": int(time.time())
            }
            self._save_paired_devices()
            
            logger.info("Successfully paired with device '%s' (%s)", device_name, device_id)
            self.current_pin = None
            self.pairing_in_progress = False
            return True
        else:
            logger.warning("Incorrect PIN provided by device '%s'.", device_name)
            return False

    def cancel_pairing(self):
        """Cancel an ongoing pairing request."""
        self.current_pin = None
        self.pairing_in_progress = False
        logger.info("Pairing cancelled or timed out.")
