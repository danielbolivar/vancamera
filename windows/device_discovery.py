"""
Device discovery for VanCamera.

Discovers Android devices via:
- USB: Polling ADB for connected devices
- WiFi: Listening for mDNS services (_vancamera._tcp)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from adb_forward import adb_is_available, list_connected_devices, get_device_name


@dataclass
class DiscoveredDevice:
    """Represents a discovered Android device."""
    id: str              # Unique identifier (serial for USB, service name for WiFi)
    name: str            # Friendly name (e.g., "Pixel 8 Pro")
    type: str            # "usb" or "wifi"
    address: str         # "127.0.0.1" for USB, actual IP for WiFi
    port: int            # Server port (default 8443)

    @property
    def display_name(self) -> str:
        """Returns a user-friendly display name for the dropdown."""
        if self.type == "usb":
            return f"{self.name} (USB)"
        else:
            return f"{self.name} ({self.address})"


class DeviceDiscovery:
    """
    Discovers and tracks available VanCamera devices.

    Supports USB devices via ADB polling and WiFi devices via mDNS.
    """

    DEFAULT_PORT = 8443
    USB_POLL_INTERVAL_S = 2.0

    def __init__(self):
        self._devices: Dict[str, DiscoveredDevice] = {}
        self._callbacks: List[Callable[[List[DiscoveredDevice]], None]] = []
        self._lock = threading.Lock()

        # USB polling
        self._usb_poll_thread: Optional[threading.Thread] = None
        self._usb_poll_running = False

        # WiFi/mDNS discovery
        self._zeroconf = None
        self._browser = None
        self._mdns_running = False

    def start(self):
        """Starts all discovery mechanisms."""
        self.start_usb_polling()
        self.start_mdns_discovery()

    def stop(self):
        """Stops all discovery mechanisms."""
        self.stop_usb_polling()
        self.stop_mdns_discovery()

    # -------------------------------------------------------------------------
    # USB Discovery (ADB polling)
    # -------------------------------------------------------------------------

    def start_usb_polling(self):
        """Starts polling for USB devices via ADB."""
        if self._usb_poll_running:
            return

        self._usb_poll_running = True
        self._usb_poll_thread = threading.Thread(target=self._usb_poll_loop, daemon=True)
        self._usb_poll_thread.start()

    def stop_usb_polling(self):
        """Stops USB device polling."""
        self._usb_poll_running = False
        if self._usb_poll_thread and self._usb_poll_thread.is_alive():
            self._usb_poll_thread.join(timeout=3)
        self._usb_poll_thread = None

    def _usb_poll_loop(self):
        """Polling loop for USB devices."""
        while self._usb_poll_running:
            try:
                self._update_usb_devices()
            except Exception as e:
                print(f"USB poll error: {e}")

            time.sleep(self.USB_POLL_INTERVAL_S)

    def _update_usb_devices(self):
        """Updates the list of USB devices from ADB."""
        if not adb_is_available():
            # Remove all USB devices if ADB is not available
            self._remove_devices_by_type("usb")
            return

        # Get current USB devices
        adb_devices = list_connected_devices()
        current_usb_ids = set()

        for adb_dev in adb_devices:
            if adb_dev.status != "device":
                continue  # Skip unauthorized or offline devices

            device_id = f"usb:{adb_dev.serial}"
            current_usb_ids.add(device_id)

            # Only add if not already tracked
            with self._lock:
                if device_id not in self._devices:
                    friendly_name = get_device_name(adb_dev.serial)
                    device = DiscoveredDevice(
                        id=device_id,
                        name=friendly_name,
                        type="usb",
                        address="127.0.0.1",
                        port=self.DEFAULT_PORT,
                    )
                    self._devices[device_id] = device
                    self._notify_change()

        # Remove USB devices that are no longer connected
        with self._lock:
            to_remove = [
                dev_id for dev_id, dev in self._devices.items()
                if dev.type == "usb" and dev_id not in current_usb_ids
            ]
            if to_remove:
                for dev_id in to_remove:
                    del self._devices[dev_id]
                self._notify_change()

    def _remove_devices_by_type(self, device_type: str):
        """Removes all devices of a given type."""
        with self._lock:
            to_remove = [
                dev_id for dev_id, dev in self._devices.items()
                if dev.type == device_type
            ]
            if to_remove:
                for dev_id in to_remove:
                    del self._devices[dev_id]
                self._notify_change()

    # -------------------------------------------------------------------------
    # WiFi Discovery (mDNS/Zeroconf)
    # -------------------------------------------------------------------------

    def start_mdns_discovery(self):
        """Starts mDNS discovery for WiFi devices."""
        if self._mdns_running:
            return

        try:
            from zeroconf import ServiceBrowser, Zeroconf, ServiceListener

            class VanCameraListener(ServiceListener):
                def __init__(self, discovery: DeviceDiscovery):
                    self.discovery = discovery

                def add_service(self, zc: Zeroconf, type_: str, name: str):
                    self.discovery._on_mdns_service_added(zc, type_, name)

                def remove_service(self, zc: Zeroconf, type_: str, name: str):
                    self.discovery._on_mdns_service_removed(name)

                def update_service(self, zc: Zeroconf, type_: str, name: str):
                    # Treat updates as re-adds
                    self.discovery._on_mdns_service_added(zc, type_, name)

            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf,
                "_vancamera._tcp.local.",
                VanCameraListener(self)
            )
            self._mdns_running = True
            print("mDNS discovery started for _vancamera._tcp.local.")

        except ImportError:
            print("zeroconf not installed - WiFi discovery disabled")
        except Exception as e:
            print(f"Failed to start mDNS discovery: {e}")

    def stop_mdns_discovery(self):
        """Stops mDNS discovery."""
        if not self._mdns_running:
            return

        try:
            if self._zeroconf:
                self._zeroconf.close()
        except Exception as e:
            print(f"Error closing zeroconf: {e}")

        self._zeroconf = None
        self._browser = None
        self._mdns_running = False

        # Remove all WiFi devices
        self._remove_devices_by_type("wifi")

    def _on_mdns_service_added(self, zc, type_: str, name: str):
        """Called when an mDNS service is discovered."""
        try:
            import socket
            info = zc.get_service_info(type_, name)
            if not info:
                return

            # Get IP address
            if info.addresses:
                ip_address = socket.inet_ntoa(info.addresses[0])
            else:
                return

            # Extract friendly name from service name (e.g., "VanCamera-Pixel8" -> "Pixel8")
            friendly_name = name.replace("VanCamera-", "").replace(f".{type_}", "")
            if not friendly_name:
                friendly_name = name

            device_id = f"wifi:{name}"

            with self._lock:
                self._devices[device_id] = DiscoveredDevice(
                    id=device_id,
                    name=friendly_name,
                    type="wifi",
                    address=ip_address,
                    port=info.port,
                )
                self._notify_change()

            print(f"mDNS: Discovered {friendly_name} at {ip_address}:{info.port}")

        except Exception as e:
            print(f"Error processing mDNS service {name}: {e}")

    def _on_mdns_service_removed(self, name: str):
        """Called when an mDNS service is removed."""
        device_id = f"wifi:{name}"

        with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                self._notify_change()
                print(f"mDNS: Service removed {name}")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_devices(self) -> List[DiscoveredDevice]:
        """Returns a list of all discovered devices."""
        with self._lock:
            return list(self._devices.values())

    def get_device_by_display_name(self, display_name: str) -> Optional[DiscoveredDevice]:
        """Finds a device by its display name."""
        with self._lock:
            for device in self._devices.values():
                if device.display_name == display_name:
                    return device
        return None

    def on_devices_changed(self, callback: Callable[[List[DiscoveredDevice]], None]):
        """
        Registers a callback to be called when devices change.

        The callback receives the updated list of devices.
        """
        self._callbacks.append(callback)

    def _notify_change(self):
        """Notifies all registered callbacks of a device change."""
        devices = list(self._devices.values())
        for callback in self._callbacks:
            try:
                callback(devices)
            except Exception as e:
                print(f"Error in device change callback: {e}")

    def refresh(self):
        """Forces an immediate refresh of USB devices."""
        self._update_usb_devices()
