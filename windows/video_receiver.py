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
    # PyAV 16+ exposes specific error types like InvalidDataError and FFmpegError,
    # but does NOT have av.AVError. Import the concrete error classes instead.
    try:
        from av import InvalidDataError, FFmpegError  # type: ignore
    except Exception:
        # Fallback: treat all exceptions as generic for decoding.
        InvalidDataError = FFmpegError = Exception  # type: ignore
except ImportError:
    HAS_AV = False
    print("Advertencia: PyAV no está instalado. La decodificación H.264 puede no funcionar correctamente.")
    InvalidDataError = FFmpegError = Exception  # type: ignore


class VideoReceiver:
    """Recibe y decodifica stream de video H.264"""

    def __init__(self, host: str, port: int, cert_handler: CertificateHandler):
        self.host = host
        self.port = port
        self.cert_handler = cert_handler
        self.socket: Optional[socket.socket] = None
        self.ssl_socket: Optional[ssl.SSLSocket] = None
        self.is_running = False
        # Callback now receives (frame, orientation_degrees)
        self.frame_callback: Optional[Callable[[np.ndarray, int], None]] = None
        self.receive_thread: Optional[threading.Thread] = None

        # Decodificador H.264
        self.codec_context: Optional[av.CodecContext] = None
        if HAS_AV:
            self._init_decoder()

    def _init_decoder(self):
        """Inicializa el decodificador H.264"""
        try:
            codec = av.CodecContext.create('h264', 'r')
            # Dimensions are auto-detected from SPS/PPS in the stream
            # Enable error concealment for partial/corrupt frames
            codec.thread_type = 'AUTO'
            self.codec_context = codec
            self.decode_error_count = 0
            self.frames_decoded = 0
        except Exception as e:
            print(f"Error initializing decoder: {e}")

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

        # Reinitialize decoder for fresh connection (ensures clean state)
        if HAS_AV:
            self._init_decoder()

        self.is_running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

    def _receive_loop(self):
        """Loop principal de recepción de datos"""

        while self.is_running and self.ssl_socket:
            try:
                # Leer tamaño del paquete (4 bytes)
                size_data = self._receive_exact(4)
                if not size_data:
                    break

                packet_size = struct.unpack('>I', size_data)[0]

                # Leer datos del paquete (includes orientation byte + H.264 data)
                packet_data = self._receive_exact(packet_size)
                if not packet_data:
                    break

                # Parse flags byte (first byte)
                # Protocol: [1 byte flags][H.264 data]
                # flags: bits 0-1 = orientation (0=0°, 1=90°, 2=180°, 3=270°)
                #        bit 7 = mirror flag (for front camera)
                if len(packet_data) < 2:
                    continue  # Invalid packet

                flags_byte = packet_data[0]
                orientation_code = flags_byte & 0x03  # Only use lower 2 bits for orientation
                mirror = (flags_byte & 0x80) != 0     # Bit 7 = mirror flag
                orientation_degrees = orientation_code * 90
                h264_data = packet_data[1:]

                # Decodificar frame
                self._decode_frame(h264_data, orientation_degrees, mirror)

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

    def _decode_frame(self, h264_data: bytes, orientation_degrees: int = 0, mirror: bool = False):
        """Decodifica un frame H.264 usando PyAV"""
        if not self.frame_callback:
            return

        if not HAS_AV or not self.codec_context:
            print("H.264 decoder not available")
            return

        try:
            # Create an AVPacket from the H.264 data
            packet = av.Packet(h264_data)

            # Decode the packet - may produce 0, 1, or more frames
            for frame in self.codec_context.decode(packet):
                self.frames_decoded += 1
                # Reset error count on successful decode
                self.decode_error_count = 0

                # Convert frame to numpy array in RGB format
                frame_array = frame.to_ndarray(format='rgb24')

                # Call callback with decoded frame, orientation, and mirror flag
                if self.frame_callback:
                    self.frame_callback(frame_array, orientation_degrees, mirror)

        except (InvalidDataError, FFmpegError) as e:
            self.decode_error_count += 1
            # Only log first few errors and then periodically to avoid spam
            if self.decode_error_count <= 3 or self.decode_error_count % 100 == 0:
                print(f"Decode error ({self.decode_error_count}x): {e}")

            # If too many consecutive errors, try reinitializing the decoder
            if self.decode_error_count >= 50:
                print("Too many decode errors, reinitializing decoder...")
                self._init_decoder()
        except Exception as e:
            print(f"Unexpected decode error: {e}")

    def set_frame_callback(self, callback: Callable[[np.ndarray, int], None]):
        """
        Establece el callback para recibir frames decodificados.

        Args:
            callback: Function that receives (frame: np.ndarray, orientation_degrees: int)
                      orientation_degrees: 0, 90, 180, or 270
        """
        self.frame_callback = callback

    def is_connected(self) -> bool:
        """Verifica si está conectado"""
        return self.is_running and self.ssl_socket is not None
