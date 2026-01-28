"""
Bridge para inyectar frames de video en OBS-VirtualCam
"""
import numpy as np
from typing import Optional
import pyvirtualcam
from pyvirtualcam import PixelFormat


class VirtualCamBridge:
    """Bridge entre el receptor de video y la cámara virtual"""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.camera: Optional[pyvirtualcam.Camera] = None
        self.is_running = False

    def start(self) -> bool:
        """
        Inicia la cámara virtual

        Returns:
            True si se inició correctamente
        """
        try:
            self.camera = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                # Use a format that pyvirtualcam supports on Windows.
                # Our decoder produces RGB frames (rgb24), so RGB is the safest choice.
                fmt=PixelFormat.RGB
            )
            self.is_running = True
            print(f"Cámara virtual iniciada: {self.width}x{self.height} @ {self.fps}fps")
            return True
        except Exception as e:
            print(f"Error al iniciar cámara virtual: {e}")
            print("Asegúrate de que OBS-VirtualCam esté instalado")
            return False

    def send_frame(self, frame: np.ndarray):
        """
        Envía un frame a la cámara virtual

        Args:
            frame: Frame en formato numpy array (RGB / RGBA / BGR / BGRA)
        """
        if not self.is_running or not self.camera:
            return

        try:
            if frame.ndim != 3 or frame.shape[2] not in (3, 4):
                print(f"Formato de frame no soportado: {frame.shape}")
                return

            # Redimensionar si es necesario
            if frame.shape[0] != self.height or frame.shape[1] != self.width:
                from PIL import Image
                img = Image.fromarray(frame)
                img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
                frame = np.array(img)

            # Ensure frame is RGB (pyvirtualcam PixelFormat.RGB expects R,G,B bytes).
            if frame.shape[2] == 4:
                # Assume RGBA and drop alpha.
                frame = frame[:, :, :3]

            # Enviar frame
            self.camera.send(frame)
            self.camera.sleep_until_next_frame()

        except Exception as e:
            print(f"Error al enviar frame: {e}")

    def stop(self):
        """Detiene la cámara virtual"""
        if self.camera:
            try:
                self.camera.close()
            except:
                pass
            self.camera = None

        self.is_running = False
        print("Cámara virtual detenida")

    def is_active(self) -> bool:
        """Verifica si la cámara virtual está activa"""
        return self.is_running and self.camera is not None
