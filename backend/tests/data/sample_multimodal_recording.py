"""
Sample data generators for multimodal synthesis tests.

These utilities create synthetic test data (images, events) for testing
without requiring actual video files.
"""

import io
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from PIL import Image


@dataclass
class SampleEvent:
    """Sample trace event for testing."""
    timestamp: float
    action_type: str
    mouse_x: Optional[int] = None
    mouse_y: Optional[int] = None
    target_text: Optional[str] = None
    window_title: Optional[str] = None
    app_name: Optional[str] = None
    key_name: Optional[str] = None

    def to_trace_event_dict(self) -> dict:
        """Convert to TraceEvent-compatible dict."""
        return {
            "timestamp": self.timestamp,
            "action_type": self.action_type,
            "mouse_x": self.mouse_x,
            "mouse_y": self.mouse_y,
            "target_text": self.target_text,
            "window_title": self.window_title,
            "app_name": self.app_name,
            "key_name": self.key_name,
        }


@dataclass
class SampleRecording:
    """Complete sample recording for testing."""
    session_id: str
    task_description: str
    video_path: str
    events: List[SampleEvent]
    resolution: tuple = (1920, 1080)
    duration: float = 10.0


class SyntheticFrameGenerator:
    """Generate synthetic frames for testing."""

    @staticmethod
    def create_click_frame(
        width: int = 1920,
        height: int = 1080,
        click_x: int = 960,
        click_y: int = 540,
        button_text: str = "Click Me"
    ) -> Image.Image:
        """Create a frame simulating a button click scenario."""
        img = Image.new('RGB', (width, height), color='#f0f0f0')

        # Draw a "button" rectangle
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        button_width, button_height = 200, 60
        button_left = click_x - button_width // 2
        button_top = click_y - button_height // 2

        # Draw button background
        draw.rectangle(
            [button_left, button_top, button_left + button_width, button_top + button_height],
            fill='#4a90d9',
            outline='#357abd',
            width=2
        )

        # Try to add text
        try:
            draw.text(
                (click_x, click_y),
                button_text,
                fill='white',
                anchor='mm'
            )
        except Exception:
            pass  # Text rendering not critical

        return img

    @staticmethod
    def create_search_frame(
        width: int = 1920,
        height: int = 1080,
        search_text: str = "Search..."
    ) -> Image.Image:
        """Create a frame with a search box."""
        img = Image.new('RGB', (width, height), color='white')

        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        # Draw search box at top
        search_box_height = 60
        draw.rectangle(
            [50, 20, width - 50, 20 + search_box_height],
            fill='#f5f5f5',
            outline='#cccccc',
            width=1
        )

        return img

    @staticmethod
    def save_frame(img: Image.Image, path: str, quality: int = 85) -> str:
        """Save frame to file."""
        img.save(path, 'JPEG', quality=quality)
        return path


class TestRecordingBuilder:
    """Builder for creating test recordings."""

    def __init__(self, session_id: str = "test-session"):
        self.session_id = session_id
        self.events = []
        self.base_time = 1000.0
        self.event_counter = 0

    def add_click(self, x: int, y: int, target_text: str = None, delay_ms: int = 1000):
        """Add a click event."""
        self.events.append(SampleEvent(
            timestamp=self.base_time + self.event_counter * (delay_ms / 1000),
            action_type="mouse_click",
            mouse_x=x,
            mouse_y=y,
            target_text=target_text,
            window_title="Test Window",
            app_name="TestApp"
        ))
        self.event_counter += 1
        return self

    def add_type(self, text: str, delay_ms: int = 500):
        """Add a typing event."""
        for char in text:
            self.events.append(SampleEvent(
                timestamp=self.base_time + self.event_counter * (delay_ms / 1000),
                action_type="key_press",
                key_name=char,
                window_title="Test Window",
                app_name="TestApp"
            ))
            self.event_counter += 1
        return self

    def add_wait(self, duration_ms: int = 1000):
        """Add a wait period (no events, just increment time)."""
        self.event_counter += duration_ms / 1000
        return self

    def build(self, task_description: str = "Test task") -> SampleRecording:
        """Build the sample recording."""
        return SampleRecording(
            session_id=self.session_id,
            task_description=task_description,
            video_path=f"/tmp/test_{self.session_id}.mp4",
            events=self.events,
            duration=self.event_counter
        )


# Pre-built test scenarios

def create_wechat_message_recording() -> SampleRecording:
    """Create a sample WeChat message recording."""
    return (
        TestRecordingBuilder("wechat-test")
        .add_click(100, 50, "Search", 500)
        .add_type("Zhang San", 100)
        .add_click(960, 540, "Zhang San", 1000)
        .add_click(960, 1000, "Message Input", 500)
        .add_type("Hello!", 100)
        .add_click(1800, 1000, "Send Button")
        .build("Send message to Zhang San in WeChat")
    )


def create_browser_search_recording() -> SampleRecording:
    """Create a sample browser search recording."""
    return (
        TestRecordingBuilder("browser-test")
        .add_click(960, 30, "Address Bar", 300)
        .add_type("python tutorial", 50)
        .add_click(960, 300, "Search Result", 2000)
        .build("Search for Python tutorial")
    )


def save_test_scenarios(output_dir: str = "/tmp/evoloop_test_data"):
    """
    Save test scenarios to disk.

    Creates:
    - JSON files with event sequences
    - Synthetic JPEG frames
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    scenarios = {
        "wechat": create_wechat_message_recording(),
        "browser": create_browser_search_recording(),
    }

    generator = SyntheticFrameGenerator()

    for name, recording in scenarios.items():
        scenario_dir = output_path / name
        scenario_dir.mkdir(exist_ok=True)

        # Save events
        events_data = [e.to_trace_event_dict() for e in recording.events]
        with open(scenario_dir / "events.json", "w") as f:
            json.dump(events_data, f, indent=2)

        # Generate and save frames
        for i, event in enumerate(recording.events):
            if event.action_type == "mouse_click":
                frame = generator.create_click_frame(
                    click_x=event.mouse_x or 960,
                    click_y=event.mouse_y or 540,
                    button_text=event.target_text or "Button"
                )
            else:
                frame = generator.create_search_frame()

            generator.save_frame(
                frame,
                str(scenario_dir / f"frame_{i:03d}.jpg")
            )

        print(f"Created test scenario: {scenario_dir}")


if __name__ == "__main__":
    # Generate test data when run directly
    save_test_scenarios()
