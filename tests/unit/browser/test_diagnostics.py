from pathlib import Path
import numpy as np
import pytest

from ai_workshop.browser.diagnostics import DiagnosticOptions, DiagnosticService
from ai_workshop.browser.frames import FrameSample
from ai_workshop.browser.models import ArtifactRef, CoordinateRegion
from ai_workshop.browser.recording import RecordingArtifact


def recording(root: Path):
    path=root/"s1"/"recording.webm"; path.parent.mkdir(parents=True); path.write_bytes(b"video")
    return RecordingArtifact(session_id="s1",video=ArtifactRef(id="s1",media_type="video/webm",path="s1/recording.webm"),
        source_url="https://example.test",viewport={"width":80,"height":60},region=CoordinateRegion(x=10,y=10,width=40,height=30))


def frames():
    result=[]
    for i,x in enumerate((5,15,25)):
        image=np.zeros((60,80,3),dtype=np.uint8); image[20:30,x:x+8]=(10,100,220); result.append(FrameSample(i*200,image))
    return result


def test_dual_diagnostics_writes_png_json_and_removes_frames(tmp_path: Path):
    result=DiagnosticService(tmp_path,decoder=lambda path,frames_dir=None: frames()).build(recording(tmp_path),DiagnosticOptions(variants="both"))
    names={a.path.split("/")[-1] for a in result.artifacts}
    assert {"recording.webm","composite-neutral.png","composite-time-gradient.png","metadata.json"} <= names
    assert not (tmp_path/"s1"/"frames").exists()


def test_keep_frames_writes_only_adaptively_selected_frames(tmp_path: Path):
    seen={}
    def decoder(path, frames_dir=None):
        seen["frames_dir"]=frames_dir
        values=frames()
        values.insert(1, FrameSample(50, values[0].image.copy()))
        return values
    artifact=recording(tmp_path)
    DiagnosticService(tmp_path, decoder=decoder).build(
        artifact,
        DiagnosticOptions(variants="neutral", keep_frames=True, max_fps=10),
    )
    assert seen["frames_dir"] is None
    saved=sorted((tmp_path/"s1"/"frames").glob("*.png"))
    assert len(saved) == 3


def test_recording_survives_composite_failure(tmp_path: Path):
    class Broken:
        def render(self,*args,**kwargs): raise RuntimeError("renderer exploded")
    artifact=recording(tmp_path)
    with pytest.raises(RuntimeError):
        DiagnosticService(tmp_path,decoder=lambda path,frames_dir=None: frames(),renderer=Broken()).build(artifact)
    assert (tmp_path/"s1"/"recording.webm").read_bytes() == b"video"
