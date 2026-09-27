"""Unit tests for FrameCompressor (app/infrastructure/vision/video/compressor.py).

Uses real PIL images generated in tmp_path to exercise the actual JPEG
compression path (no external deps).
"""

import pytest
from PIL import Image

from app.infrastructure.vision.video.compressor import (
    CompressionConfig,
    CompressionStrategy,
    CoordinateNormalizer,
    FrameCompressor,
)


@pytest.fixture
def sample_image(tmp_path):
    """Create a real RGB image file and return its path."""
    p = tmp_path / "frame.png"
    img = Image.new("RGB", (1920, 1080), color=(120, 80, 200))
    img.save(p, "PNG")
    return str(p)


class TestFrameCompressor:
    def test_compress_returns_frame(self, sample_image):
        c = FrameCompressor()
        frame = c.compress(sample_image)
        assert frame.data
        assert frame.width == 768  # max_width for default preset
        assert frame.original_size == (1920, 1080)
        assert frame.height == int(768 * 1080 / 1920)

    def test_compress_missing_file_raises(self, tmp_path):
        c = FrameCompressor()
        with pytest.raises(FileNotFoundError):
            c.compress(str(tmp_path / "nope.png"))

    def test_compress_with_explicit_config(self, sample_image):
        c = FrameCompressor()
        cfg = CompressionConfig(max_width=512, quality=60, detail_level="low")
        frame = c.compress(sample_image, config=cfg)
        assert frame.width == 512
        assert frame.detail_level == "low"


class TestCoordinateNormalizer:
    def test_normalize_scales_to_unit(self):
        n = CoordinateNormalizer(1920, 1080)
        x, y = n.normalize(960, 540)
        assert x == pytest.approx(0.5)
        assert y == pytest.approx(0.5)

    def test_normalize_none_returns_none(self):
        n = CoordinateNormalizer(1920, 1080)
        assert n.normalize(None, None) is None


class TestCompressionStrategy:
    def test_enum_values(self):
        assert CompressionStrategy.GENERAL.value == "general"
        assert CompressionStrategy.TEXT_DENSE.value == "text_dense"
        assert CompressionStrategy.ICON_UI.value == "icon_ui"
