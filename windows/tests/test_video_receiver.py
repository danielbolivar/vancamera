import threading
import time

import pytest

from certificate_handler import CertificateHandler
from video_receiver import VideoReceiver, parse_flags

from fake_phone import FakePhone


def wait_for(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def phone(tmp_path):
    p = FakePhone(tmp_path).start()
    yield p
    p.stop()


def test_parse_flags():
    assert parse_flags(0x00) == (0, False)
    assert parse_flags(0x01) == (90, False)
    assert parse_flags(0x82) == (180, True)
    assert parse_flags(0x83) == (270, True)


def test_receives_and_decodes_frames_with_flags(phone):
    frames = []
    receiver = VideoReceiver("127.0.0.1", phone.port, CertificateHandler())
    receiver.set_frame_callback(lambda f, o, b: frames.append((f.shape, o, b)))
    assert receiver.connect(), receiver.last_error
    receiver.start_receiving()
    try:
        assert wait_for(lambda: len(frames) >= 10)
        assert frames[0] == ((240, 320, 3), 90, True)
        stats = receiver.get_stats()
        assert stats.width == 320 and stats.height == 240
    finally:
        receiver.disconnect()


def test_detects_stalled_stream(phone):
    """Issue #3: a silent connection used to freeze the picture forever."""
    reasons = []
    receiver = VideoReceiver("127.0.0.1", phone.port, CertificateHandler(), stall_timeout_s=1.0)
    receiver.set_frame_callback(lambda *a: None)
    receiver.set_disconnect_callback(reasons.append)
    assert receiver.connect()
    receiver.start_receiving()
    assert wait_for(lambda: receiver.frames_decoded > 3)
    phone.paused.set()
    assert wait_for(lambda: reasons, timeout=5)
    assert "No video" in reasons[0]
    assert not receiver.is_connected()


def test_reports_closed_connection(phone):
    phone.max_packets = 5
    reasons = []
    receiver = VideoReceiver("127.0.0.1", phone.port, CertificateHandler())
    receiver.set_disconnect_callback(reasons.append)
    assert receiver.connect()
    receiver.start_receiving()
    assert wait_for(lambda: reasons)
    assert "closed" in reasons[0].lower()


def test_rejects_out_of_sync_stream(phone):
    phone.bad_size = True
    reasons = []
    receiver = VideoReceiver("127.0.0.1", phone.port, CertificateHandler())
    receiver.set_disconnect_callback(reasons.append)
    assert receiver.connect()
    receiver.start_receiving()
    assert wait_for(lambda: reasons)
    assert "Protocol error" in reasons[0]


def test_connection_refused_has_friendly_error():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    receiver = VideoReceiver("127.0.0.1", port, CertificateHandler())
    assert not receiver.connect()
    assert "refused" in receiver.last_error.lower()


def test_disconnect_does_not_fire_callback(phone):
    fired = threading.Event()
    receiver = VideoReceiver("127.0.0.1", phone.port, CertificateHandler())
    receiver.set_disconnect_callback(lambda r: fired.set())
    assert receiver.connect()
    receiver.start_receiving()
    assert wait_for(lambda: receiver.frames_decoded > 0)
    receiver.disconnect()
    assert not fired.wait(0.5)
