"""
Receptor de video H.264 desde Android vía TLS 1.3
"""
import socket
import ssl
import struct
import threading
from typing import Optional, Callable
import numpy as np
from certificate_handler import CertificateHandler

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False
    print("Advertencia: PyAV no está instalado. La decodificación H.264 puede no funcionar correctamente.")


class VideoReceiver:
    """Recibe y decodifica stream de video H.264"""

    def __init__(self, host: str, port: int, cert_handler: CertificateHandler):
        self.host = host
        self.port = port
        self.cert_handler = cert_handler
        self.socket: Optional[socket.socket] = None
        self.ssl_socket: Optional[ssl.SSLSocket] = None
        self.is_running = False
        self.frame_callback: Optional[Callable[[np.ndarray], None]] = None
        self.receive_thread: Optional[threading.Thread] = None

        # Decodificador H.264
        self.codec_context: Optional[av.CodecContext] = None
        if HAS_AV:
            self._init_decoder()

    def _init_decoder(self):
        """Inicializa el decodificador H.264"""
        try:
            codec = av.CodecContext.create('h264', 'r')
            # Las dimensiones se ajustarán automáticamente con el primer frame
            self.codec_context = codec
        except Exception as e:
            print(f"Error al inicializar decodificador: {e}")

    def connect(self) -> bool:
        """
        Conecta al servidor Android

        Returns:
            True si la conexión fue exitosa
        """
        try:
            # Crear socket TCP
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # 10 segundos de timeout

            # Crear contexto SSL
            ssl_context = self.cert_handler.create_ssl_context(
                verify_cert=self.cert_handler.cert_path is not None
            )

            # Conectar
            self.socket.connect((self.host, self.port))

            # Envolver en SSL
            self.ssl_socket = ssl_context.wrap_socket(
                self.socket,
                server_hostname=self.host if self.cert_handler.cert_path else None
            )

            print(f"Conectado a {self.host}:{self.port}")
            return True

        except Exception as e:
            print(f"Error al conectar: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        """Desconecta del servidor"""
        self.is_running = False

        if self.ssl_socket:
            try:
                self.ssl_socket.close()
            except:
                pass
            self.ssl_socket = None

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)

    def start_receiving(self):
        """Inicia el hilo de recepción de datos"""
        if self.is_running:
            return

        if not self.ssl_socket:
            if not self.connect():
                return

        self.is_running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

    def _receive_loop(self):
        """Loop principal de recepción de datos"""
        buffer = bytearray()

        while self.is_running and self.ssl_socket:
            try:
                # Leer tamaño del paquete (4 bytes)
                size_data = self._receive_exact(4)
                if not size_data:
                    break

                packet_size = struct.unpack('>I', size_data)[0]

                # Leer datos del paquete
                packet_data = self._receive_exact(packet_size)
                if not packet_data:
                    break

                # Decodificar frame
                self._decode_frame(packet_data)

            except Exception as e:
                print(f"Error en loop de recepción: {e}")
                break

        self.is_running = False
        print("Conexión cerrada")

    def _receive_exact(self, size: int) -> Optional[bytes]:
        """Recibe exactamente 'size' bytes"""
        if not self.ssl_socket:
            return None

        data = bytearray()
        while len(data) < size:
            try:
                chunk = self.ssl_socket.recv(size - len(data))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error al recibir datos: {e}")
                return None

        return bytes(data)

    def _decode_frame(self, h264_data: bytes):
        """Decodifica un frame H.264 usando PyAV"""
        if not self.frame_callback:
            return

        if not HAS_AV or not self.codec_context:
            print("Decodificador H.264 no disponible")
            return

        try:
            # Crear un paquete AVPacket desde los datos H.264
            packet = av.Packet(h264_data)

            # Decodificar el paquete
            for frame in self.codec_context.decode(packet):
                # Convertir frame a numpy array en formato RGB
                frame_array = frame.to_ndarray(format='rgb24')

                # Llamar callback con el frame decodificado
                if self.frame_callback:
                    self.frame_callback(frame_array)

        except Exception as e:
            print(f"Error al decodificar frame: {e}")

    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """Establece el callback para recibir frames decodificados"""
        self.frame_callback = callback

    def is_connected(self) -> bool:
        """Verifica si está conectado"""
        return self.is_running and self.ssl_socket is not None
