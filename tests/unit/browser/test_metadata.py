import numpy as np

from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSample, SelectionConfig
from ai_workshop.browser.metadata import build_metadata
from ai_workshop.browser.models import CoordinateRegion


def test_metadata_contains_capture_and_candidate_details():
    a=np.zeros((10,10,3),dtype=np.uint8); b=a.copy(); b[1:4,1:4]=255
    selection=AdaptiveFrameSelector().select([FrameSample(0,a),FrameSample(250,b)],SelectionConfig(sensitivity="high"))
    metadata=build_metadata(source_url="https://example.test/editor",viewport={"width":800,"height":600},
        region=CoordinateRegion(x=1,y=2,width=300,height=200),duration_ms=250,selection=selection,variant="neutral",legend=False)
    assert metadata["region"]["kind"] == "coordinates"
    assert metadata["threshold"]["sensitivity"] == "high"
    assert metadata["frames"][1]["selected"] is True
