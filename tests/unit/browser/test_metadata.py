from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSelectionConfig, VideoFrame
from ai_workshop.browser.metadata import build_metadata
from ai_workshop.browser.regions import ResolvedRegion
import numpy as np


def test_metadata_records_frames_boxes_threshold_and_legend() -> None:
    a = np.zeros((20, 20, 3), dtype=np.uint8)
    b = a.copy(); b[5:10, 5:10] = 255
    config = FrameSelectionConfig(sensitivity="high", max_fps=12)
    selection = AdaptiveFrameSelector.select([VideoFrame(0, a), VideoFrame(200, b)], config)
    region = ResolvedRegion(kind="selector", selector="#canvas", clip={"x": 1, "y": 2, "width": 20, "height": 20})
    metadata = build_metadata(
        source_url="https://workshop.test/editor",
        viewport={"width": 800, "height": 600},
        region=region,
        duration_ms=200,
        selection=selection,
        variant="time-gradient",
        config=config,
        legend=True,
    )
    data = metadata.model_dump(mode="json")
    assert data["source_url"] == "https://workshop.test/editor"
    assert data["viewport"] == {"width": 800, "height": 600}
    assert data["region"]["selector"] == "#canvas"
    assert data["duration_ms"] == 200
    assert data["variant"] == "time-gradient"
    assert data["threshold"]["sensitivity"] == "high"
    assert data["threshold"]["max_fps"] == 12
    assert data["legend"] is True
    assert len(data["frames"]) == 2
    assert data["frames"][1]["selected"] is True
    assert data["frames"][1]["boxes"]
