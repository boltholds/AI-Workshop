import numpy as np

from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSelectionConfig, VideoFrame


def frame(timestamp_ms: float, image: np.ndarray) -> VideoFrame:
    return VideoFrame(timestamp_ms=timestamp_ms, image=image)


def canvas() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_adaptive_selector_collapses_static_frames() -> None:
    base = canvas()
    frames = [frame(i * 100, base.copy()) for i in range(5)]
    result = AdaptiveFrameSelector.select(frames, FrameSelectionConfig())
    assert [item.timestamp_ms for item in result.selected_frames] == [0]
    assert sum(decision.selected for decision in result.decisions) == 1


def test_moving_rectangle_selects_meaningful_frames_and_boxes() -> None:
    frames = []
    for i, x in enumerate((0, 20, 40, 60)):
        image = canvas()
        image[30:50, x:x + 20] = 255
        frames.append(frame(i * 150, image))
    result = AdaptiveFrameSelector.select(frames, FrameSelectionConfig())
    assert len(result.selected_frames) == 4
    assert all(decision.boxes for decision in result.decisions[1:])
    assert result.decisions[-1].change_score > 0


def test_manual_sensitivity_controls_subtle_small_change() -> None:
    first = canvas()
    second = first.copy()
    second[10:13, 10:13] = 30
    high = AdaptiveFrameSelector.select([frame(0, first), frame(200, second)], FrameSelectionConfig(sensitivity="high"))
    low = AdaptiveFrameSelector.select([frame(0, first), frame(200, second)], FrameSelectionConfig(sensitivity="low"))
    assert len(high.selected_frames) == 2
    assert len(low.selected_frames) == 1


def test_auto_ignores_single_pixel_noise() -> None:
    first = canvas()
    second = first.copy()
    second[50, 50] = 255
    result = AdaptiveFrameSelector.select([frame(0, first), frame(200, second)], FrameSelectionConfig(sensitivity="auto"))
    assert len(result.selected_frames) == 1


def test_max_fps_limits_dense_motion_samples() -> None:
    frames = []
    for i in range(8):
        image = canvas()
        x = i * 5
        image[20:40, x:x + 20] = 255
        frames.append(frame(i * 20, image))
    result = AdaptiveFrameSelector.select(frames, FrameSelectionConfig(sensitivity="high", max_fps=10))
    times = [item.timestamp_ms for item in result.selected_frames]
    assert times[0] == 0
    assert all(b - a >= 100 for a, b in zip(times, times[1:]))
