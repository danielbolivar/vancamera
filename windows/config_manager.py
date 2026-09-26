"""
Persistent configuration for the Windows app.
"""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional


@dataclass
class AppConfig:
    """Application settings"""
    server_ip: str = "0.0.0.0"
    # Avoid privileged ports (<1024) on Android.
    server_port: int = 8443
    connection_mode: str = "wifi"  # "wifi", "usb" or "manual"
    certificate_path: Optional[str] = None
    verify_certificate: bool = False  # Self-signed certificates
    video_width: int = 1280
    video_height: int = 720
    fps: int = 30
    # UX
    auto_reconnect: bool = True
    show_preview: bool = True
    last_device_id: Optional[str] = None
    # Phones added by IP ("192.168.1.50:8443"), for networks where mDNS is blocked.
    manual_devices: List[str] = field(default_factory=list)


class ConfigManager:
    """Persistent configuration manager"""

    def __init__(self, config_file: Optional[Path] = None):
        if config_file is None:
            config_file = Path.home() / ".vancamera" / "config.json"

        self.config_file = config_file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        """Loads the configuration from disk."""
        if self._config is not None:
            return self._config

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Ignore unknown keys (older/newer versions) instead of discarding everything.
                known = {f.name for f in fields(AppConfig)}
                self._config = AppConfig(**{k: v for k, v in data.items() if k in known})
                return self._config
            except Exception as e:
                print(f"Error loading configuration: {e}")

        # Default configuration
        self._config = AppConfig()
        return self._config

    def save(self, config: AppConfig) -> bool:
        """
        Saves the configuration to disk.

        Returns:
            True on success
        """
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config_file.with_suffix(".tmp")
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, indent=2)
            tmp.replace(self.config_file)
            self._config = config
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

    def get(self) -> AppConfig:
        """Returns the current configuration."""
        if self._config is None:
            return self.load()
        return self._config

    def update(self, **kwargs) -> bool:
        """
        Updates specific configuration values.

        Returns:
            True on success
        """
        config = self.get()
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return self.save(config)
