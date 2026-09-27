import time

import numpy as np

import virtual_cam_bridge
from test_video_receiver import wait_for


class RecordingCamera:
    def __init__(self, width, height, fps, fmt):
        self.size = (width, height)
        self.device = "Test Camera"
        self.sent = []
        self.closed = False

    def send(self, frame):
        self.sent.append((time.monotonic(), frame.copy()))

    def close(self):
        self.closed = True


def make_bridge(monkeypatch):
    cameras = []

    def factory(**kw):
        cameras.append(RecordingCamera(**kw))
        return cameras[-1]

    monkeypatch.setattr(virtual_cam_bridge.pyvirtualcam, "Camera", factory)
    bridge = virtual_cam_bridge.VirtualCamBridge(width=64, height=36, fps=30)
    assert bridge.start()
    bridge.cameras = cameras
    return bridge, cameras[0]


def sends_per_second(cam, window=0.5):
    last = cam.sent[-1][0]
    return len([t for t, _ in cam.sent if t > last - window]) / window


def test_resends_latest_frame_at_twice_the_frame_rate(monkeypatch):
    bridge, cam = make_bridge(monkeypatch)
    try:
        bridge.send_frame(np.full((36, 64, 3), 200, np.uint8))
        time.sleep(1.0)
        # Unity Capture drops frames unless the sender outpaces the reader: ~60 sends per second.
        assert sends_per_second(cam) >= 45
        assert (cam.sent[-1][1] == 200).all()
    finally:
        bridge.stop()
    assert cam.closed


def test_letterboxes_portrait_frames(monkeypatch):
    bridge, cam = make_bridge(monkeypatch)
    try:
        bridge.send_frame(np.full((64, 36, 3), 255, np.uint8))
        assert wait_for(lambda: cam.sent and cam.sent[-1][1][18, 32, 0] == 255)
        frame = cam.sent[-1][1]
        assert (frame[:, 0] == 0).all() and (frame[:, -1] == 0).all()
    finally:
        bridge.stop()


def test_stop_ends_the_pump(monkeypatch):
    bridge, cam = make_bridge(monkeypatch)
    bridge.stop()
    count = len(cam.sent)
    time.sleep(0.2)
    assert len(cam.sent) == count


def test_pump_doubles_a_sixty_fps_stream(monkeypatch):
    bridge, cam = make_bridge(monkeypatch)
    try:
        frame = np.zeros((36, 64, 3), np.uint8)
        end = time.perf_counter() + 1.5
        next_frame = time.perf_counter()
        while time.perf_counter() < end:
            bridge.send_frame(frame)
            next_frame += 1 / 60
            time.sleep(max(0.0, next_frame - time.perf_counter()))
        assert sends_per_second(cam) >= 90
    finally:
        bridge.stop()


def test_set_size_reopens_the_device(monkeypatch):
    bridge, first = make_bridge(monkeypatch)
    try:
        assert bridge.set_size(96, 54)
        assert first.closed
        second = bridge.cameras[-1]
        assert second.size == (96, 54)
        bridge.send_frame(np.full((54, 96, 3), 7, np.uint8))
        assert wait_for(lambda: second.sent and second.sent[-1][1].shape == (54, 96, 3)
                        and (second.sent[-1][1] == 7).all())
    finally:
        bridge.stop()
