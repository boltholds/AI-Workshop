from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np


Sensitivity = Literal["auto", "low", "medium", "high"]


@dataclass(slots=True)
class FrameSample:
    timestamp_ms: int
    image: np.ndarray


@dataclass(slots=True)
class SelectionConfig:
    sensitivity: Sensitivity = "auto"
    max_fps: float = 10.0

    def __post_init__(self) -> None:
        if self.max_fps <= 0:
            raise ValueError("max_fps must be positive")


@dataclass(slots=True)
class FrameCandidate:
    frame: FrameSample
    change_score: float
    changed_boxes: list[dict[str, int]] = field(default_factory=list)
    selected: bool = False

    @property
    def timestamp_ms(self) -> int:
        return self.frame.timestamp_ms


@dataclass(slots=True)
class SelectionResult:
    candidates: list[FrameCandidate]
    selected: list[FrameSample]
    config: SelectionConfig


class AdaptiveFrameSelector:
    _PIXEL_THRESHOLDS: dict[Sensitivity, int] = {
        "auto": 12,
        "low": 32,
        "medium": 16,
        "high": 8,
    }
    _MIN_CHANGED_FRACTION: dict[Sensitivity, float] = {
        "auto": 0.002,
        "low": 0.005,
        "medium": 0.002,
        "high": 0.0005,
    }

    def select(self, frames: list[FrameSample], config: SelectionConfig | None = None) -> SelectionResult:
        config = config or SelectionConfig()
        if not frames:
            return SelectionResult(candidates=[], selected=[], config=config)

        min_interval_ms = 1000.0 / config.max_fps
        candidates = [FrameCandidate(frame=frames[0], change_score=0.0, selected=True)]
        selected = [frames[0]]
        last_selected_ts = frames[0].timestamp_ms
        previous = frames[0].image

        for sample in frames[1:]:
            score, boxes = self._difference(previous, sample.image, config.sensitivity)
            significant = score >= self._MIN_CHANGED_FRACTION[config.sensitivity]
            rate_ok = sample.timestamp_ms - last_selected_ts >= min_interval_ms
            is_selected = significant and rate_ok
            candidates.append(
                FrameCandidate(
                    frame=sample,
                    change_score=score,
                    changed_boxes=boxes,
                    selected=is_selected,
                )
            )
            if is_selected:
                selected.append(sample)
                last_selected_ts = sample.timestamp_ms
            previous = sample.image

        return SelectionResult(candidates=candidates, selected=selected, config=config)

    def _difference(
        self,
        before: np.ndarray,
        after: np.ndarray,
        sensitivity: Sensitivity,
    ) -> tuple[float, list[dict[str, int]]]:
        if before.shape != after.shape:
            raise ValueError("all frames must have the same dimensions")
        delta = cv2.absdiff(before, after)
        if delta.ndim == 3:
            magnitude = np.max(delta, axis=2)
        else:
            magnitude = delta
        mask = (magnitude >= self._PIXEL_THRESHOLDS[sensitivity]).astype(np.uint8) * 255
        changed = int(np.count_nonzero(mask))
        score = changed / float(mask.size)
        if changed == 0:
            return 0.0, []
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            boxes.append({"x": int(x), "y": int(y), "width": int(width), "height": int(height)})
        boxes.sort(key=lambda b: (b["y"], b["x"]))
        return score, boxes
