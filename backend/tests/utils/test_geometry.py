"""
Tests for app.utils.geometry module.
"""

import pytest

from app.utils.geometry import (
    Bounds,
    parse_bounds,
    format_bounds,
    normalize_coordinates,
    get_bounds_center,
    is_point_in_bounds,
    calculate_iou,
    describe_position,
    clamp_coordinates,
)


class TestBounds:
    """Test cases for Bounds dataclass."""

    def test_creation(self):
        """Test creating Bounds instance."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=100)
        assert bounds.x1 == 0
        assert bounds.y1 == 0
        assert bounds.x2 == 100
        assert bounds.y2 == 100
    
    def test_width_property(self):
        """Test width property."""
        bounds = Bounds(x1=10, y1=20, x2=50, y2=80)
        assert bounds.width == 40
    
    def test_height_property(self):
        """Test height property."""
        bounds = Bounds(x1=10, y1=20, x2=50, y2=80)
        assert bounds.height == 60
    
    def test_area_property(self):
        """Test area property."""
        bounds = Bounds(x1=0, y1=0, x2=10, y2=20)
        assert bounds.area == 200


class TestParseBounds:
    """Test cases for parse_bounds function."""

    def test_valid_bounds_string(self):
        """Test parsing valid bounds string."""
        result = parse_bounds("[0,0][100,100]")
        assert result is not None
        assert result.x1 == 0
        assert result.y1 == 0
        assert result.x2 == 100
        assert result.y2 == 100
    
    def test_invalid_format(self):
        """Test parsing invalid format."""
        result = parse_bounds("invalid")
        assert result is None
    
    def test_incomplete_bounds(self):
        """Test parsing incomplete bounds."""
        result = parse_bounds("[0,0]")
        assert result is None


class TestFormatBounds:
    """Test cases for format_bounds function."""

    def test_format_bounds(self):
        """Test formatting bounds."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=100)
        result = format_bounds(bounds)
        assert "0" in result
        assert "100" in result
    
    def test_format_tuple(self):
        """Test formatting tuple."""
        result = format_bounds((0, 0, 100, 100))
        assert "0" in result
        assert "100" in result


class TestNormalizeCoordinates:
    """Test cases for normalize_coordinates function."""
    
    def test_basic_normalization(self):
        """Test basic coordinate normalization."""
        result = normalize_coordinates(500, 500, screen_w=1000, screen_h=1000)
        # Returns normalized (x, y)
        assert result[0] is not None
        assert result[1] is not None
    
    def test_none_coordinates(self):
        """Test with None coordinates."""
        result = normalize_coordinates(None, None, screen_w=1000, screen_h=1000)
        assert result == (None, None)


class TestGetBoundsCenter:
    """Test cases for get_bounds_center function."""

    def test_center_calculation(self):
        """Test center point calculation."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=200)
        cx, cy = get_bounds_center(bounds)
        assert cx == 50
        assert cy == 100
    
    def test_tuple_input(self):
        """Test with tuple input."""
        cx, cy = get_bounds_center((0, 0, 100, 200))
        assert cx == 50
        assert cy == 100


class TestIsPointInBounds:
    """Test cases for is_point_in_bounds function."""

    def test_point_inside(self):
        """Test point inside bounds."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=100)
        assert is_point_in_bounds(50, 50, bounds) is True
    
    def test_point_outside(self):
        """Test point outside bounds."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=100)
        assert is_point_in_bounds(150, 50, bounds) is False
        assert is_point_in_bounds(50, 150, bounds) is False
    
    def test_point_on_edge(self):
        """Test point on edge of bounds."""
        bounds = Bounds(x1=0, y1=0, x2=100, y2=100)
        assert is_point_in_bounds(0, 50, bounds) is True
        assert is_point_in_bounds(100, 50, bounds) is True


class TestCalculateIou:
    """Test cases for calculate_iou function."""

    def test_identical_bounds(self):
        """Test identical bounds have IoU of 1."""
        bounds1 = Bounds(x1=0, y1=0, x2=100, y2=100)
        bounds2 = Bounds(x1=0, y1=0, x2=100, y2=100)
        iou = calculate_iou(bounds1, bounds2)
        assert iou == 1.0
    
    def test_no_overlap(self):
        """Test non-overlapping bounds have IoU of 0."""
        bounds1 = Bounds(x1=0, y1=0, x2=10, y2=10)
        bounds2 = Bounds(x1=20, y1=20, x2=30, y2=30)
        iou = calculate_iou(bounds1, bounds2)
        assert iou == 0.0
    
    def test_partial_overlap(self):
        """Test partially overlapping bounds."""
        bounds1 = Bounds(x1=0, y1=0, x2=10, y2=10)
        bounds2 = Bounds(x1=5, y1=5, x2=15, y2=15)
        iou = calculate_iou(bounds1, bounds2)
        # Intersection: 5x5=25, Union: 100+100-25=175
        assert 0 < iou < 1.0


class TestDescribePosition:
    """Test cases for describe_position function."""

    def test_center_position(self):
        """Test describing center position."""
        result = describe_position(0.5, 0.5)
        assert isinstance(result, str)
    
    def test_top_left(self):
        """Test top-left position."""
        result = describe_position(0.0, 0.0)
        assert isinstance(result, str)
    
    def test_bottom_right(self):
        """Test bottom-right position."""
        result = describe_position(0.9, 0.9)
        assert isinstance(result, str)


class TestClampCoordinates:
    """Test cases for clamp_coordinates function."""

    def test_within_bounds(self):
        """Test coordinates within bounds stay the same."""
        result = clamp_coordinates(50, 50, max_x=100, max_y=100)
        assert result == (50, 50)
    
    def test_clamp_x(self):
        """Test clamping x coordinate."""
        result = clamp_coordinates(150, 50, max_x=100, max_y=100)
        assert result == (100, 50)
    
    def test_clamp_y(self):
        """Test clamping y coordinate."""
        result = clamp_coordinates(50, 150, max_x=100, max_y=100)
        assert result == (50, 100)
    
    def test_clamp_both(self):
        """Test clamping both coordinates."""
        result = clamp_coordinates(150, 150, max_x=100, max_y=100)
        assert result == (100, 100)
    
    def test_negative_coordinates(self):
        """Test negative coordinates are clamped to 0."""
        result = clamp_coordinates(-10, -20, max_x=100, max_y=100)
        assert result == (0, 0)
