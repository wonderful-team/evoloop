"""
Frame compression and keyframe selection utilities.

Provides:
- FrameCompressor: scale + quality compression for LLM token cost control
- KeyframeSelector: intelligent keyframe selection from event sequences
- CoordinateNormalizer: pixel → normalized coordinate conversion

Migrated from app.core.learning.frame_compressor.
"""

import io
import logging
from enum import Enum
from pathlib import Path

from PIL import Image

from app.infrastructure.video.schemas import (
    CompressedFrame,
    CompressionConfig,
    KeyframeCandidate,
)

logger = logging.getLogger(__name__)


class CompressionStrategy(Enum):
    GENERAL = "general"
    TEXT_DENSE = "text_dense"
    ICON_UI = "icon_ui"


PRESETS = {
    CompressionStrategy.GENERAL: CompressionConfig(
        max_width=768, quality=85, detail_level="low"
    ),
    CompressionStrategy.TEXT_DENSE: CompressionConfig(
        max_width=1024, quality=90, detail_level="high"
    ),
    CompressionStrategy.ICON_UI: CompressionConfig(
        max_width=512, quality=80, detail_level="low"
    ),
}


class CoordinateNormalizer:
    def __init__(self, original_width: int, original_height: int):
        self.original = (original_width, original_height)

    def normalize(self, x: int | None, y: int | None) -> tuple[float, float] | None:
        if x is None or y is None:
            return None
        return (round(x / self.original[0], 4), round(y / self.original[1], 4))

    def denormalize_to_compressed(
        self,
        norm_x: float,
        norm_y: float,
        compressed_width: int,
        compressed_height: int,
    ) -> tuple[int, int]:
        return (int(norm_x * compressed_width), int(norm_y * compressed_height))

    @staticmethod
    def describe_position(norm_x: float, norm_y: float) -> str:
        if norm_x < 0.15:
            h = "far left"
        elif norm_x < 0.35:
            h = "left"
        elif norm_x < 0.65:
            h = "center"
        elif norm_x < 0.85:
            h = "right"
        else:
            h = "far right"
        if norm_y < 0.15:
            v = "top"
        elif norm_y < 0.35:
            v = "upper"
        elif norm_y < 0.65:
            v = "middle"
        elif norm_y < 0.85:
            v = "lower"
        else:
            v = "bottom"
        if norm_x < 0.1 or norm_x > 0.9:
            if norm_y < 0.1:
                return f"top-{h} corner"
            elif norm_y > 0.9:
                return f"bottom-{h} corner"
            return f"{v} edge ({h})"
        return f"{v}-{h}"


