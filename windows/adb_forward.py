"""
ADB helpers for VanCamera.

Goal: when a USB device is connected, automatically run:
  adb -s <serial> forward tcp:<local_port> tcp:<remote_port>
so the user does not need to run setup_adb_forward.ps1 manually.

Finding adb (issue #2)
----------------------
The installer copies Android platform-tools to ``{app}\\platform-tools`` and adds that folder to
the user's PATH in the registry. Processes started right after the install (from the Start Menu
or the installer's "Launch" checkbox) inherit Explorer's *old* environment, so
``shutil.which("adb")`` fails until the user logs off or reboots.

``find_adb()`` therefore does not depend on the inherited PATH. It checks, in order:

1. ``VANCAMERA_ADB`` environment variable (explicit override)
2. ``platform-tools/adb(.exe)`` next to the executable / script (bundled by the installer)
3. the current PATH
4. the *current* PATH stored in the Windows registry (what a fresh logon would see)
5. well-known SDK locations (ANDROID_HOME, ANDROID_SDK_ROOT, %LOCALAPPDATA%\\Android\\Sdk, ...)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


ADB_EXE = "adb.exe" if sys.platform == "win32" else "adb"


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    status: str


# ---------------------------------------------------------------------------
# Locating adb
# ---------------------------------------------------------------------------

_adb_path: Optional[str] = None
_adb_lock = threading.Lock()


def _app_dirs() -> List[Path]:
    """Directories the app runs from: the PyInstaller exe dir and the source dir."""
    dirs: List[Path] = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass))
    dirs.append(Path(__file__).resolve().parent)
    return dirs


def _read_registry_path() -> List[str]:
    """Returns the user + machine PATH entries currently stored in the registry (Windows only)."""
    if sys.platform != "win32":
        return []
    try:
        import winreg  # type: ignore
    except ImportError:
        return []

    entries: List[str] = []
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        for entry in str(value).split(os.pathsep):
            entry = os.path.expandvars(entry.strip().strip('"'))
            if entry:
                entries.append(entry)
    return entries


def _well_known_dirs() -> List[Path]:
    dirs: List[Path] = []
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(var)
        if value:
            dirs.append(Path(value) / "platform-tools")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools")
        dirs.append(Path(local_app_data) / "Programs" / "VanCamera" / "platform-tools")
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(var)
        if value:
            dirs.append(Path(value) / "VanCamera" / "platform-tools")
    if sys.platform == "win32":
        dirs.append(Path("C:/platform-tools"))
    else:
        dirs.append(Path.home() / "Android" / "Sdk" / "platform-tools")
        dirs.append(Path.home() / "Library" / "Android" / "sdk" / "platform-tools")
    return dirs


def _candidates() -> Iterable[Path]:
    override = os.environ.get("VANCAMERA_ADB")
    if override:
        yield Path(override)

    for app_dir in _app_dirs():
        yield app_dir / "platform-tools" / ADB_EXE

    found = shutil.which("adb")
    if found:
        yield Path(found)

    for entry in _read_registry_path():
        yield Path(entry) / ADB_EXE

    for directory in _well_known_dirs():
        yield directory / ADB_EXE


def find_adb(refresh: bool = False) -> Optional[str]:
    """
    Returns the absolute path of the adb executable, or None if it cannot be found.
    The result is cached; a cached path that disappears is looked up again.
    """
    global _adb_path
    with _adb_lock:
        if not refresh and _adb_path and os.path.isfile(_adb_path):
            return _adb_path
        _adb_path = None
        for candidate in _candidates():
            try:
                if candidate.is_file():
                    _adb_path = str(candidate)
                    break
            except OSError:
                continue
        return _adb_path


def adb_is_available() -> bool:
    return find_adb() is not None


# ---------------------------------------------------------------------------
# Running adb
# ---------------------------------------------------------------------------

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


def _run_adb(args: List[str], timeout_s: int = 5) -> Optional[subprocess.CompletedProcess]:
    adb = find_adb()
    if not adb:
        return None
    flags = _get_subprocess_flags()
    flags["timeout"] = timeout_s
    try:
        return subprocess.run([adb, *args], **flags)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"ADB: failed to run 'adb {' '.join(args)}': {e}")
        return None


def parse_devices_output(output: str) -> List[AdbDevice]:
    devices: List[AdbDevice] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append(AdbDevice(serial=parts[0], status=parts[1]))
    return devices


def list_connected_devices() -> List[AdbDevice]:
    proc = _run_adb(["devices"], timeout_s=10)
    if proc is None or proc.returncode != 0:
        return []
    return parse_devices_output(proc.stdout)


def has_ready_usb_device() -> bool:
    return any(d.status == "device" for d in list_connected_devices())


def get_device_name(serial: str) -> str:
    """
    Gets the friendly device name (model) for a given serial.
    Returns the serial if the name cannot be retrieved.
    """
    proc = _run_adb(["-s", serial, "shell", "getprop", "ro.product.model"], timeout_s=5)
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return serial


def ensure_port_forward(local_port: int, remote_port: int, serial: Optional[str] = None) -> bool:
    """
    Creates/refreshes adb port forwarding.

    ``serial`` selects the phone when several are plugged in (plain ``adb forward`` fails with
    "more than one device/emulator" in that case).

    Returns True if a forward exists after this call.
    """
    if not adb_is_available():
        return False

    target = ["-s", serial] if serial else []
    if not serial and not has_ready_usb_device():
        # If there is no authorized device, don't try to forward.
        return False

    # Remove existing forward on local port (if any), then add.
    _run_adb([*target, "forward", "--remove", f"tcp:{local_port}"], timeout_s=5)

    proc = _run_adb([*target, "forward", f"tcp:{local_port}", f"tcp:{remote_port}"], timeout_s=5)
    if proc is None:
        return False
    if proc.returncode != 0:
        print(f"ADB: forward failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.returncode == 0
