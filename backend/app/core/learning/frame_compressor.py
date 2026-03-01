"""
关键帧压缩与坐标归一化模块

功能:
- 图像尺寸压缩（控制 token 成本）
- 格式转换（PNG -> JPEG 节省体积）
- 坐标归一化（原始分辨率 -> 0.0-1.0）
- 质量自适应（文字密集区域保持高分辨率）
"""

import io
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class CompressionStrategy(Enum):
    """压缩策略"""
    GENERAL = "general"           # 一般 UI：768px, low detail
    TEXT_DENSE = "text_dense"     # 文字密集：1024px, high detail
    ICON_UI = "icon_ui"           # 图标导航：512px, low detail


@dataclass
class CompressionConfig:
    """压缩配置"""
    max_width: int
    quality: int                  # JPEG 质量 0-100
    detail_level: str             # "low" or "high" (for LLM)
    format: str = "JPEG"


# 预设配置
PRESETS = {
    CompressionStrategy.GENERAL: CompressionConfig(
        max_width=768,
        quality=85,
        detail_level="low"
    ),
    CompressionStrategy.TEXT_DENSE: CompressionConfig(
        max_width=1024,
        quality=90,
        detail_level="high"
    ),
    CompressionStrategy.ICON_UI: CompressionConfig(
        max_width=512,
        quality=80,
        detail_level="low"
    )
}


@dataclass
class CompressedFrame:
    """压缩后的帧数据"""
    data: bytes                   # JPEG 数据
    width: int
    height: int
    original_size: Tuple[int, int]  # 原始分辨率
    compression_ratio: float      # 压缩比
    detail_level: str             # "low" or "high"


@dataclass
class NormalizedEvent:
    """归一化后的事件"""
    action: str
    norm_x: Optional[float]       # 0.0-1.0
    norm_y: Optional[float]
    target_text: Optional[str]
    timestamp: float
    description: str              # 人类可读描述


class CoordinateNormalizer:
    """
    坐标归一化器

    将原始屏幕坐标（像素）转换为归一化坐标（0.0-1.0），
    使 LLM 能够理解与分辨率无关的位置描述。
    """

    def __init__(self, original_width: int, original_height: int):
        self.original = (original_width, original_height)

    def normalize(self, x: Optional[int], y: Optional[int]) -> Optional[Tuple[float, float]]:
        """
        原始像素坐标 -> 归一化坐标
        """
        if x is None or y is None:
            return None

        norm_x = round(x / self.original[0], 4)
        norm_y = round(y / self.original[1], 4)
        return (norm_x, norm_y)

    def denormalize_to_compressed(
        self,
        norm_x: float,
        norm_y: float,
        compressed_width: int,
        compressed_height: int
    ) -> Tuple[int, int]:
        """
        归一化坐标 -> 压缩图像上的绝对坐标（用于可视化）
        """
        return (
            int(norm_x * compressed_width),
            int(norm_y * compressed_height)
        )

    @staticmethod
    def describe_position(norm_x: float, norm_y: float) -> str:
        """
        将归一化坐标转换为人类可读的方位描述
        """
        # 水平位置
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

        # 垂直位置
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

        # 特殊边缘位置
        if norm_x < 0.1 or norm_x > 0.9:
            if norm_y < 0.1:
                return f"top-{h} corner"
            elif norm_y > 0.9:
                return f"bottom-{h} corner"
            return f"{v} edge ({h})"

        return f"{v}-{h}"


