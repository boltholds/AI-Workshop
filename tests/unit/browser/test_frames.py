import numpy as np

from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSample, SelectionConfig


def frame(ts: int, image: np.ndarray) -> FrameSample:
    return FrameSample(timestamp_ms=ts, image=image)


def blank():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_adaptive_selector_collapses_static_frames():
    frames = [frame(i * 100, blank()) for i in range(10)]
    result = AdaptiveFrameSelector().select(frames, SelectionConfig(sensitivity="auto", max_fps=10))
    assert [c.selected for c in result.candidates].count(True) == 1


def test_selects_moving_rectangle_and_reports_boxes():
    frames=[]
    for i,x in enumerate((10,30,50)):
        img=blank(); img[20:40,x:x+20]=255; frames.append(frame(i*200,img))
    result=AdaptiveFrameSelector().select(frames,SelectionConfig(sensitivity="auto",max_fps=10))
    assert len(result.selected)==3
    assert result.candidates[1].changed_boxes


def test_high_sensitivity_keeps_subtle_change():
    a=blank(); b=blank(); b[20:30,20:30]=18
    low=AdaptiveFrameSelector().select([frame(0,a),frame(200,b)],SelectionConfig(sensitivity="low",max_fps=10))
    high=AdaptiveFrameSelector().select([frame(0,a),frame(200,b)],SelectionConfig(sensitivity="high",max_fps=10))
    assert len(low.selected)==1 and len(high.selected)==2


def test_small_pixel_noise_is_ignored_in_auto_mode():
    rng=np.random.default_rng(7)
    a=np.full((100,100,3),80,dtype=np.uint8)
    b=np.clip(a.astype(np.int16)+rng.integers(-2,3,a.shape),0,255).astype(np.uint8)
    assert len(AdaptiveFrameSelector().select([frame(0,a),frame(200,b)],SelectionConfig()).selected)==1


def test_max_fps_limits_selected_frames():
    frames=[]
    for i in range(10):
        img=blank(); img[:,:i+1]=255; frames.append(frame(i*20,img))
    times=[f.timestamp_ms for f in AdaptiveFrameSelector().select(frames,SelectionConfig(sensitivity="high",max_fps=10)).selected]
    assert all(b-a >= 100 for a,b in zip(times,times[1:]))


def test_incremental_subthreshold_changes_accumulate_against_last_selected():
    frames=[]; image=blank(); frames.append(frame(0,image.copy()))
    for i in range(1,8):
        image=image.copy(); x=2*i; image[10:12,x:x+2]=255; frames.append(frame(i*50,image.copy()))
    result=AdaptiveFrameSelector().select(frames,SelectionConfig(sensitivity="auto",max_fps=20))
    assert len(result.selected)>=2
    assert result.selected[-1].timestamp_ms>=250


def test_auto_threshold_adapts_to_noisy_background_but_keeps_real_motion():
    rng=np.random.default_rng(42)
    base=np.full((100,100,3),80,dtype=np.uint8)
    noise=rng.integers(-15,16,base.shape)
    noisy=np.clip(base.astype(np.int16)+noise,0,255).astype(np.uint8)
    noise_only=AdaptiveFrameSelector().select(
        [frame(0,base),frame(200,noisy)],
        SelectionConfig(sensitivity="auto",max_fps=10),
    )
    assert len(noise_only.selected)==1

    moved=noisy.copy()
    moved[30:50,30:50]=220
    with_motion=AdaptiveFrameSelector().select(
        [frame(0,base),frame(200,moved)],
        SelectionConfig(sensitivity="auto",max_fps=10),
    )
    assert len(with_motion.selected)==2
    assert with_motion.candidates[1].pixel_threshold > 15
