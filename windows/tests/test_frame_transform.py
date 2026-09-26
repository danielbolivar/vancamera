import numpy as np
import pytest

import frame_transform as ft


@pytest.fixture
def frame():
    # 2x3 frame with unique pixel values so we can track where each pixel ends up.
    return np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3)


@pytest.mark.parametrize("orientation,back,expected", [
    (0, True, lambda f: f),
    (90, True, lambda f: np.rot90(f, 3)),
    (180, True, lambda f: np.rot90(f, 2)),
    (270, True, lambda f: np.rot90(f, 1)),
    (0, False, lambda f: np.fliplr(f)),
    (90, False, lambda f: np.fliplr(np.rot90(f, 1))),
])
def test_preview_matches_original_behaviour(frame, orientation, back, expected):
    np.testing.assert_array_equal(ft.for_preview(frame, orientation, back), expected(frame))


@pytest.mark.parametrize("orientation,back,expected", [
    (0, True, lambda f: np.fliplr(f)),
    (90, True, lambda f: np.fliplr(np.rot90(f, 3))),
    (180, True, lambda f: np.fliplr(f)),
    (270, True, lambda f: np.fliplr(np.rot90(f, 1))),
    (0, False, lambda f: f),
    (270, False, lambda f: np.rot90(f, 3)),
])
def test_virtual_camera_matches_original_behaviour(frame, orientation, back, expected):
    np.testing.assert_array_equal(ft.for_virtual_camera(frame, orientation, back), expected(frame))


def test_fit_size_keeps_aspect():
    assert ft.fit_size(1280, 720, 640, 640) == (640, 360)
    assert ft.fit_size(720, 1280, 640, 360) == (202, 360)


def test_preview_frame_downscales_then_rotates():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    out = ft.preview_frame(frame, 90, True, 400, 400)
    assert out.shape[0] <= 400 and out.shape[1] <= 400
    assert out.shape[0] > out.shape[1]  # portrait
    assert out.flags["C_CONTIGUOUS"]


def test_resize_fallback_without_cv2(monkeypatch):
    monkeypatch.setattr(ft, "HAS_CV2", False)
    frame = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)
    assert ft.resize(frame, 2, 2).shape == (2, 2, 3)