class FrameCompressor:
    """
    关键帧智能压缩器

    根据内容类型自动选择压缩策略，平衡视觉质量与 token 成本。
    """

    # 目标文件大小（压缩后）
    TARGET_SIZE_KB = 100  # ~100KB per frame

    def __init__(self):
        self.default_strategy = CompressionStrategy.GENERAL

    def compress(
        self,
        image_path: str,
        strategy: Optional[CompressionStrategy] = None,
        config: Optional[CompressionConfig] = None
    ) -> CompressedFrame:
        """
        压缩单帧图像

        Args:
            image_path: 原始图像路径
            strategy: 压缩策略（自动检测或指定）
            config: 自定义配置（覆盖策略）

        Returns:
            CompressedFrame: 压缩后的帧数据
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # 加载原始图像
        with Image.open(image_path) as img:
            original_size = img.size

            # 自动检测策略（如果未指定）
            if strategy is None and config is None:
                strategy = self._detect_strategy(img)

            cfg = config or PRESETS[strategy]

            # 执行压缩
            compressed_data = self._compress_image(img, cfg)

            # 计算压缩比
            original_bytes = path.stat().st_size
            compression_ratio = len(compressed_data) / original_bytes

            logger.debug(
                f"Compressed {original_size} -> {cfg.max_width}px "
                f"({compression_ratio:.1%} of original)"
            )

            return CompressedFrame(
                data=compressed_data,
                width=cfg.max_width,
                height=int(cfg.max_width * original_size[1] / original_size[0]),
                original_size=original_size,
                compression_ratio=compression_ratio,
                detail_level=cfg.detail_level
            )

    def compress_with_target_size(
        self,
        image_path: str,
        target_kb: int = 100
    ) -> CompressedFrame:
        """
        自适应压缩到目标文件大小

        通过二分查找找到合适的质量参数
        """
        # 先用默认策略
        result = self.compress(image_path)
        current_kb = len(result.data) / 1024

        if current_kb <= target_kb:
            return result

        # 需要进一步压缩，降低质量
        low_quality, high_quality = 30, 85
        best_result = result

        while low_quality <= high_quality:
            mid_quality = (low_quality + high_quality) // 2

            config = CompressionConfig(
                max_width=768,
                quality=mid_quality,
                detail_level="low"
            )

            with Image.open(image_path) as img:
                data = self._compress_image(img, config)
                current_kb = len(data) / 1024

                if abs(current_kb - target_kb) < 10:
                    # 接近目标
                    return self._create_frame_result(image_path, data, config)

                if current_kb > target_kb:
                    high_quality = mid_quality - 1
                else:
                    best_result = self._create_frame_result(image_path, data, config)
                    low_quality = mid_quality + 1

        return best_result

    def _compress_image(self, img: Image.Image, config: CompressionConfig) -> bytes:
        """
        执行图像压缩
        """
        # 转换为 RGB（去除 alpha）
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # 等比缩放
        original_width, original_height = img.size
        if original_width > config.max_width:
            ratio = config.max_width / original_width
            new_size = (config.max_width, int(original_height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # 保存为 JPEG
        buffer = io.BytesIO()
        img.save(
            buffer,
            format=config.format,
            quality=config.quality,
            optimize=True
        )

        return buffer.getvalue()

    def _detect_strategy(self, img: Image.Image) -> CompressionStrategy:
        """
        自动检测图像内容类型，选择压缩策略

        启发式规则：
        - 如果图像很高或很宽 -> 可能是代码编辑器（TEXT_DENSE）
        - 如果图像接近正方形且较小 -> 可能是移动端（ICON_UI）
        - 默认 -> GENERAL
        """
        width, height = img.size
        aspect_ratio = width / height

        # 超宽屏可能是代码编辑器
        if aspect_ratio > 2.0:
            return CompressionStrategy.TEXT_DENSE

        # 接近正方形可能是移动端截图
        if 0.8 < aspect_ratio < 1.2 and width < 1000:
            return CompressionStrategy.ICON_UI

        return CompressionStrategy.GENERAL

    def _create_frame_result(
        self,
        image_path: str,
        data: bytes,
        config: CompressionConfig
    ) -> CompressedFrame:
        """创建帧结果对象"""
        with Image.open(image_path) as img:
            original_size = img.size

        return CompressedFrame(
            data=data,
            width=config.max_width,
            height=int(config.max_width * original_size[1] / original_size[0]),
            original_size=original_size,
            compression_ratio=len(data) / Path(image_path).stat().st_size,
            detail_level=config.detail_level
        )


class KeyframeSelector:
    """
    智能关键帧选择器

    从视频和事件中选择最具信息量的帧，同时控制总数和避免冗余。
    """

    # 配置
    PRE_ACTION_OFFSET_MS = -200    # 操作前 200ms
    POST_ACTION_OFFSET_MS = 500    # 操作后 500ms
    TRANSITION_DELAY_MS = 800      # 页面切换等待
    MIN_INTERVAL_MS = 300          # 最小帧间隔
    MAX_KEYFRAMES = 15             # 最大关键帧数

    def __init__(self):
        pass

    def select_keyframes(
        self,
        events: list,
        video_duration: float,
        video_resolution: Tuple[int, int]
    ) -> List["KeyframeCandidate"]:
        """
        基于事件选择关键帧

        Args:
            events: TraceEvent 列表
            video_duration: 视频总时长（秒）
            video_resolution: 视频分辨率 (width, height)

        Returns:
            KeyframeCandidate 列表（按时间排序）
        """
        candidates = []
        last_timestamp = -1

        for i, event in enumerate(events):
            event_ts = getattr(event, 'timestamp', 0)
            if not event_ts:
                continue

            event_ts = float(event_ts)

            # 跳过鼠标移动事件（太多了）
            action_type = getattr(event, 'action_type', '')
            if action_type in ('mouse_move', 'cursor_move'):
                continue

            # 操作前帧
            pre_ts = max(0, event_ts + self.PRE_ACTION_OFFSET_MS / 1000)
            if pre_ts > last_timestamp + self.MIN_INTERVAL_MS / 1000:
                candidates.append(KeyframeCandidate(
                    timestamp=pre_ts,
                    context="pre_action",
                    description=f"Before {action_type}: UI state before action",
                    related_event=event,
                    priority=2
                ))

            # 操作后帧（高优先级）
            post_ts = min(video_duration, event_ts + self.POST_ACTION_OFFSET_MS / 1000)
            candidates.append(KeyframeCandidate(
                timestamp=post_ts,
                context="post_action",
                description=f"After {action_type}: Result state",
                related_event=event,
                priority=3
            ))

            last_timestamp = post_ts

        # 按优先级和时间排序
        candidates.sort(key=lambda k: (-k.priority, k.timestamp))

        # 时间窗口去重（保留高优先级的）
        deduped = self._temporal_deduplication(candidates)

        # 限制总数
        if len(deduped) > self.MAX_KEYFRAMES:
            deduped = self._prioritize_frames(deduped)

        # 最终按时间排序
        return sorted(deduped, key=lambda k: k.timestamp)

    def _temporal_deduplication(
        self,
        candidates: List["KeyframeCandidate"]
    ) -> List["KeyframeCandidate"]:
        """
        时间窗口去重：过于接近的帧只保留高优先级的
        """
        if not candidates:
            return []

        result = []
        for candidate in candidates:
            # 检查是否与已保留的帧太接近
            too_close = False
            for kept in result:
                if abs(candidate.timestamp - kept.timestamp) < self.MIN_INTERVAL_MS / 1000:
                    too_close = True
                    break

            if not too_close:
                result.append(candidate)

        return result

    def _prioritize_frames(
        self,
        candidates: List["KeyframeCandidate"]
    ) -> List["KeyframeCandidate"]:
        """
        当帧数超过限制时，按优先级筛选
        """
        # 按优先级分组
        by_priority = {}
        for c in candidates:
            by_priority.setdefault(c.priority, []).append(c)

        # 优先选择高优先级的
        result = []
        for priority in sorted(by_priority.keys(), reverse=True):
            frames = by_priority[priority]
            # 同优先级内按时间间隔采样
            for i, frame in enumerate(frames):
                if len(result) < self.MAX_KEYFRAMES:
                    result.append(frame)

        return result


@dataclass
class KeyframeCandidate:
    """关键帧候选"""
    timestamp: float
    context: str           # "pre_action", "post_action", "transition"
    description: str
    related_event: any
    priority: int          # 3=high, 2=medium, 1=low

    def __repr__(self):
        return f"Keyframe({self.timestamp:.2f}s, {self.context}, P{self.priority})"
