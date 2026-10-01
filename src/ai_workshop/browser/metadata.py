from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ai_workshop.browser.frames import ChangeBox, FrameSelectionConfig, SelectionResult
from ai_workshop.browser.regions import ResolvedRegion


class DiagnosticFrameMetadata(BaseModel):
    timestamp_ms: float
    change_score: float
    boxes: list[ChangeBox]
    selected: bool


class DiagnosticMetadata(BaseModel):
    source_url: str
    viewport: dict[str, int]
    region: ResolvedRegion
    duration_ms: float
    frames: list[DiagnosticFrameMetadata]
    variant: Literal["neutral", "time-gradient"]
    threshold: FrameSelectionConfig
    legend: bool


def build_metadata(
    *,
    source_url: str,
    viewport: dict[str, int],
    region: ResolvedRegion,
    duration_ms: float,
    selection: SelectionResult,
    variant: Literal["neutral", "time-gradient"],
    config: FrameSelectionConfig,
    legend: bool,
) -> DiagnosticMetadata:
    return DiagnosticMetadata(
        source_url=source_url,
        viewport=viewport,
        region=region,
        duration_ms=duration_ms,
        frames=[DiagnosticFrameMetadata(**decision.model_dump()) for decision in selection.decisions],
        variant=variant,
        threshold=config,
        legend=legend,
    )
