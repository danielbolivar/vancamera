import pytest

import device_discovery as dd
from adb_forward import AdbDevice
from device_discovery import DeviceDiscovery, clean_service_name, parse_host_port


class FakeInfo:
    def __init__(self, address, port=8443, props=None):
        self._address = address
        self.port = port
        self.properties = props or {}

    def parsed_addresses(self, *_):
        return [self._address]


class FakeZeroconf:
    def __init__(self, infos):
        self.infos = infos

    def get_service_info(self, type_, name, timeout=None):
        return self.infos.get(name)


TYPE = "_vancamera._tcp.local."


def names(discovery):
    return [d.display_name for d in discovery.get_devices()]


def test_same_phone_renamed_service_is_listed_once():
    """Issue #1: reconnecting made the same phone show up again as 'VanCamera-X (2)'."""
    disc = DeviceDiscovery()
    zc = FakeZeroconf({
        f"VanCamera-Pixel_8.{TYPE}": FakeInfo("192.168.1.50"),
        f"VanCamera-Pixel_8 (2).{TYPE}": FakeInfo("192.168.1.50"),
    })
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-Pixel_8.{TYPE}")
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-Pixel_8 (2).{TYPE}")
    assert names(disc) == ["Pixel 8 (192.168.1.50)"]

    # The stale service going away must not remove the phone that is still announced.
    disc._on_mdns_service_removed(f"VanCamera-Pixel_8.{TYPE}")
    assert names(disc) == ["Pixel 8 (192.168.1.50)"]
    disc._on_mdns_service_removed(f"VanCamera-Pixel_8 (2).{TYPE}")
    assert names(disc) == []


def test_stable_id_follows_phone_across_ip_changes():
    disc = DeviceDiscovery()
    zc = FakeZeroconf({
        f"VanCamera-Pixel.{TYPE}": FakeInfo("192.168.1.50", props={b"id": b"abc123"}),
        f"VanCamera-Pixel (2).{TYPE}": FakeInfo("192.168.1.77", props={b"id": b"abc123"}),
    })
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-Pixel.{TYPE}")
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-Pixel (2).{TYPE}")
    devices = disc.get_devices()
    assert len(devices) == 1
    assert devices[0].id == "wifi:abc123"
    assert devices[0].address == "192.168.1.77"


def test_two_phones_are_both_listed():
    disc = DeviceDiscovery()
    zc = FakeZeroconf({
        f"VanCamera-A.{TYPE}": FakeInfo("192.168.1.10"),
        f"VanCamera-B.{TYPE}": FakeInfo("192.168.1.11"),
    })
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-A.{TYPE}")
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-B.{TYPE}")
    assert len(disc.get_devices()) == 2


def test_re_announcement_does_not_notify_again():
    disc = DeviceDiscovery()
    changes = []
    disc.on_devices_changed(changes.append)
    zc = FakeZeroconf({f"VanCamera-A.{TYPE}": FakeInfo("192.168.1.10")})
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-A.{TYPE}")
    disc._on_mdns_service_added(zc, TYPE, f"VanCamera-A.{TYPE}")
    assert len(changes) == 1


def test_manual_devices():
    disc = DeviceDiscovery()
    dev = disc.add_manual_device("10.0.0.12", 9000)
    assert dev.display_name == "Phone (10.0.0.12:9000, manual)"
    disc.add_manual_device("10.0.0.12", 9000)
    assert len(disc.get_devices()) == 1
    disc.remove_device(dev.id)
    assert disc.get_devices() == []


def test_usb_devices_from_adb(monkeypatch):
    monkeypatch.setattr(dd.adb_forward, "adb_is_available", lambda: True)
    monkeypatch.setattr(dd, "list_connected_devices", lambda: [
        AdbDevice("SERIAL1", "device"), AdbDevice("SERIAL2", "unauthorized")])
    calls = []
    monkeypatch.setattr(dd, "get_device_name", lambda s: calls.append(s) or "Pixel 8")
    disc = DeviceDiscovery()
    disc._update_usb_devices()
    disc._update_usb_devices()
    devices = disc.get_devices()
    assert [(d.id, d.serial, d.display_name) for d in devices] == [("usb:SERIAL1", "SERIAL1", "Pixel 8 (USB)")]
    assert disc.unauthorized_usb_devices == 1
    assert calls == ["SERIAL1"]  # model looked up once

    monkeypatch.setattr(dd, "list_connected_devices", lambda: [])
    disc._update_usb_devices()
    assert disc.get_devices() == []


def test_usb_devices_removed_when_adb_missing(monkeypatch):
    disc = DeviceDiscovery()
    monkeypatch.setattr(dd.adb_forward, "adb_is_available", lambda: False)
    disc._devices["usb:X"] = dd.DiscoveredDevice("usb:X", "X", "usb", "127.0.0.1", 8443, "X")
    disc._update_usb_devices()
    assert disc.get_devices() == []
    assert disc.adb_available is False


@pytest.mark.parametrize("text,expected", [
    ("192.168.1.50", ("192.168.1.50", 8443)),
    (" 10.0.0.2:9000 ", ("10.0.0.2", 9000)),
    ("phone.local", ("phone.local", 8443)),
    ("fe80::1", ("fe80::1", 8443)),
])
def test_parse_host_port(text, expected):
    assert parse_host_port(text) == expected


@pytest.mark.parametrize("text", ["", "192.168.1.50:99999", "bad host!", "1.2.3.4:abc"])
def test_parse_host_port_rejects(text):
    with pytest.raises(ValueError):
        parse_host_port(text)


def test_clean_service_name():
    assert clean_service_name(f"VanCamera-Samsung_SM-G991B (3).{TYPE}") == "Samsung SM-G991B"
