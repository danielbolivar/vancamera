"""
GUI with CustomTkinter.

Tkinter is not thread safe: background threads (device discovery, streaming) never touch widgets.
They post events to a queue that the Tk main loop drains, and the preview is pulled from the
StreamController at a fixed rate. Calling Tk from the receive thread, as the old code did, can
freeze or crash the window.
"""
from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from typing import Dict, List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from certificate_handler import CertificateHandler
from config_manager import ConfigManager
from device_discovery import DeviceDiscovery, DiscoveredDevice, parse_host_port
from stream_controller import StreamController, StreamState, StreamStatus


NO_DEVICES = "No phones found"
SEARCHING = "Searching for phones…"

STATE_COLORS = {
    StreamState.IDLE: "#9CA3AF",
    StreamState.CONNECTING: "#F59E0B",
    StreamState.RECONNECTING: "#F59E0B",
    StreamState.STREAMING: "#22C55E",
    StreamState.ERROR: "#EF4444",
}


class VanCameraApp:
    """VanCamera Windows main application"""

    EVENT_POLL_MS = 50
    PREVIEW_POLL_MS = 33
    STATS_POLL_MS = 1000

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("VanCamera")
        self.root.geometry("960x680")
        self.root.minsize(720, 540)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_icon()

        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()

        self.cert_handler = CertificateHandler()
        if self.config.certificate_path:
            self.cert_handler.load_certificate(Path(self.config.certificate_path))

        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._devices_by_label: Dict[str, DiscoveredDevice] = {}
        self._selected_device: Optional[DiscoveredDevice] = None
        self._closing = False

        # Streaming
        self.controller = StreamController(
            self.cert_handler,
            vcam_size=(self.config.video_width, self.config.video_height),
            vcam_fps=self.config.fps,
        )
        self.controller.add_listener(lambda status: self._events.put(("status", status)))
        self.controller.set_preview(self.config.show_preview)
        self._preview_seq = 0
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._photo_size = (0, 0)

        # Device discovery
        self.device_discovery = DeviceDiscovery()
        self.device_discovery.on_devices_changed(lambda devices: self._events.put(("devices", devices)))
        for entry in self.config.manual_devices:
            try:
                host, port = parse_host_port(entry)
                self.device_discovery.add_manual_device(host, port)
            except ValueError:
                pass

        self.setup_ui()
        self._render_status(self.controller.status)
        self._update_device_dropdown(self.device_discovery.get_devices())

        # Start device discovery after UI is set up
        self.device_discovery.start()

        self.root.after(self.EVENT_POLL_MS, self._drain_events)
        self.root.after(self.PREVIEW_POLL_MS, self._preview_tick)
        self.root.after(self.STATS_POLL_MS, self._stats_tick)

    def _set_icon(self):
        for candidate in (Path(__file__).parent / "vancamera.ico",
                          Path(__file__).parent.parent / "logo" / "vancamera_logo.ico"):
            if candidate.exists():
                try:
                    self.root.iconbitmap(str(candidate))
                except Exception:
                    pass
                return

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Sets up the user interface"""
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Header: title + status pill
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="VanCamera", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w")

        status_frame = ctk.CTkFrame(header, corner_radius=16)
        status_frame.grid(row=0, column=2, sticky="e")
        self.status_dot = ctk.CTkLabel(status_frame, text="●", font=ctk.CTkFont(size=16), width=16)
        self.status_dot.pack(side="left", padx=(12, 4), pady=4)
        self.status_label = ctk.CTkLabel(status_frame, text="Idle")
        self.status_label.pack(side="left", padx=(0, 12), pady=4)

        # Preview (plain Tk label: pasting into one PhotoImage is much cheaper than new images)
        preview_frame = ctk.CTkFrame(self.root, corner_radius=12, fg_color="#0B0F17")
        preview_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=6)
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_label = tk.Label(
            preview_frame, bg="#0B0F17", fg="#9CA3AF", font=("Segoe UI", 13),
            text="Connect a phone to see the video here", bd=0, highlightthickness=0,
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.preview_label.bind("<Configure>", self._on_preview_resize)

        # Device selection
        device_frame = ctk.CTkFrame(self.root)
        device_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
        device_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(device_frame, text="Phone").grid(row=0, column=0, padx=(12, 8), pady=10)
        self.device_dropdown = ctk.CTkComboBox(
            device_frame,
            values=[SEARCHING],
            state="readonly",
            command=self._on_device_selected,
        )
        self.device_dropdown.set(SEARCHING)
        self.device_dropdown.grid(row=0, column=1, sticky="ew", pady=10)

        self.refresh_button = ctk.CTkButton(device_frame, text="Refresh", width=80, command=self._refresh_devices)
        self.refresh_button.grid(row=0, column=2, padx=(8, 0), pady=10)
        self.add_ip_button = ctk.CTkButton(device_frame, text="Add by IP…", width=100, command=self._add_by_ip)
        self.add_ip_button.grid(row=0, column=3, padx=(8, 0), pady=10)
        self.forget_button = ctk.CTkButton(
            device_frame, text="Forget", width=70, fg_color="transparent", border_width=1,
            command=self._forget_device,
        )
        self.forget_button.grid(row=0, column=4, padx=(8, 12), pady=10)

        # Actions
        action_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        action_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 4))
        action_frame.grid_columnconfigure(3, weight=1)

        self.start_button = ctk.CTkButton(
            action_frame, text="Connect", width=180, height=40,
            font=ctk.CTkFont(size=15, weight="bold"), command=self.toggle_streaming,
        )
        self.start_button.grid(row=0, column=0, sticky="w")

        self.preview_switch = ctk.CTkSwitch(action_frame, text="Show preview", command=self._on_preview_toggle)
        self.preview_switch.grid(row=0, column=1, padx=(20, 0))
        if self.config.show_preview:
            self.preview_switch.select()

        self.reconnect_switch = ctk.CTkSwitch(action_frame, text="Auto-reconnect", command=self._on_reconnect_toggle)
        self.reconnect_switch.grid(row=0, column=2, padx=(20, 0))
        if self.config.auto_reconnect:
            self.reconnect_switch.select()

        self.stats_label = ctk.CTkLabel(action_frame, text="", text_color="gray")
        self.stats_label.grid(row=0, column=3, sticky="e")

        # Hints
        self.hint_label = ctk.CTkLabel(self.root, text="", text_color="gray", justify="left", anchor="w")
        self.hint_label.grid(row=4, column=0, sticky="ew", padx=20, pady=(2, 12))
        self.root.bind("<Configure>", self._on_window_resize, add="+")

    def _on_window_resize(self, event):
        if event.widget is self.root:
            self.hint_label.configure(wraplength=max(300, event.width - 40))

    # ------------------------------------------------------------------
    # Event pump (main thread)
    # ------------------------------------------------------------------

    def _drain_events(self):
        if self._closing:
            return
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "devices":
                    self._update_device_dropdown(payload)
                elif kind == "status":
                    self._render_status(payload)
        except queue.Empty:
            pass
        self.root.after(self.EVENT_POLL_MS, self._drain_events)

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def _update_device_dropdown(self, devices: List[DiscoveredDevice]):
        """Updates the device dropdown with discovered devices."""
        self._devices_by_label = {d.display_name: d for d in devices}
        labels = list(self._devices_by_label)

        if not labels:
            self.device_dropdown.configure(values=[NO_DEVICES])
            self.device_dropdown.set(NO_DEVICES)
            self._selected_device = None
        else:
            self.device_dropdown.configure(values=labels)
            current = self._selected_device
            # Keep the selection when the same phone is still there (even if its label changed).
            match = next((d for d in devices if current and d.id == current.id), None)
            if match is None and self.config.last_device_id:
                match = next((d for d in devices if d.id == self.config.last_device_id), None)
            if match is None:
                match = devices[0]
            self._selected_device = match
            self.device_dropdown.set(match.display_name)

        self._update_hint()
        self._update_buttons()

    def _on_device_selected(self, selection: str):
        """Called when user selects a device from dropdown."""
        device = self._devices_by_label.get(selection)
        if device:
            self._selected_device = device
            self.config.last_device_id = device.id
            self.config_manager.save(self.config)
        self._update_buttons()

    def _refresh_devices(self):
        """Forces a refresh of the device list."""
        self.device_discovery.refresh()
        self._update_hint()

    def _add_by_ip(self):
        dialog = ctk.CTkInputDialog(
            title="Add phone by IP",
            text="Enter the address shown on the phone screen\n(for example 192.168.1.50 or 10.0.0.12:8443):",
        )
        text = dialog.get_input()
        if not text:
            return
        try:
            host, port = parse_host_port(text)
        except ValueError as e:
            self._show_hint(str(e), error=True)
            return
        device = self.device_discovery.add_manual_device(host, port)
        entry = f"{host}:{port}"
        if entry not in self.config.manual_devices:
            self.config.manual_devices.append(entry)
        self.config.last_device_id = device.id
        self._selected_device = device
        self.config_manager.save(self.config)
        self._update_device_dropdown(self.device_discovery.get_devices())

    def _forget_device(self):
        device = self._selected_device
        if not device or device.type != "manual":
            return
        entry = f"{device.address}:{device.port}"
        self.config.manual_devices = [e for e in self.config.manual_devices if e != entry]
        if self.config.last_device_id == device.id:
            self.config.last_device_id = None
        self.config_manager.save(self.config)
        self._selected_device = None
        self.device_discovery.remove_device(device.id)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def toggle_streaming(self):
        """Starts or stops video reception"""
        if self.controller.is_active:
            self.stop_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        device = self._selected_device
        if not device:
            self._show_hint("Select a phone first, or use 'Add by IP…'.", error=True)
            return
        self.config.last_device_id = device.id
        self.config.connection_mode = device.type
        self.config.server_ip = device.address
        self.config.server_port = device.port
        self.config_manager.save(self.config)
        self._update_preview_box()
        self.controller.start(device, auto_reconnect=bool(self.reconnect_switch.get()))
        self._update_buttons()

    def stop_streaming(self):
        """Stops video reception"""
        self.controller.stop()
        self._clear_preview("Connect a phone to see the video here")
        self.stats_label.configure(text="")
        self._update_buttons()

    def _render_status(self, status: StreamStatus):
        self.status_dot.configure(text_color=STATE_COLORS.get(status.state, "#9CA3AF"))
        text = {
            StreamState.IDLE: "Idle",
            StreamState.CONNECTING: "Connecting…",
            StreamState.STREAMING: "Live",
            StreamState.RECONNECTING: "Reconnecting…",
            StreamState.ERROR: "Error",
        }[status.state]
        if status.state == StreamState.STREAMING and status.device:
            text = f"Live · {status.device.name}"
        self.status_label.configure(text=text)

        if status.state in (StreamState.CONNECTING, StreamState.RECONNECTING):
            self._clear_preview(status.message)
        elif status.state == StreamState.ERROR:
            self._clear_preview(status.message)
        self._update_hint(status)
        self._update_buttons()

    def _update_buttons(self):
        active = self.controller.is_active
        self.start_button.configure(
            text="Disconnect" if active else "Connect",
            fg_color="#DC2626" if active else ("#3B8ED0", "#1F6AA5"),
            hover_color="#B91C1C" if active else ("#36719F", "#144870"),
            state="normal" if (active or self._selected_device) else "disabled",
        )
        manual = self._selected_device is not None and self._selected_device.type == "manual"
        self.forget_button.configure(state="normal" if manual and not active else "disabled")
        self.device_dropdown.configure(state="disabled" if active else "readonly")

    # ------------------------------------------------------------------
    # Hints
    # ------------------------------------------------------------------

    def _show_hint(self, text: str, error: bool = False):
        self.hint_label.configure(text=text, text_color="#F87171" if error else "gray")

    def _update_hint(self, status: Optional[StreamStatus] = None):
        status = status or self.controller.status
        disc = self.device_discovery
        if status.state in (StreamState.STREAMING, StreamState.RECONNECTING, StreamState.CONNECTING):
            if self.controller.vcam_error:
                self._show_hint(
                    "Virtual camera unavailable: install OBS-VirtualCam 2.0.5 and restart VanCamera "
                    f"({self.controller.vcam_error}). The preview still works.", error=True)
            elif status.state == StreamState.STREAMING:
                self._show_hint('In Zoom / Teams / Discord select the camera named "OBS-Camera".')
            else:
                self._show_hint(status.message)
            return
        if status.state == StreamState.ERROR:
            self._show_hint(status.message, error=True)
            return

        if disc.unauthorized_usb_devices:
            self._show_hint("A phone is connected by USB but not authorized: unlock it and accept "
                            "'Allow USB debugging'.", error=True)
        elif not self._devices_by_label:
            parts = ["Tap 'Start streaming' on the phone. Phones on the same Wi-Fi appear automatically."]
            if not disc.adb_available:
                parts.append("USB mode needs ADB, which was not found (reinstall VanCamera or install "
                             "Android platform-tools).")
            else:
                parts.append("For USB, enable USB debugging and plug in the cable.")
            parts.append("Office/university Wi-Fi often blocks discovery: use 'Add by IP…' with the "
                         "address shown on the phone.")
            self._show_hint(" ".join(parts))
        else:
            self._show_hint("Select your phone and click Connect.")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_preview_toggle(self):
        self.config.show_preview = bool(self.preview_switch.get())
        self.config_manager.save(self.config)
        self._update_preview_box()
        if not self.config.show_preview:
            self._clear_preview("Preview hidden (saves CPU). The virtual camera keeps working.")

    def _on_reconnect_toggle(self):
        self.config.auto_reconnect = bool(self.reconnect_switch.get())
        self.config_manager.save(self.config)

    def _on_preview_resize(self, _event=None):
        self._update_preview_box()

    def _update_preview_box(self):
        width = max(160, self.preview_label.winfo_width() - 4)
        height = max(90, self.preview_label.winfo_height() - 4)
        self.controller.set_preview(self.config.show_preview, width, height)

    def _clear_preview(self, text: str):
        self._photo = None
        self._photo_size = (0, 0)
        try:
            self.preview_label.configure(image="", text=text)
        except tk.TclError:
            pass

    def _preview_tick(self):
        if self._closing:
            return
        if self.config.show_preview and self.controller.status.state == StreamState.STREAMING:
            frame, self._preview_seq = self.controller.get_preview_frame(self._preview_seq)
            if frame is not None:
                self._show_frame(frame)
        self.root.after(self.PREVIEW_POLL_MS, self._preview_tick)

    def _show_frame(self, frame):
        height, width = frame.shape[:2]
        image = Image.fromarray(frame)
        try:
            if self._photo is None or self._photo_size != (width, height):
                self._photo = ImageTk.PhotoImage(image=image)
                self._photo_size = (width, height)
                self.preview_label.configure(image=self._photo, text="")
            else:
                self._photo.paste(image)
        except tk.TclError:
            pass

    def _stats_tick(self):
        if self._closing:
            return
        stats = self.controller.stats()
        if stats and self.controller.status.state == StreamState.STREAMING:
            self.stats_label.configure(
                text=f"{stats.fps:.0f} fps · {stats.kbps / 1000:.1f} Mbps · {stats.width}×{stats.height}"
            )
        else:
            self.stats_label.configure(text="")
        # The worker may have finished on its own (error without auto-reconnect).
        self._update_buttons()
        self.root.after(self.STATS_POLL_MS, self._stats_tick)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self):
        self._closing = True
        try:
            self.controller.stop()
            self.device_discovery.stop()
        finally:
            self.root.destroy()

    def run(self):
        """Runs the application"""
        self.root.mainloop()
