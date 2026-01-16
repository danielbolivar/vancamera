"""
Manejo de certificados TLS para conexión segura con Android
"""
import ssl
import socket
from pathlib import Path
from typing import Optional


class CertificateHandler:
    """Maneja la carga y validación de certificados TLS"""

    def __init__(self, cert_path: Optional[Path] = None):
        self.cert_path = cert_path
        self.certificate: Optional[bytes] = None

    def load_certificate(self, cert_path: Path) -> bool:
        """
        Carga un certificado desde un archivo PEM

        Args:
            cert_path: Ruta al archivo de certificado

        Returns:
            True si se cargó correctamente, False en caso contrario
        """
        try:
            with open(cert_path, 'r') as f:
                cert_content = f.read()
                # Extraer solo el contenido del certificado (sin headers PEM)
                cert_lines = [line for line in cert_content.split('\n')
                             if line and not line.startswith('-----')]
                cert_b64 = ''.join(cert_lines)
                self.certificate = cert_b64.encode('utf-8')
                self.cert_path = cert_path
                return True
        except Exception as e:
            print(f"Error al cargar certificado: {e}")
            return False

    def create_ssl_context(self, verify_cert: bool = True) -> ssl.SSLContext:
        """
        Crea un contexto SSL configurado para TLS 1.3

        Args:
            verify_cert: Si True, valida el certificado del servidor

        Returns:
            Contexto SSL configurado
        """
        context = ssl.create_default_context()

        # Forzar TLS 1.3
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        if not verify_cert:
            # Para desarrollo: aceptar certificados auto-firmados
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        elif self.cert_path:
            # Cargar certificado personalizado si está disponible
            try:
                context.load_verify_locations(str(self.cert_path))
            except Exception as e:
                print(f"Advertencia: No se pudo cargar certificado personalizado: {e}")
                # Continuar sin validación estricta para certificados auto-firmados
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

        return context

    def get_certificate_info(self) -> Optional[dict]:
        """
        Obtiene información del certificado cargado

        Returns:
            Diccionario con información del certificado o None
        """
        if not self.cert_path or not self.cert_path.exists():
            return None

        try:
            import cryptography.x509
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            with open(self.cert_path, 'rb') as f:
                cert_data = f.read()
                cert = x509.load_pem_x509_certificate(cert_data, default_backend())

                return {
                    'subject': cert.subject.rfc4514_string(),
                    'issuer': cert.issuer.rfc4514_string(),
                    'serial_number': str(cert.serial_number),
                    'not_valid_before': cert.not_valid_before.isoformat(),
                    'not_valid_after': cert.not_valid_after.isoformat(),
                }
        except Exception as e:
            print(f"Error al obtener información del certificado: {e}")
            return None
