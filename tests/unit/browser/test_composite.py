import numpy as np

from ai_workshop.browser.composite import CompositeRenderer
from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSample, SelectionConfig


def moving_frames():
    frames=[]
    for i, x in enumerate((5, 25, 45)):
        img=np.zeros((60,80,3), dtype=np.uint8); img[20:35, x:x+10]=(40,120,220)
        frames.append(FrameSample(i*200, img))
    return AdaptiveFrameSelector().select(frames, SelectionConfig())


def test_neutral_composite_shows_multiple_motion_positions():
    image=np.array(CompositeRenderer().render(moving_frames(), variant="neutral"))
    assert image[25,8].sum() > 0 and image[25,28].sum() > 0 and image[25,48].sum() > 0


def test_neutral_composite_preserves_latest_pixel_color():
    image=np.array(CompositeRenderer().render(moving_frames(), variant="neutral"))
    assert tuple(image[25,48]) == (40,120,220)


def test_time_gradient_encodes_early_and_late_differently():
    image=np.array(CompositeRenderer().render(moving_frames(), variant="time-gradient"))
    assert tuple(image[25,8]) != tuple(image[25,48])


def test_legend_is_optional_and_does_not_change_dimensions():
    renderer=CompositeRenderer(); result=moving_frames()
    a=renderer.render(result,variant="time-gradient",legend=False); b=renderer.render(result,variant="time-gradient",legend=True)
    assert a.size == b.size == (80,60)
    assert np.any(np.array(a) != np.array(b))


def test_neutral_composite_preserves_static_ui_background_color():
    frames = []
    background = (13, 27, 41)
    for i, x in enumerate((5, 25, 45)):
        img = np.zeros((40, 70, 3), dtype=np.uint8)
        img[:] = background
        img[10:20, x:x + 8] = (200, 100, 50)
        frames.append(FrameSample(i * 200, img))
    selection = AdaptiveFrameSelector().select(frames, SelectionConfig(sensitivity="high"))
    image = np.array(CompositeRenderer().render(selection, variant="neutral"))
    assert tuple(image[35, 60]) == background
