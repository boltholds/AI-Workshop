from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image

from ai_workshop.browser.frames import SelectionResult


CompositeVariant = Literal["neutral", "time-gradient"]


class CompositeRenderer:
    def render(
        self,
        selection: SelectionResult,
        *,
        variant: CompositeVariant,
        legend: bool = False,
    ) -> Image.Image:
        frames = selection.selected
        if not frames:
            raise ValueError("cannot render a composite without selected frames")
        arrays = [np.asarray(frame.image, dtype=np.uint8) for frame in frames]
        shape = arrays[0].shape
        if any(array.shape != shape for array in arrays):
            raise ValueError("all selected frames must have the same dimensions")

        background = arrays[-1]
        output = background.astype(np.float32)
        count = len(arrays)

        for index, array in enumerate(arrays):
            delta = np.max(np.abs(array.astype(np.int16) - background.astype(np.int16)), axis=2)
            mask = delta >= 8
            if not np.any(mask):
                continue
            t = 1.0 if count == 1 else index / (count - 1)
            if variant == "neutral":
                source = array.astype(np.float32)
                alpha = 0.35 + 0.65 * t
            elif variant == "time-gradient":
                color = np.array([255 * t, 64, 255 * (1.0 - t)], dtype=np.float32)
                luminance = np.mean(array.astype(np.float32), axis=2, keepdims=True) / 255.0
                source = color.reshape(1, 1, 3) * (0.45 + 0.55 * luminance)
                alpha = 0.55 + 0.45 * t
            else:
                raise ValueError(f"unknown composite variant: {variant}")
            output[mask] = output[mask] * (1.0 - alpha) + source[mask] * alpha

        rendered = np.clip(output, 0, 255).astype(np.uint8)
        if legend and variant == "time-gradient":
            self._draw_time_legend(rendered)
        return Image.fromarray(rendered, mode="RGB")

    @staticmethod
    def _draw_time_legend(image: np.ndarray) -> None:
        height, width = image.shape[:2]
        if width < 12 or height < 4:
            return
        x0, x1 = 4, width - 4
        y0, y1 = max(0, height - 6), max(1, height - 2)
        span = max(1, x1 - x0)
        for x in range(x0, x1):
            t = (x - x0) / max(1, span - 1)
            image[y0:y1, x] = np.array([255 * t, 64, 255 * (1.0 - t)], dtype=np.uint8)
