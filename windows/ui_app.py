"""
GUI with CustomTkinter
"""
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk
import threading
from typing import Optional, List
from video_receiver import VideoReceiver
from virtual_cam_bridge import VirtualCamBridge
from certificate_handler import CertificateHandler
from config_manager import ConfigManager, AppConfig
from adb_forward import ensure_port_forward
from device_discovery import DeviceDiscovery, DiscoveredDevice


class VanCameraApp:
    """VanCamera Windows main application"""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("VanCamera")
        self.root.geometry("800x600")

        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()

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

        # Frame dropping for low latency - track if UI update is pending
        self._ui_update_pending = False

        # Device discovery
        self.device_discovery = DeviceDiscovery()
        self.device_discovery.on_devices_changed(self._on_devices_changed)
        self._selected_device: Optional[DiscoveredDevice] = None

        self.setup_ui()

        # Start device discovery after UI is set up
        self.device_discovery.start()

    def setup_ui(self):
        """Sets up the user interface"""
        # Main frame
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Video preview
        self.preview_label = ctk.CTkLabel(
            main_frame,
            text="No connection",
            width=640,
            height=360
        )
        self.preview_label.pack(pady=10)

        # Controls panel
        controls_frame = ctk.CTkFrame(main_frame)
        controls_frame.pack(fill="x", pady=10)

        # Device selection
        device_frame = ctk.CTkFrame(controls_frame)
        device_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(device_frame, text="Device:").pack(side="left", padx=5)

        self.device_dropdown = ctk.CTkComboBox(
            device_frame,
            width=300,
            values=["Searching for devices..."],
            state="readonly",
            command=self._on_device_selected
        )
        self.device_dropdown.pack(side="left", padx=5)

        ctk.CTkButton(
            device_frame,
            text="Refresh",
            command=self._refresh_devices,
            width=80
        ).pack(side="left", padx=5)

        # Buttons
        button_frame = ctk.CTkFrame(controls_frame)
        button_frame.pack(fill="x", padx=10, pady=5)

        self.start_button = ctk.CTkButton(
            button_frame,
            text="Start Receiving",
            command=self.toggle_streaming,
            width=150
        )
        self.start_button.pack(side="left", padx=5)

        # Status
        self.status_label = ctk.CTkLabel(
            controls_frame,
            text="Searching for devices...",
            text_color="gray"
        )
        self.status_label.pack(pady=5)

    def _on_devices_changed(self, devices: List[DiscoveredDevice]):
        """Called when the list of discovered devices changes."""
        # Update dropdown on the main thread
        self.root.after(0, lambda: self._update_device_dropdown(devices))

    def _update_device_dropdown(self, devices: List[DiscoveredDevice]):
        """Updates the device dropdown with discovered devices."""
        if not devices:
            self.device_dropdown.configure(values=["No devices found"])
            self.device_dropdown.set("No devices found")
            self._selected_device = None
            if not self.is_streaming:
                self.status_label.configure(text="No devices found", text_color="gray")
            return

        # Build list of display names
        display_names = [d.display_name for d in devices]
        self.device_dropdown.configure(values=display_names)

        # If no device selected, select the first one
        current_selection = self.device_dropdown.get()
        if current_selection not in display_names:
            self.device_dropdown.set(display_names[0])
            self._selected_device = devices[0]

        if not self.is_streaming:
            self.status_label.configure(
                text=f"{len(devices)} device(s) found",
                text_color="gray"
            )

    def _on_device_selected(self, selection: str):
        """Called when user selects a device from dropdown."""
        device = self.device_discovery.get_device_by_display_name(selection)
        self._selected_device = device

    def _refresh_devices(self):
        """Forces a refresh of the device list."""
        self.status_label.configure(text="Refreshing...", text_color="gray")
        self.device_discovery.refresh()

    def toggle_streaming(self):
        """Starts or stops video reception"""
        if self.is_streaming:
            self.stop_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        """Starts video reception"""
        try:
            # Get selected device
            if not self._selected_device:
                self.status_label.configure(
                    text="No device selected",
                    text_color="red"
                )
                return

            device = self._selected_device
            ip = device.address
            port = device.port

            print(f"Connecting to {device.name} ({device.type}) at {ip}:{port}")

            # For USB devices, ensure ADB port forwarding is set up
            if device.type == "usb":
                # Extract serial from device ID (format: "usb:SERIAL")
                serial = device.id.replace("usb:", "")
                print(f"ADB: Setting up port forward tcp:{port} -> tcp:{port} for {serial}...")

                if ensure_port_forward(local_port=port, remote_port=port):
                    print("ADB: Port forward established successfully")
                    self.config.connection_mode = "usb"
                else:
                    print("ADB: Port forward FAILED")
                    self.status_label.configure(
                        text="Error: could not setup ADB port forward",
                        text_color="red",
                    )
                    return
            else:
                # WiFi connection
                self.config.connection_mode = "wifi"
                print(f"WiFi: Direct connection to {ip}:{port}")

            # Update configuration
            self.config.server_ip = ip
            self.config.server_port = port
            self.config_manager.save(self.config)

            # Initialize receiver
            self.video_receiver = VideoReceiver(ip, port, self.cert_handler)
            self.video_receiver.set_frame_callback(self.on_frame_received)

            # Initialize virtual camera
            self.virtual_cam = VirtualCamBridge(
                width=self.config.video_width,
                height=self.config.video_height,
                fps=self.config.fps
            )

            if not self.virtual_cam.start():
                self.status_label.configure(text="Error: OBS-VirtualCam not available", text_color="red")
                return

            # Update UI to show connecting status
            self.status_label.configure(text=f"Connecting to {device.name}...", text_color="gray")
            self.root.update()

            # Connect and start receiving
            if self.video_receiver.connect():
                self.video_receiver.start_receiving()
                self.is_streaming = True
                self.start_button.configure(text="Stop Receiving")
                self.status_label.configure(
                    text=f"Connected to {device.name}",
                    text_color="green"
                )
            else:
                self.status_label.configure(text="Connection error", text_color="red")
                self.virtual_cam.stop()

        except Exception as e:
            self.status_label.configure(text=f"Error: {e}", text_color="red")

    def stop_streaming(self):
        """Stops video reception"""
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

        self.start_button.configure(text="Start Receiving")
        self.status_label.configure(text="Disconnected", text_color="red")

        # Reset preview safely
        try:
            self.preview_label.configure(image="", text="No connection")
        except Exception:
            pass  # Ignore if widget has issues

    def on_frame_received(self, frame: np.ndarray, orientation_degrees: int = 0, is_back_camera: bool = False):
        """
        Callback when a frame is received.

        Args:
            frame: Decoded video frame (RGB numpy array)
            orientation_degrees: Device orientation (0, 90, 180, 270)
            is_back_camera: True if this is from the back camera (different rotation needed)
        """
        # Process frame for preview
        preview_frame = self._process_frame_for_preview(frame, orientation_degrees, is_back_camera)
        self.current_frame = preview_frame

        # Process frame for virtual camera (OBS) - may need different transformations
        if self.virtual_cam:
            vcam_frame = self._process_frame_for_vcam(frame, orientation_degrees, is_back_camera)
            self.virtual_cam.send_frame(vcam_frame)

        # Update UI preview
        self.update_preview(preview_frame)

    def _process_frame_for_preview(self, frame: np.ndarray, orientation_degrees: int, is_back_camera: bool) -> np.ndarray:
        """Process frame for UI preview display."""
        if is_back_camera:
            # Back camera transformations for PREVIEW (don't touch - working)
            if orientation_degrees == 0:
                return frame
            elif orientation_degrees == 90:
                return np.rot90(frame, k=3)
            elif orientation_degrees == 180:
                return np.rot90(frame, k=2)
            elif orientation_degrees == 270:
                return np.rot90(frame, k=1)
            else:
                return frame
        else:
            # Front camera for PREVIEW - rotate then flip horizontal
            rotated = self._rotate_front_camera(frame, orientation_degrees)
            return np.fliplr(rotated)

    def _process_frame_for_vcam(self, frame: np.ndarray, orientation_degrees: int, is_back_camera: bool) -> np.ndarray:
        """Process frame for virtual camera (OBS)."""
        if is_back_camera:
            # Back camera transformations for OBS/Virtual Camera
            # Both landscape orientations (0° and 180°) need same treatment
            if orientation_degrees == 0:
                # Landscape right - just flip horizontal
                return np.fliplr(frame)
            elif orientation_degrees == 90:
                # Portrait - rotate 270° + flip horizontal (OK)
                rotated = np.rot90(frame, k=3)
                return np.fliplr(rotated)
            elif orientation_degrees == 180:
                # Landscape left - just flip horizontal
                return np.fliplr(frame)
            elif orientation_degrees == 270:
                # Portrait upside-down - rotate 90° + flip horizontal
                rotated = np.rot90(frame, k=1)
                return np.fliplr(rotated)
            else:
                return frame
        else:
            # Front camera - standard rotation
            return self._rotate_front_camera(frame, orientation_degrees)

    def _rotate_front_camera(self, frame: np.ndarray, orientation_degrees: int) -> np.ndarray:
        """Standard rotation for front camera."""
        if orientation_degrees == 0:
            return frame
        elif orientation_degrees == 90:
            return np.rot90(frame, k=1)
        elif orientation_degrees == 180:
            return np.rot90(frame, k=2)
        elif orientation_degrees == 270:
            return np.rot90(frame, k=3)
        else:
            return frame

    def update_preview(self, frame: np.ndarray):
        """Actualiza el preview en la UI con frame dropping para baja latencia"""
        # Don't update if not streaming (prevents errors after stopping)
        if not self.is_streaming:
            return

        # Frame dropping: skip this frame if UI hasn't finished updating the previous one
        if self._ui_update_pending:
            return  # Drop frame - UI is behind

        try:
            # Convertir a PIL Image
            img = Image.fromarray(frame)

            # Redimensionar para preview - use NEAREST for speed (fastest resampling)
            img.thumbnail((640, 360), Image.Resampling.NEAREST)

            # Convertir a PhotoImage and store reference to prevent garbage collection
            self._current_photo = ImageTk.PhotoImage(image=img)

            # Mark update as pending
            self._ui_update_pending = True

            # Actualizar label (debe hacerse en el hilo principal)
            # Use a direct reference to the stored photo
            def _update_label():
                if self.is_streaming and self._current_photo:
                    try:
                        self.preview_label.configure(image=self._current_photo, text="")
                    except Exception:
                        pass  # Ignore errors if widget was destroyed
                # Mark update complete so next frame can be processed
                self._ui_update_pending = False

            self.root.after(0, _update_label)

        except Exception as e:
            self._ui_update_pending = False  # Reset on error
            print(f"Error updating preview: {e}")

    def run(self):
        """Runs the application"""
        self.root.mainloop()

        # Cleanup on close
        self.stop_streaming()
        self.device_discovery.stop()