class FrameCompressor:
    TARGET_SIZE_KB = 100

    def __init__(self):
        self.default_strategy = CompressionStrategy.GENERAL

    def compress(
        self,
        image_path: str,
        strategy: CompressionStrategy | None = None,
        config: CompressionConfig | None = None,
    ) -> CompressedFrame:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        with Image.open(image_path) as img:
            original_size = img.size
            if strategy is None and config is None:
                strategy = self._detect_strategy(img)
            effective_strategy = strategy or self.default_strategy
            cfg = config or PRESETS[effective_strategy]
            compressed_data = self._compress_image(img, cfg)
            compression_ratio = len(compressed_data) / path.stat().st_size
            return CompressedFrame(
                data=compressed_data,
                width=cfg.max_width,
                height=int(cfg.max_width * original_size[1] / original_size[0]),
                original_size=original_size,
                compression_ratio=compression_ratio,
                detail_level=cfg.detail_level,
            )

    def compress_with_target_size(
        self, image_path: str, target_kb: int = 100
    ) -> CompressedFrame:
        result = self.compress(image_path)
        current_kb = len(result.data) / 1024
        if current_kb <= target_kb:
            return result
        low_quality, high_quality = 30, 85
        best_result = result
        while low_quality <= high_quality:
            mid_quality = (low_quality + high_quality) // 2
            config = CompressionConfig(
                max_width=768, quality=mid_quality, detail_level="low"
            )
            with Image.open(image_path) as img:
                data = self._compress_image(img, config)
                current_kb = len(data) / 1024
                if abs(current_kb - target_kb) < 10:
                    return self._create_frame_result(image_path, data, config)
                if current_kb > target_kb:
                    high_quality = mid_quality - 1
                else:
                    best_result = self._create_frame_result(image_path, data, config)
                    low_quality = mid_quality + 1
        return best_result

    def _compress_image(self, img: Image.Image, config: CompressionConfig) -> bytes:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        original_width, original_height = img.size
        if original_width > config.max_width:
            ratio = config.max_width / original_width
            img = img.resize(
                (config.max_width, int(original_height * ratio)),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        img.save(buffer, format=config.format, quality=config.quality, optimize=True)
        return buffer.getvalue()

    def _detect_strategy(self, img: Image.Image) -> CompressionStrategy:
        width, height = img.size
        aspect_ratio = width / height
        if aspect_ratio > 2.0:
            return CompressionStrategy.TEXT_DENSE
        if 0.8 < aspect_ratio < 1.2 and width < 1000:
            return CompressionStrategy.ICON_UI
        return CompressionStrategy.GENERAL

    def _create_frame_result(
        self, image_path: str, data: bytes, config: CompressionConfig
    ) -> CompressedFrame:
        with Image.open(image_path) as img:
            original_size = img.size
        return CompressedFrame(
            data=data,
            width=config.max_width,
            height=int(config.max_width * original_size[1] / original_size[0]),
            original_size=original_size,
            compression_ratio=len(data) / Path(image_path).stat().st_size,
            detail_level=config.detail_level,
        )


class KeyframeSelector:
    DEFAULT_MAX_KEYFRAMES = 15
    PRE_ACTION_OFFSET_MS = -200
    POST_ACTION_OFFSET_MS = 1500
    TRANSITION_DELAY_MS = 800
    MIN_INTERVAL_MS = 300

    def __init__(self, max_keyframes: int | None = None):
        self.max_keyframes = max_keyframes or self.DEFAULT_MAX_KEYFRAMES

    def select_keyframes(
        self, events: list, video_duration: float, max_frames: int | None = None
    ) -> list[KeyframeCandidate]:
        candidates = []
        last_timestamp = -1
        for i, event in enumerate(events):
            event_ts = getattr(event, "timestamp", 0)
            if not event_ts:
                continue
            event_ts = float(event_ts)
            if event_ts > video_duration:
                continue
            action_type = getattr(event, "action_type", "")
            if action_type in ("mouse_move", "cursor_move"):
                continue
            pre_ts = max(0, event_ts + self.PRE_ACTION_OFFSET_MS / 1000)
            if pre_ts > last_timestamp + self.MIN_INTERVAL_MS / 1000:
                candidates.append(
                    KeyframeCandidate(
                        timestamp=pre_ts,
                        context="pre_action",
                        description=f"Before {action_type}",
                        related_event=event,
                        priority=2,
                    )
                )
            post_ts = min(video_duration, event_ts + self.POST_ACTION_OFFSET_MS / 1000)
            candidates.append(
                KeyframeCandidate(
                    timestamp=post_ts,
                    context="post_action",
                    description=f"After {action_type}",
                    related_event=event,
                    priority=3,
                )
            )
            last_timestamp = post_ts
        candidates.sort(key=lambda k: (-k.priority, k.timestamp))
        deduped = self._temporal_deduplication(candidates)
        limit = max_frames or self.max_keyframes
        if len(deduped) > limit:
            deduped = self._prioritize_frames(deduped, limit=limit)
        return sorted(deduped, key=lambda k: k.timestamp)

    def _temporal_deduplication(
        self, candidates: list[KeyframeCandidate]
    ) -> list[KeyframeCandidate]:
        if not candidates:
            return []
        result = []
        for candidate in candidates:
            too_close = any(
                abs(candidate.timestamp - kept.timestamp) < self.MIN_INTERVAL_MS / 1000
                for kept in result
            )
            if not too_close:
                result.append(candidate)
        return result

    def _prioritize_frames(
        self, candidates: list[KeyframeCandidate], limit: int = 15
    ) -> list[KeyframeCandidate]:
        by_priority = {}
        for c in candidates:
            by_priority.setdefault(c.priority, []).append(c)
        result = []
        for priority in sorted(by_priority, reverse=True):
            for frame in by_priority[priority]:
                if len(result) < limit:
                    result.append(frame)
        return result
