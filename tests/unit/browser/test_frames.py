import numpy as np

from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSample, SelectionConfig


def frame(ts, image): return FrameSample(timestamp_ms=ts, image=image)
def blank(): return np.zeros((100, 100, 3), dtype=np.uint8)


def test_adaptive_selector_collapses_static_frames():
    result = AdaptiveFrameSelector().select([frame(i * 100, blank()) for i in range(10)], SelectionConfig())
    assert [c.selected for c in result.candidates].count(True) == 1


def test_selects_moving_rectangle_and_reports_boxes():
    frames = []
    for i, x in enumerate((10, 30, 50)):
        img = blank(); img[20:40, x:x+20] = 255; frames.append(frame(i * 200, img))
    result = AdaptiveFrameSelector().select(frames, SelectionConfig())
    assert len(result.selected) == 3
    assert result.candidates[1].change_score > 0
    assert result.candidates[1].changed_boxes


def test_high_sensitivity_keeps_subtle_change():
    a = blank(); b = blank(); b[20:30, 20:30] = 18
    low = AdaptiveFrameSelector().select([frame(0,a), frame(200,b)], SelectionConfig(sensitivity="low"))
    high = AdaptiveFrameSelector().select([frame(0,a), frame(200,b)], SelectionConfig(sensitivity="high"))
    assert len(low.selected) == 1 and len(high.selected) == 2


def test_small_pixel_noise_is_ignored_in_auto_mode():
    rng = np.random.default_rng(7)
    a = np.full((100,100,3), 80, dtype=np.uint8)
    b = np.clip(a.astype(np.int16) + rng.integers(-2, 3, a.shape), 0, 255).astype(np.uint8)
    assert len(AdaptiveFrameSelector().select([frame(0,a), frame(200,b)]).selected) == 1


def test_max_fps_limits_selected_frames():
    frames=[]
    for i in range(10):
        img=blank(); img[:, :i+1] = 255; frames.append(frame(i*20, img))
    times=[f.timestamp_ms for f in AdaptiveFrameSelector().select(frames, SelectionConfig(sensitivity="high", max_fps=10)).selected]
    assert all(b-a >= 100 for a,b in zip(times,times[1:]))
