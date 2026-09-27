import socket
import time

import numpy as np
import pytest

from certificate_handler import CertificateHandler
from device_discovery import DiscoveredDevice
from stream_controller import StreamController, StreamState

from fake_phone import FakePhone
from test_video_receiver import wait_for


class FakeVcam:
    instances = []

    def __init__(self, width, height, fps):
        self.width, self.height = width, height
        self.frames = []
        self.last_error = None
        self.device_name = "Fake Camera"
        self.stopped = False
        FakeVcam.instances.append(self)

    def start(self):
        return True

    def set_size(self, width, height):
        self.width, self.height = width, height
        return True

    def send_frame(self, frame):
        assert frame.ndim == 3
        self.frames.append(frame.shape)

    def stop(self):
        self.stopped = True


class BrokenVcam(FakeVcam):
    def start(self):
        self.last_error = "driver missing"
        return False


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_controller(vcam=FakeVcam):
    FakeVcam.instances.clear()
    controller = StreamController(CertificateHandler(), vcam_factory=vcam,
                                  port_forwarder=lambda **kw: True)
    controller.RECONNECT_DELAYS_S = (0.2,)
    states = []
    controller.add_listener(lambda s: states.append(s.state))
    return controller, states


def device(port):
    return DiscoveredDevice(id=f"manual:127.0.0.1:{port}", name="Test phone", type="manual",
                            address="127.0.0.1", port=port)


def test_streams_to_virtual_camera_and_preview(tmp_path):
    phone = FakePhone(tmp_path, flags=0x01).start()  # front camera, portrait
    controller, states = make_controller()
    try:
        controller.set_preview(True, 200, 200)
        controller.start(device(phone.port))
        assert wait_for(lambda: controller.status.state == StreamState.STREAMING)
        vcam = FakeVcam.instances[0]
        assert controller.vcam_device == "Fake Camera"
        # The virtual camera follows the stream size (the fake phone sends 320x240).
        assert wait_for(lambda: (vcam.width, vcam.height) == (320, 240))
        assert wait_for(lambda: len(vcam.frames) >= 5)
        # Portrait: the 320x240 landscape frame is rotated to 240x320.
        assert vcam.frames[-1] == (320, 240, 3)
        frame, seq = controller.get_preview_frame(0)
        assert frame is not None and seq > 0
        h, w = frame.shape[:2]
        assert h <= 200 and w <= 200 and h > w
        assert frame.flags["C_CONTIGUOUS"]
    finally:
        controller.stop()
        phone.stop()
    assert FakeVcam.instances[0].stopped
    assert controller.status.state == StreamState.IDLE


def test_reconnects_after_drop_and_keeps_virtual_camera(tmp_path):
    phone = FakePhone(tmp_path).start()
    phone.max_packets = 20
    controller, states = make_controller()
    try:
        controller.start(device(phone.port))
        assert wait_for(lambda: phone.connections >= 2, timeout=15)
        assert wait_for(lambda: states.count(StreamState.STREAMING) >= 2, timeout=15)
        assert StreamState.RECONNECTING in states
        # The virtual camera is not torn down between reconnections (video apps keep working).
        assert len(FakeVcam.instances) == 1
        assert not FakeVcam.instances[0].stopped
    finally:
        controller.stop()
        phone.stop()


def test_waits_for_phone_to_start(tmp_path):
    port = free_port()
    controller, states = make_controller()
    phone = None
    try:
        controller.start(device(port))
        assert wait_for(lambda: controller.status.state == StreamState.RECONNECTING)
        assert "Waiting for the phone" in controller.status.message
        phone = FakePhone(tmp_path, port=port).start()
        assert wait_for(lambda: controller.status.state == StreamState.STREAMING, timeout=10)
    finally:
        controller.stop()
        if phone:
            phone.stop()


def test_without_auto_reconnect_reports_error(tmp_path):
    controller, states = make_controller()
    try:
        controller.start(device(free_port()), auto_reconnect=False)
        assert wait_for(lambda: controller.status.state == StreamState.ERROR)
        assert wait_for(lambda: not controller.is_active)
    finally:
        controller.stop()


def test_missing_virtual_camera_is_not_fatal(tmp_path):
    phone = FakePhone(tmp_path).start()
    controller, _ = make_controller(vcam=BrokenVcam)
    try:
        controller.set_preview(True)
        controller.start(device(phone.port))
        assert wait_for(lambda: controller.status.state == StreamState.STREAMING)
        assert controller.vcam_error == "driver missing"
        assert wait_for(lambda: controller.get_preview_frame(0)[0] is not None)
    finally:
        controller.stop()
        phone.stop()


def test_usb_device_sets_up_port_forward(tmp_path):
    phone = FakePhone(tmp_path).start()
    calls = []
    controller = StreamController(CertificateHandler(), vcam_factory=FakeVcam,
                                  port_forwarder=lambda **kw: calls.append(kw) or True)
    usb = DiscoveredDevice(id="usb:ABC", name="Pixel", type="usb", address="127.0.0.1",
                           port=phone.port, serial="ABC")
    try:
        controller.start(usb)
        assert wait_for(lambda: controller.status.state == StreamState.STREAMING)
        assert calls[0] == {"local_port": phone.port, "remote_port": phone.port, "serial": "ABC"}
    finally:
        controller.stop()
        phone.stop()
