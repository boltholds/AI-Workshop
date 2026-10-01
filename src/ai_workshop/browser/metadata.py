from __future__ import annotations

from typing import Any

from ai_workshop.browser.frames import SelectionResult
from ai_workshop.browser.models import CaptureRegion


def build_metadata(
    *,
    source_url: str,
    viewport: dict[str, int] | None,
    region: CaptureRegion,
    duration_ms: int,
    selection: SelectionResult,
    variant: str,
    legend: bool,
) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "viewport": viewport,
        "region": region.model_dump(),
        "duration_ms": duration_ms,
        "threshold": {"sensitivity": selection.config.sensitivity},
        "max_fps": selection.config.max_fps,
        "variant": variant,
        "legend": legend,
        "frames": [
            {
                "timestamp_ms": candidate.timestamp_ms,
                "change_score": candidate.change_score,
                "changed_boxes": candidate.changed_boxes,
                "selected": candidate.selected,
                "pixel_threshold": candidate.pixel_threshold,
            }
            for candidate in selection.candidates
        ],
    }
