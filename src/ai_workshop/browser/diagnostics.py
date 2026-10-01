from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from ai_workshop.browser.artifacts import ArtifactStore
from ai_workshop.browser.composite import CompositeRenderer
from ai_workshop.browser.frames import AdaptiveFrameSelector, FrameSample, SelectionConfig
from ai_workshop.browser.metadata import build_metadata
from ai_workshop.browser.models import ArtifactRef, CoordinateRegion
from ai_workshop.browser.recording import RecordingArtifact, decode_video


VariantRequest = Literal["neutral", "time-gradient", "both"]


@dataclass(slots=True)
class DiagnosticOptions:
    variants: VariantRequest = "neutral"
    legend: bool = False
    sensitivity: Literal["auto", "low", "medium", "high"] = "auto"
    max_fps: float = 10.0
    keep_frames: bool = False


@dataclass(slots=True)
class DiagnosticResult:
    session_id: str
    artifacts: list[ArtifactRef]


class DiagnosticService:
    def __init__(self, artifact_root: Path, *, decoder: Callable[..., list[FrameSample]] = decode_video, renderer: CompositeRenderer | None = None):
        self.store = ArtifactStore(artifact_root)
        self.decoder = decoder
        self.renderer = renderer or CompositeRenderer()

    def build(self, recording: RecordingArtifact, options: DiagnosticOptions | None = None) -> DiagnosticResult:
        options = options or DiagnosticOptions()
        session_id = recording.session_id
        video_path = self.store.root / recording.video.path
        artifacts = [recording.video]
        try:
            frames = self.decoder(video_path, frames_dir=None)
            frames = self._crop_frames(frames, recording)
            selection = AdaptiveFrameSelector().select(
                frames, SelectionConfig(sensitivity=options.sensitivity, max_fps=options.max_fps)
            )
            if options.keep_frames:
                from PIL import Image
                frames_dir = self.store.session_dir(session_id) / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                for index, sample in enumerate(selection.selected):
                    Image.fromarray(sample.image).save(frames_dir / f"{index:06d}.png", format="PNG")
            variants = ["neutral", "time-gradient"] if options.variants == "both" else [options.variants]
            for variant in variants:
                image = self.renderer.render(selection, variant=variant, legend=options.legend)
                name = f"composite-{variant}.png"
                path = self.store.path(session_id, name)
                image.save(path, format="PNG")
                artifacts.append(ArtifactRef(
                    id=session_id, media_type="image/png", path=f"{session_id}/{name}",
                    width=image.width, height=image.height
                ))
            duration_ms = frames[-1].timestamp_ms - frames[0].timestamp_ms if len(frames) > 1 else 0
            metadata = build_metadata(
                source_url=recording.source_url, viewport=recording.viewport, region=recording.region,
                duration_ms=duration_ms, selection=selection, variant=options.variants, legend=options.legend,
            )
            artifacts.append(self.store.write_json(session_id, "metadata.json", metadata))
            return DiagnosticResult(session_id=session_id, artifacts=artifacts)
        finally:
            if not options.keep_frames:
                self.store.cleanup_frames(session_id)

    @staticmethod
    def _crop_frames(frames: list[FrameSample], recording: RecordingArtifact) -> list[FrameSample]:
        clip = recording.resolved_clip
        if clip is None and isinstance(recording.region, CoordinateRegion):
            clip = {"x": recording.region.x, "y": recording.region.y,
                    "width": recording.region.width, "height": recording.region.height}
        if clip is None:
            return frames
        x, y = int(clip["x"]), int(clip["y"])
        width, height = int(clip["width"]), int(clip["height"])
        cropped: list[FrameSample] = []
        for sample in frames:
            image = sample.image[y:y + height, x:x + width]
            if image.size == 0:
                raise ValueError("capture region is outside decoded video frame")
            cropped.append(FrameSample(timestamp_ms=sample.timestamp_ms, image=image.copy()))
        return cropped
