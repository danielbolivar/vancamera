"""
Gestión de configuración de la aplicación Windows
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class AppConfig:
    """Configuración de la aplicación"""
    server_ip: str = "0.0.0.0"
    server_port: int = 443
    connection_mode: str = "wifi"  # "wifi" o "usb"
    certificate_path: Optional[str] = None
    verify_certificate: bool = False  # Para certificados auto-firmados
    video_width: int = 1280
    video_height: int = 720
    fps: int = 30


class ConfigManager:
    """Gestor de configuración persistente"""

    def __init__(self, config_file: Optional[Path] = None):
        if config_file is None:
            config_file = Path.home() / ".vancamera" / "config.json"

        self.config_file = config_file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        """Carga la configuración desde el archivo"""
        if self._config is not None:
            return self._config

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self._config = AppConfig(**data)
                    return self._config
            except Exception as e:
                print(f"Error al cargar configuración: {e}")

        # Configuración por defecto
        self._config = AppConfig()
        return self._config

    def save(self, config: AppConfig) -> bool:
        """
        Guarda la configuración en el archivo

        Args:
            config: Configuración a guardar

        Returns:
            True si se guardó correctamente
        """
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(asdict(config), f, indent=2)
            self._config = config
            return True
        except Exception as e:
            print(f"Error al guardar configuración: {e}")
            return False

    def get(self) -> AppConfig:
        """Obtiene la configuración actual"""
        if self._config is None:
            return self.load()
        return self._config

    def update(self, **kwargs) -> bool:
        """
        Actualiza valores específicos de la configuración

        Args:
            **kwargs: Valores a actualizar

        Returns:
            True si se actualizó correctamente
        """
        config = self.get()
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return self.save(config)
