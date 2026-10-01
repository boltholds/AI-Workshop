from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class VideoFrame:
    timestamp_ms: float
    image: np.ndarray


class ChangeBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class FrameDecision(BaseModel):
    timestamp_ms: float
    change_score: float
    boxes: list[ChangeBox]
    selected: bool


class FrameSelectionConfig(BaseModel):
    sensitivity: Literal["auto", "low", "medium", "high"] = "auto"
    max_fps: float = Field(default=10.0, gt=0, le=60)
    pixel_delta: int = Field(default=10, ge=1, le=255)


@dataclass(frozen=True)
class SelectionResult:
    selected_frames: tuple[VideoFrame, ...]
    decisions: tuple[FrameDecision, ...]


class AdaptiveFrameSelector:
    @staticmethod
    def _threshold(config: FrameSelectionConfig, previous_scores: list[float]) -> float:
        fixed = {"low": 0.01, "medium": 0.002, "high": 0.0005}
        if config.sensitivity != "auto":
            return fixed[config.sensitivity]
        nonzero = [score for score in previous_scores if score > 0]
        if not nonzero:
            return 0.002
        return float(np.clip(np.median(nonzero) * 0.25, 0.001, 0.02))

    @staticmethod
    def _compare(previous: np.ndarray, current: np.ndarray, pixel_delta: int) -> tuple[float, list[ChangeBox]]:
        if previous.shape != current.shape:
            raise ValueError("all video frames must have identical dimensions")
        delta = cv2.absdiff(previous, current)
        mask = np.max(delta, axis=2) >= pixel_delta if delta.ndim == 3 else delta >= pixel_delta
        changed = int(np.count_nonzero(mask))
        score = changed / float(mask.size)
        if changed == 0:
            return 0.0, []
        ys, xs = np.nonzero(mask)
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        return score, [ChangeBox(x=x0, y=y0, width=x1 - x0 + 1, height=y1 - y0 + 1)]

    @classmethod
    def select(cls, frames: list[VideoFrame], config: FrameSelectionConfig) -> SelectionResult:
        if not frames:
            return SelectionResult(selected_frames=(), decisions=())
        min_interval_ms = 1000.0 / config.max_fps
        selected = [frames[0]]
        decisions = [FrameDecision(timestamp_ms=frames[0].timestamp_ms, change_score=1.0, boxes=[], selected=True)]
        previous_scores: list[float] = []
        last_selected = frames[0]

        for current in frames[1:]:
            score, boxes = cls._compare(last_selected.image, current.image, config.pixel_delta)
            threshold = cls._threshold(config, previous_scores)
            previous_scores.append(score)
            far_enough = current.timestamp_ms - last_selected.timestamp_ms >= min_interval_ms - 1e-9
            keep = score >= threshold and far_enough
            decisions.append(FrameDecision(timestamp_ms=current.timestamp_ms, change_score=score, boxes=boxes, selected=keep))
            if keep:
                selected.append(current)
                last_selected = current

        return SelectionResult(selected_frames=tuple(selected), decisions=tuple(decisions))


def decode_video(path: Path) -> list[VideoFrame]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"unable to open video: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames: list[VideoFrame] = []
    index = 0
    try:
        while True:
            ok, image = capture.read()
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp_ms <= 0 and index > 0:
                timestamp_ms = index * 1000.0 / fps
            frames.append(VideoFrame(timestamp_ms=float(timestamp_ms), image=image))
            index += 1
    finally:
        capture.release()
    return frames
