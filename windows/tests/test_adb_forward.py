import os
import subprocess
import sys
from pathlib import Path

import pytest

import adb_forward


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real adb, PATH or registry: every test controls where adb 'exists'."""
    monkeypatch.setattr(adb_forward, "_adb_path", None)
    monkeypatch.delenv("VANCAMERA_ADB", raising=False)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr(adb_forward, "_app_dirs", lambda: [tmp_path / "app"])
    monkeypatch.setattr(adb_forward, "_read_registry_path", lambda: [])
    monkeypatch.setattr(adb_forward, "_well_known_dirs", lambda: [tmp_path / "sdk" / "platform-tools"])
    monkeypatch.setattr(adb_forward.shutil, "which", lambda name: None)
    return tmp_path


def make_adb(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    adb = directory / adb_forward.ADB_EXE
    adb.write_text("")
    return adb


def test_bundled_adb_found_without_path(isolated):
    """Issue #2: right after install the inherited PATH has no platform-tools."""
    adb = make_adb(isolated / "app" / "platform-tools")
    assert adb_forward.find_adb() == str(adb)
    assert adb_forward.adb_is_available()


def test_registry_path_used_when_process_path_is_stale(isolated, monkeypatch):
    adb = make_adb(isolated / "installed" / "platform-tools")
    monkeypatch.setattr(adb_forward, "_read_registry_path", lambda: [str(adb.parent)])
    assert adb_forward.find_adb() == str(adb)


def test_env_override_wins(isolated, monkeypatch):
    make_adb(isolated / "app" / "platform-tools")
    custom = make_adb(isolated / "custom")
    monkeypatch.setenv("VANCAMERA_ADB", str(custom))
    assert adb_forward.find_adb() == str(custom)


def test_falls_back_to_path_and_sdk(isolated, monkeypatch):
    assert adb_forward.find_adb() is None
    sdk_adb = make_adb(isolated / "sdk" / "platform-tools")
    # Negative results are not cached: installing adb later is picked up.
    assert adb_forward.find_adb() == str(sdk_adb)


def test_cached_path_is_revalidated(isolated):
    adb = make_adb(isolated / "app" / "platform-tools")
    assert adb_forward.find_adb() == str(adb)
    adb.unlink()
    assert adb_forward.find_adb() is None


def test_parse_devices_output():
    out = ("* daemon not running; starting now at tcp:5037\n* daemon started successfully\n"
           "List of devices attached\nR58M123\tdevice\nemulator-5554\tunauthorized\n\n")
    assert adb_forward.parse_devices_output(out) == [
        adb_forward.AdbDevice("R58M123", "device"),
        adb_forward.AdbDevice("emulator-5554", "unauthorized"),
    ]


def test_port_forward_targets_serial_with_resolved_adb(isolated, monkeypatch):
    adb = make_adb(isolated / "app" / "platform-tools")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(adb_forward.subprocess, "run", fake_run)
    assert adb_forward.ensure_port_forward(8443, 8443, serial="R58M123")
    assert calls == [
        [str(adb), "-s", "R58M123", "forward", "--remove", "tcp:8443"],
        [str(adb), "-s", "R58M123", "forward", "tcp:8443", "tcp:8443"],
    ]


def test_no_adb_means_no_forward(isolated):
    assert adb_forward.ensure_port_forward(8443, 8443) is False
    assert adb_forward.list_connected_devices() == []
