"""
Device discovery for VanCamera.

Discovers Android devices via:
- USB: Polling ADB for connected devices
- WiFi: Listening for mDNS services (_vancamera._tcp)
- Manual: Devices added by IP address (for networks that block mDNS, e.g. enterprise Wi-Fi)

Wi-Fi devices are keyed by the phone's stable id (TXT record ``id``) or, for older app versions,
by IP:port, never by the mDNS service name: Android renames the service ("VanCamera-Pixel (2)")
when a stale registration from a previous session is still cached on the network, which used to
make the same phone appear several times (issue #1).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import adb_forward
from adb_forward import get_device_name, list_connected_devices


DEFAULT_PORT = 8443


@dataclass
class DiscoveredDevice:
    """Represents a discovered Android device."""
    id: str              # Unique identifier ("usb:<serial>", "wifi:<id or ip:port>", "manual:<ip:port>")
    name: str            # Friendly name (e.g., "Pixel 8 Pro")
    type: str            # "usb", "wifi" or "manual"
    address: str         # "127.0.0.1" for USB, actual IP for WiFi / manual
    port: int            # Server port (default 8443)
    serial: Optional[str] = None  # ADB serial for USB devices

    @property
    def display_name(self) -> str:
        """Returns a user-friendly display name for the dropdown."""
        if self.type == "usb":
            return f"{self.name} (USB)"
        port = "" if self.port == DEFAULT_PORT else f":{self.port}"
        if self.type == "manual":
            return f"{self.name} ({self.address}{port}, manual)"
        return f"{self.name} ({self.address}{port})"


def parse_host_port(text: str, default_port: int = DEFAULT_PORT) -> Tuple[str, int]:
    """
    Parses "192.168.1.50", "192.168.1.50:8443" or "phone.local:8443".
    Raises ValueError on invalid input.
    """
    text = text.strip()
    if not text:
        raise ValueError("Enter the IP address shown on the phone")
    host, port = text, default_port
    match = re.fullmatch(r"\[?([^\[\]]+?)\]?(?::(\d{1,5}))?", text)
    if match and text.count(":") <= 1:
        host = match.group(1)
        if match.group(2):
            port = int(match.group(2))
    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid port: {port}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9\-.]*[A-Za-z0-9])?", host):
            raise ValueError(f"Invalid address: {host}")
    return host, port


def clean_service_name(name: str, type_: str = "_vancamera._tcp.local.") -> str:
    """'VanCamera-Pixel_8 (2)._vancamera._tcp.local.' -> 'Pixel 8'."""
    friendly = name
    suffix = f".{type_}"
    if friendly.endswith(suffix):
        friendly = friendly[: -len(suffix)]
    if friendly.startswith("VanCamera-"):
        friendly = friendly[len("VanCamera-"):]
    # Conflict suffix added by Android/Bonjour when the name is already taken.
    friendly = re.sub(r"\s*\(\d+\)$", "", friendly)
    friendly = friendly.replace("_", " ").strip()
    return friendly or name


class DeviceDiscovery:
    """
    Discovers and tracks available VanCamera devices.

    Supports USB devices via ADB polling, WiFi devices via mDNS and manually added devices.
    Callbacks run on background threads; UI code must marshal them to its own thread.
    """

    DEFAULT_PORT = DEFAULT_PORT
    USB_POLL_INTERVAL_S = 2.0

    def __init__(self):
        self._devices: Dict[str, DiscoveredDevice] = {}
        self._mdns_names: Dict[str, str] = {}   # mDNS service name -> device id
        self._callbacks: List[Callable[[List[DiscoveredDevice]], None]] = []
        self._lock = threading.RLock()

        # USB polling
        self._usb_poll_thread: Optional[threading.Thread] = None
        self._usb_poll_running = False
        self._usb_wakeup = threading.Event()
        self._usb_names: Dict[str, str] = {}    # serial -> model (getprop is slow, cache it)

        # Status for UI hints
        self.adb_available = False
        self.unauthorized_usb_devices = 0

        # WiFi/mDNS discovery
        self._zeroconf = None
        self._browser = None
        self._mdns_running = False
        self.mdns_available = False

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
        self._usb_poll_thread = threading.Thread(target=self._usb_poll_loop, daemon=True, name="usb-poll")
        self._usb_poll_thread.start()

    def stop_usb_polling(self):
        """Stops USB device polling."""
        self._usb_poll_running = False
        self._usb_wakeup.set()
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

            self._usb_wakeup.wait(self.USB_POLL_INTERVAL_S)
            self._usb_wakeup.clear()

    def _update_usb_devices(self):
        """Updates the list of USB devices from ADB."""
        self.adb_available = adb_forward.adb_is_available()
        if not self.adb_available:
            # Remove all USB devices if ADB is not available
            self.unauthorized_usb_devices = 0
            self._remove_devices_by_type("usb")
            return

        adb_devices = list_connected_devices()
        ready = [d for d in adb_devices if d.status == "device"]
        self.unauthorized_usb_devices = sum(1 for d in adb_devices if d.status == "unauthorized")

        current_usb_ids = set()
        added = []
        for adb_dev in ready:
            device_id = f"usb:{adb_dev.serial}"
            current_usb_ids.add(device_id)
            with self._lock:
                known = device_id in self._devices
            if known:
                continue
            name = self._usb_names.get(adb_dev.serial)
            if name is None:
                name = get_device_name(adb_dev.serial)
                self._usb_names[adb_dev.serial] = name
            added.append(DiscoveredDevice(
                id=device_id,
                name=name,
                type="usb",
                address="127.0.0.1",
                port=self.DEFAULT_PORT,
                serial=adb_dev.serial,
            ))

        with self._lock:
            changed = False
            for device in added:
                self._devices[device.id] = device
                changed = True
            to_remove = [
                dev_id for dev_id, dev in self._devices.items()
                if dev.type == "usb" and dev_id not in current_usb_ids
            ]
            for dev_id in to_remove:
                del self._devices[dev_id]
                changed = True
            if changed:
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
            self.mdns_available = True
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
        with self._lock:
            self._mdns_names.clear()
        self._remove_devices_by_type("wifi")

    @staticmethod
    def _ipv4_addresses(info) -> List[str]:
        try:
            from zeroconf import IPVersion
            return list(info.parsed_addresses(IPVersion.V4Only))
        except Exception:
            addresses = []
            for raw in getattr(info, "addresses", []) or []:
                if len(raw) == 4:
                    addresses.append(socket.inet_ntoa(raw))
            return addresses

    @staticmethod
    def _txt_value(info, key: str) -> Optional[str]:
        props = getattr(info, "properties", None) or {}
        value = props.get(key.encode(), props.get(key))
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        return value or None

    def _on_mdns_service_added(self, zc, type_: str, name: str):
        """Called when an mDNS service is discovered."""
        try:
            info = zc.get_service_info(type_, name, timeout=3000)
            if not info:
                return
            addresses = self._ipv4_addresses(info)
            if not addresses:
                return
            self.add_wifi_device(
                service_name=name,
                address=addresses[0],
                port=info.port or self.DEFAULT_PORT,
                friendly_name=clean_service_name(name, type_),
                stable_id=self._txt_value(info, "id"),
            )
        except Exception as e:
            print(f"Error processing mDNS service {name}: {e}")

    def add_wifi_device(self, service_name: str, address: str, port: int,
                        friendly_name: str, stable_id: Optional[str] = None) -> DiscoveredDevice:
        """Adds/updates a Wi-Fi device, de-duplicating by stable id and by address."""
        device_id = f"wifi:{stable_id}" if stable_id else f"wifi:{address}:{port}"
        device = DiscoveredDevice(
            id=device_id, name=friendly_name, type="wifi", address=address, port=port,
        )
        with self._lock:
            # Drop any other Wi-Fi entry for the same phone: same stable id under an old
            # service name, or a different id announcing the same address (renamed service).
            stale = [
                dev_id for dev_id, dev in self._devices.items()
                if dev.type == "wifi" and dev_id != device_id
                and (dev.address, dev.port) == (address, port)
            ]
            for dev_id in stale:
                del self._devices[dev_id]
            for svc, dev_id in list(self._mdns_names.items()):
                if dev_id in stale:
                    del self._mdns_names[svc]

            previous = self._devices.get(device_id)
            self._mdns_names[service_name] = device_id
            self._devices[device_id] = device
            if stale or previous != device:
                self._notify_change()
                print(f"mDNS: {friendly_name} at {address}:{port}")
        return device

    def _on_mdns_service_removed(self, name: str):
        """Called when an mDNS service is removed."""
        with self._lock:
            device_id = self._mdns_names.pop(name, None)
            if device_id is None:
                return
            # Another (renamed) service may still point to the same phone.
            if device_id in self._mdns_names.values():
                return
            if device_id in self._devices:
                del self._devices[device_id]
                self._notify_change()
                print(f"mDNS: Service removed {name}")

    # -------------------------------------------------------------------------
    # Manual devices
    # -------------------------------------------------------------------------

    def add_manual_device(self, address: str, port: int = DEFAULT_PORT,
                          name: Optional[str] = None) -> DiscoveredDevice:
        device = DiscoveredDevice(
            id=f"manual:{address}:{port}",
            name=name or "Phone",
            type="manual",
            address=address,
            port=port,
        )
        with self._lock:
            if self._devices.get(device.id) != device:
                self._devices[device.id] = device
                self._notify_change()
        return device

    def remove_device(self, device_id: str):
        with self._lock:
            if self._devices.pop(device_id, None) is not None:
                self._notify_change()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_devices(self) -> List[DiscoveredDevice]:
        """Returns a list of all discovered devices (USB first, then Wi-Fi, then manual)."""
        with self._lock:
            return self._sorted(self._devices.values())

    @staticmethod
    def _sorted(devices) -> List[DiscoveredDevice]:
        order = {"usb": 0, "wifi": 1, "manual": 2}
        return sorted(devices, key=lambda d: (order.get(d.type, 3), d.name.lower(), d.address))

    def get_device(self, device_id: str) -> Optional[DiscoveredDevice]:
        with self._lock:
            return self._devices.get(device_id)

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
        devices = self._sorted(self._devices.values())
        for callback in self._callbacks:
            try:
                callback(devices)
            except Exception as e:
                print(f"Error in device change callback: {e}")

    def refresh(self):
        """Forces an immediate refresh of USB devices (without blocking the caller)."""
        adb_forward.find_adb(refresh=True)
        self._usb_wakeup.set()
