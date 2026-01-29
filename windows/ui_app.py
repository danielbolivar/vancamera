"""
Interfaz gráfica con CustomTkinter
"""
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk
import threading
from typing import Optional
from video_receiver import VideoReceiver
from virtual_cam_bridge import VirtualCamBridge
from certificate_handler import CertificateHandler
from config_manager import ConfigManager, AppConfig
from adb_forward import ensure_port_forward, has_ready_usb_device, adb_is_available, list_connected_devices


class VanCameraApp:
    """Aplicación principal de VanCamera Windows"""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("VanCamera")
        self.root.geometry("800x600")

        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()

        # Auto USB setup: if a device is connected over USB, setup adb port forwarding
        # so the user does not need to run setup_adb_forward.ps1 manually.
        #
        # Note: adb must be installed and on PATH for this to work.
        if has_ready_usb_device():
            if ensure_port_forward(local_port=self.config.server_port, remote_port=self.config.server_port):
                # For USB forwarding, the destination is local.
                self.config.server_ip = "127.0.0.1"
                self.config.connection_mode = "usb"
                self.config_manager.save(self.config)

        self.cert_handler = CertificateHandler()
        if self.config.certificate_path:
            from pathlib import Path
            self.cert_handler.load_certificate(Path(self.config.certificate_path))

        self.video_receiver: Optional[VideoReceiver] = None
        self.virtual_cam: Optional[VirtualCamBridge] = None

        self.is_streaming = False
        self.current_frame: Optional[np.ndarray] = None
        # Keep reference to prevent garbage collection of PhotoImage
        self._current_photo: Optional[ImageTk.PhotoImage] = None

        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz de usuario"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Preview de video
        self.preview_label = ctk.CTkLabel(
            main_frame,
            text="Sin conexión",
            width=640,
            height=360
        )
        self.preview_label.pack(pady=10)

        # Panel de controles
        controls_frame = ctk.CTkFrame(main_frame)
        controls_frame.pack(fill="x", pady=10)

        # Configuración de conexión
        conn_frame = ctk.CTkFrame(controls_frame)
        conn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(conn_frame, text="IP del Android:").pack(side="left", padx=5)
        self.ip_entry = ctk.CTkEntry(conn_frame, width=150)
        self.ip_entry.insert(0, self.config.server_ip)
        self.ip_entry.pack(side="left", padx=5)

        ctk.CTkLabel(conn_frame, text="Puerto:").pack(side="left", padx=5)
        self.port_entry = ctk.CTkEntry(conn_frame, width=80)
        self.port_entry.insert(0, str(self.config.server_port))
        self.port_entry.pack(side="left", padx=5)

        # Botones
        button_frame = ctk.CTkFrame(controls_frame)
        button_frame.pack(fill="x", padx=10, pady=5)

        self.start_button = ctk.CTkButton(
            button_frame,
            text="Iniciar Recepción",
            command=self.toggle_streaming,
            width=150
        )
        self.start_button.pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame,
            text="Configuración",
            command=self.open_settings,
            width=150
        ).pack(side="left", padx=5)

        # Estado
        self.status_label = ctk.CTkLabel(
            controls_frame,
            text="Desconectado",
            text_color="red"
        )
        self.status_label.pack(pady=5)

    def toggle_streaming(self):
        """Inicia o detiene la recepción de video"""
        if self.is_streaming:
            self.stop_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        """Inicia la recepción de video"""
        try:
            # Obtener configuración de UI
            ip = self.ip_entry.get()
            port = int(self.port_entry.get())

            # Diagnose ADB status
            if not adb_is_available():
                print("ADB: Not found in PATH. Install Android SDK Platform Tools and add to PATH.")
            else:
                devices = list_connected_devices()
                if not devices:
                    print("ADB: No devices found. Connect phone via USB and enable USB debugging.")
                else:
                    print(f"ADB: Found devices: {[(d.serial, d.status) for d in devices]}")

            # If a USB device is available, ensure adb port forwarding is active on this port.
            # This makes `adb forward tcp:port tcp:port` effectively persistent for each session.
            if has_ready_usb_device():
                print(f"ADB: Setting up port forward tcp:{port} -> tcp:{port}...")
                if ensure_port_forward(local_port=port, remote_port=port):
                    print("ADB: Port forward established successfully")
                    # For USB forwarding, the destination is always the local loopback.
                    ip = "127.0.0.1"
                    # Persist this choice so next launch reuses it.
                    self.config.connection_mode = "usb"
                else:
                    print("ADB: Port forward FAILED")
                    self.status_label.configure(
                        text="Error: could not setup ADB port forward (check adb/USB)",
                        text_color="red",
                    )
                    return
            else:
                print(f"ADB: No ready USB device. Will try direct connection to {ip}:{port}")

            # Actualizar configuración (IP puede haber cambiado si usamos USB)
            self.config.server_ip = ip
            self.config.server_port = port
            self.config_manager.save(self.config)

            # Inicializar receptor
            self.video_receiver = VideoReceiver(ip, port, self.cert_handler)
            self.video_receiver.set_frame_callback(self.on_frame_received)

            # Inicializar cámara virtual
            self.virtual_cam = VirtualCamBridge(
                width=self.config.video_width,
                height=self.config.video_height,
                fps=self.config.fps
            )

            if not self.virtual_cam.start():
                self.status_label.configure(text="Error: OBS-VirtualCam no disponible", text_color="red")
                return

            # Conectar y empezar recepción
            if self.video_receiver.connect():
                self.video_receiver.start_receiving()
                self.is_streaming = True
                self.start_button.configure(text="Detener Recepción")
                self.status_label.configure(text="Conectado", text_color="green")
            else:
                self.status_label.configure(text="Error de conexión", text_color="red")
                self.virtual_cam.stop()

        except Exception as e:
            self.status_label.configure(text=f"Error: {e}", text_color="red")

    def stop_streaming(self):
        """Detiene la recepción de video"""
        # Set flag FIRST to stop callbacks from updating UI
        self.is_streaming = False

        # Clear photo reference
        self._current_photo = None

        if self.video_receiver:
            self.video_receiver.disconnect()
            self.video_receiver = None

        if self.virtual_cam:
            self.virtual_cam.stop()
            self.virtual_cam = None

        self.start_button.configure(text="Iniciar Recepción")
        self.status_label.configure(text="Desconectado", text_color="red")

        # Reset preview safely
        try:
            self.preview_label.configure(image="", text="Sin conexión")
        except Exception:
            pass  # Ignore if widget has issues

    def on_frame_received(self, frame: np.ndarray, orientation_degrees: int = 0):
        """
        Callback cuando se recibe un frame.

        Args:
            frame: Decoded video frame (RGB numpy array)
            orientation_degrees: Device orientation (0, 90, 180, 270)
        """
        # Rotate frame based on orientation from Android device
        rotated_frame = self._rotate_frame(frame, orientation_degrees)
        self.current_frame = rotated_frame

        # Enviar a cámara virtual
        if self.virtual_cam:
            self.virtual_cam.send_frame(rotated_frame)

        # Actualizar preview en UI
        self.update_preview(rotated_frame)

    def _rotate_frame(self, frame: np.ndarray, orientation_degrees: int) -> np.ndarray:
        """
        Rotate frame based on device orientation.

        Args:
            frame: Input frame
            orientation_degrees: 0 (landscape), 90 (portrait right), 180 (landscape upside-down), 270 (portrait left)

        Returns:
            Rotated frame
        """
        if orientation_degrees == 0:
            # Landscape - no rotation needed
            return frame
        elif orientation_degrees == 90:
            # Portrait (phone rotated right) - rotate frame 90° counter-clockwise
            return np.rot90(frame, k=1)
        elif orientation_degrees == 180:
            # Upside-down landscape - rotate 180°
            return np.rot90(frame, k=2)
        elif orientation_degrees == 270:
            # Portrait (phone rotated left) - rotate frame 90° clockwise
            return np.rot90(frame, k=3)
        else:
            return frame

    def update_preview(self, frame: np.ndarray):
        """Actualiza el preview en la UI"""
        # Don't update if not streaming (prevents errors after stopping)
        if not self.is_streaming:
            return

        try:
            # Convertir a PIL Image
            img = Image.fromarray(frame)

            # Redimensionar para preview
            img.thumbnail((640, 360), Image.Resampling.LANCZOS)

            # Convertir a PhotoImage and store reference to prevent garbage collection
            self._current_photo = ImageTk.PhotoImage(image=img)

            # Actualizar label (debe hacerse en el hilo principal)
            # Use a direct reference to the stored photo
            def _update_label():
                if self.is_streaming and self._current_photo:
                    try:
                        self.preview_label.configure(image=self._current_photo, text="")
                    except Exception:
                        pass  # Ignore errors if widget was destroyed

            self.root.after(0, _update_label)

        except Exception as e:
            print(f"Error al actualizar preview: {e}")

    def open_settings(self):
        """Abre ventana de configuración"""
        settings_window = ctk.CTkToplevel(self.root)
        settings_window.title("Configuración")
        settings_window.geometry("400x300")

        # Aquí se pueden agregar más opciones de configuración
        ctk.CTkLabel(settings_window, text="Configuración de VanCamera").pack(pady=10)

        # Ruta del certificado
        cert_frame = ctk.CTkFrame(settings_window)
        cert_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(cert_frame, text="Ruta del certificado:").pack(side="left", padx=5)
        cert_entry = ctk.CTkEntry(cert_frame, width=200)
        if self.config.certificate_path:
            cert_entry.insert(0, self.config.certificate_path)
        cert_entry.pack(side="left", padx=5)

        def save_settings():
            cert_path = cert_entry.get()
            if cert_path:
                self.config.certificate_path = cert_path
                self.config_manager.save(self.config)
                self.cert_handler.load_certificate(cert_path)
            settings_window.destroy()

        ctk.CTkButton(settings_window, text="Guardar", command=save_settings).pack(pady=10)

    def run(self):
        """Ejecuta la aplicación"""
        self.root.mainloop()

        # Limpiar al cerrar
        self.stop_streaming()
