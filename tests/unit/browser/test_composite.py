import numpy as np

from ai_workshop.browser.composite import CompositeRenderer
from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSelectionConfig, VideoFrame


def moving_selection():
    frames = []
    for i, x in enumerate((10, 40, 70)):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[30:50, x:x + 20] = 255
        image[80:90, 80:90] = [10, 20, 30]  # BGR stable UI color
        frames.append(VideoFrame(timestamp_ms=i * 200, image=image))
    return AdaptiveFrameSelector.select(frames, FrameSelectionConfig(sensitivity="high", max_fps=30))


def test_neutral_composite_keeps_multiple_motion_positions_visible() -> None:
    image = np.asarray(CompositeRenderer.render(moving_selection(), variant="neutral", legend=False))
    assert image[40, 15].max() > 0
    assert image[40, 45].max() > 0
    assert image[40, 75].max() > 0
    assert np.array_equal(image[0, 0], [0, 0, 0])


def test_neutral_composite_preserves_latest_pixel_color() -> None:
    image = np.asarray(CompositeRenderer.render(moving_selection(), variant="neutral", legend=False))
    assert np.array_equal(image[85, 85], [30, 20, 10])


def test_time_gradient_encodes_different_motion_times() -> None:
    image = np.asarray(CompositeRenderer.render(moving_selection(), variant="time-gradient", legend=False))
    assert not np.array_equal(image[40, 15], image[40, 45])
    assert not np.array_equal(image[40, 45], image[40, 75])


def test_legend_is_optional_and_does_not_change_dimensions() -> None:
    without = CompositeRenderer.render(moving_selection(), variant="time-gradient", legend=False)
    with_legend = CompositeRenderer.render(moving_selection(), variant="time-gradient", legend=True)
    assert without.size == (100, 100)
    assert with_legend.size == without.size
    assert not np.array_equal(np.asarray(without), np.asarray(with_legend))
