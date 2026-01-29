"""
ADB port-forward helper for VanCamera.

Goal: when a USB device is connected, automatically run:
  adb forward tcp:<local_port> tcp:<remote_port>
so the user does not need to run setup_adb_forward.ps1 manually.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    status: str


def _get_subprocess_flags() -> dict:
    """
    Returns subprocess flags to hide console window on Windows.
    This prevents a command prompt from flashing when running ADB commands.
    """
    flags = {
        "capture_output": True,
        "text": True,
        "check": False,
    }

    # On Windows, hide the console window
    if sys.platform == "win32":
        # CREATE_NO_WINDOW flag prevents console window from appearing
        flags["creationflags"] = subprocess.CREATE_NO_WINDOW

    return flags


def _run_adb(args: List[str], timeout_s: int = 5) -> subprocess.CompletedProcess[str]:
    flags = _get_subprocess_flags()
    flags["timeout"] = timeout_s
    return subprocess.run(args, **flags)


def adb_is_available() -> bool:
    return shutil.which("adb") is not None


def list_connected_devices() -> List[AdbDevice]:
    if not adb_is_available():
        return []

    proc = _run_adb(["adb", "devices"], timeout_s=5)
    if proc.returncode != 0:
        return []

    devices: List[AdbDevice] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append(AdbDevice(serial=parts[0], status=parts[1]))
    return devices


def has_ready_usb_device() -> bool:
    return any(d.status == "device" for d in list_connected_devices())


def get_device_name(serial: str) -> str:
    """
    Gets the friendly device name (model) for a given serial.
    Returns the serial if the name cannot be retrieved.
    """
    if not adb_is_available():
        return serial

    proc = _run_adb(["adb", "-s", serial, "shell", "getprop", "ro.product.model"], timeout_s=5)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return serial


def ensure_port_forward(local_port: int, remote_port: int) -> bool:
    """
    Creates/refreshes adb port forwarding.
    Returns True if a forward exists after this call.
    """
    if not adb_is_available():
        return False

    # If there is no authorized device, don't try to forward.
    if not has_ready_usb_device():
        return False

    # Remove existing forward on local port (if any), then add.
    _run_adb(["adb", "forward", "--remove", f"tcp:{local_port}"], timeout_s=5)

    proc = _run_adb(["adb", "forward", f"tcp:{local_port}", f"tcp:{remote_port}"], timeout_s=5)
    return proc.returncode == 0

