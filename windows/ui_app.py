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
from adb_forward import ensure_port_forward, has_ready_usb_device


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

            # If a USB device is available, ensure adb port forwarding is active on this port.
            # This makes `adb forward tcp:port tcp:port` effectively persistent for each session.
            if has_ready_usb_device():
                if ensure_port_forward(local_port=port, remote_port=port):
                    # For USB forwarding, the destination is always the local loopback.
                    ip = "127.0.0.1"
                    # Persist this choice so next launch reuses it.
                    self.config.connection_mode = "usb"
                else:
                    self.status_label.configure(
                        text="Error: could not setup ADB port forward (check adb/USB)",
                        text_color="red",
                    )
                    return

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
        if self.video_receiver:
            self.video_receiver.disconnect()
            self.video_receiver = None

        if self.virtual_cam:
            self.virtual_cam.stop()
            self.virtual_cam = None

        self.is_streaming = False
        self.start_button.configure(text="Iniciar Recepción")
        self.status_label.configure(text="Desconectado", text_color="red")
        self.preview_label.configure(image=None, text="Sin conexión")

    def on_frame_received(self, frame: np.ndarray):
        """Callback cuando se recibe un frame"""
        self.current_frame = frame

        # Enviar a cámara virtual
        if self.virtual_cam:
            self.virtual_cam.send_frame(frame)

        # Actualizar preview en UI
        self.update_preview(frame)

    def update_preview(self, frame: np.ndarray):
        """Actualiza el preview en la UI"""
        try:
            # Convertir a PIL Image
            img = Image.fromarray(frame)

            # Redimensionar para preview
            img.thumbnail((640, 360), Image.Resampling.LANCZOS)

            # Convertir a PhotoImage
            photo = ImageTk.PhotoImage(image=img)

            # Actualizar label (debe hacerse en el hilo principal)
            self.root.after(0, lambda: self.preview_label.configure(image=photo, text=""))

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
