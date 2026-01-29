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
        Envía un frame a la cámara virtual.
        Maintains aspect ratio using letterboxing (black bars) when needed.

        Args:
            frame: Frame en formato numpy array (RGB / RGBA / BGR / BGRA)
        """
        if not self.is_running or not self.camera:
            return

        try:
            if frame.ndim != 3 or frame.shape[2] not in (3, 4):
                print(f"Formato de frame no soportado: {frame.shape}")
                return

            # Ensure frame is RGB (pyvirtualcam PixelFormat.RGB expects R,G,B bytes).
            if frame.shape[2] == 4:
                # Assume RGBA and drop alpha.
                frame = frame[:, :, :3]

            # Handle resize with aspect ratio preservation (letterboxing/pillarboxing)
            frame_h, frame_w = frame.shape[:2]

            if frame_h != self.height or frame_w != self.width:
                from PIL import Image

                # Calculate scaling to fit within target dimensions while preserving aspect ratio
                scale_w = self.width / frame_w
                scale_h = self.height / frame_h
                scale = min(scale_w, scale_h)

                new_w = int(frame_w * scale)
                new_h = int(frame_h * scale)

                # Resize the frame - use NEAREST for speed (fastest resampling)
                img = Image.fromarray(frame)
                img = img.resize((new_w, new_h), Image.Resampling.NEAREST)

                # Create black canvas at target size and paste resized image centered
                canvas = Image.new('RGB', (self.width, self.height), (0, 0, 0))
                paste_x = (self.width - new_w) // 2
                paste_y = (self.height - new_h) // 2
                canvas.paste(img, (paste_x, paste_y))

                frame = np.array(canvas)

            # Enviar frame - NO sleep_until_next_frame() to avoid 33ms blocking delay!
            self.camera.send(frame)

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
