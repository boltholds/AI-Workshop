from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

from ai_workshop.browser.frames import SelectionResult

CompositeVariant = Literal["neutral", "time-gradient"]


def _rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.repeat(image[:, :, None], 3, axis=2)
    if image.shape[2] == 4:
        return image[:, :, [2, 1, 0, 3]][:, :, :3]
    return image[:, :, ::-1]


def _motion_masks(images: list[np.ndarray], pixel_delta: int = 10) -> tuple[np.ndarray, list[np.ndarray]]:
    stack = np.stack(images).astype(np.float32)
    background = np.median(stack, axis=0)
    masks = [np.max(np.abs(image.astype(np.float32) - background), axis=2) >= pixel_delta for image in images]
    return background, masks


def _time_color(position: float) -> np.ndarray:
    # RGB: cool early frames -> warm late frames.
    position = float(np.clip(position, 0.0, 1.0))
    early = np.array([40.0, 130.0, 255.0])
    late = np.array([255.0, 80.0, 40.0])
    return early * (1.0 - position) + late * position


class CompositeRenderer:
    @classmethod
    def render(cls, selection: SelectionResult, *, variant: CompositeVariant, legend: bool = False) -> Image.Image:
        frames = list(selection.selected_frames)
        if not frames:
            raise ValueError("cannot render a composite without selected frames")
        rgb_images = [_rgb(frame.image) for frame in frames]
        latest = rgb_images[-1].astype(np.float32)
        _, masks = _motion_masks(rgb_images)

        if variant == "neutral":
            output = latest.copy()
            older_count = max(1, len(rgb_images) - 1)
            for index, (image, mask) in enumerate(zip(rgb_images[:-1], masks[:-1])):
                # Oldest trail is faintest; recent history is easier to follow.
                alpha = 0.25 + 0.35 * (index / older_count)
                output[mask] = output[mask] * (1.0 - alpha) + image.astype(np.float32)[mask] * alpha
        elif variant == "time-gradient":
            output = latest.copy()
            count = max(1, len(rgb_images) - 1)
            for index, mask in enumerate(masks):
                color = _time_color(index / count)
                output[mask] = output[mask] * 0.25 + color * 0.75
        else:
            raise ValueError(f"unsupported composite variant: {variant}")

        image = Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")
        if legend and variant == "time-gradient":
            cls._draw_legend(image)
        return image

    @staticmethod
    def _draw_legend(image: Image.Image) -> None:
        draw = ImageDraw.Draw(image)
        width = min(120, max(24, image.width // 3))
        height = min(10, max(4, image.height // 20))
        x0 = max(2, image.width - width - 4)
        y0 = max(2, image.height - height - 4)
        for offset in range(width):
            color = tuple(int(v) for v in _time_color(offset / max(1, width - 1)))
            draw.line((x0 + offset, y0, x0 + offset, y0 + height), fill=color)
        draw.rectangle((x0 - 1, y0 - 1, x0 + width, y0 + height + 1), outline=(255, 255, 255))
