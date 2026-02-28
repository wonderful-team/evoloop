#!/usr/bin/env python3
"""
Storage Management Script - Unified management for screenshots and screen recordings.

Usage:
    python manage_storage.py stats                    # Show all storage statistics
    python manage_storage.py stats --screenshots      # Show screenshots only
    python manage_storage.py stats --recordings       # Show recordings only
    python manage_storage.py cleanup                  # Clean all expired items
    python manage_storage.py cleanup --dry-run        # Preview cleanup
    python manage_storage.py cleanup --screenshots    # Clean screenshots only
    python manage_storage.py cleanup --recordings     # Clean recordings only
    python manage_storage.py config                   # Show storage configuration
    python manage_storage.py test                     # Test storage functionality
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.vision.cleanup import (
    cleanup_screenshots,
    cleanup_screen_recordings,
    cleanup_all,
    get_storage_report,
)
from app.core.vision.storage import (
    ScreenshotPurpose,
    screenshot_storage,
    screen_recording_storage,
)


def show_stats(screenshots: bool = True, recordings: bool = True):
    """Display storage statistics."""
    report = get_storage_report()

    print("\n" + "=" * 70)
    print("📊 Storage Statistics")
    print("=" * 70)

    if screenshots:
        print("\n📸 SCREENSHOTS")
        print("-" * 70)
        for purpose, stats in report["screenshots"]["categories"].items():
            print(f"\n  📁 {purpose.upper()}")
            print(f"     Path: {stats['directory']}")
            print(f"     Files: {stats['file_count']}")
            print(f"     Size: {stats['total_size_mb']:.2f} MB")
            print(f"     Retention: {stats['retention_days']} days")

        print("\n  " + "-" * 66)
        summary = report["screenshots"]["summary"]
        print(f"  📦 Total Files: {summary['total_files']}")
        print(f"  📦 Total Size: {summary['total_size_mb']:.2f} MB ({summary['total_size_gb']:.2f} GB)")

    if recordings:
        print("\n🎬 SCREEN RECORDINGS")
        print("-" * 70)
        for category, stats in report["recordings"]["categories"].items():
            print(f"\n  📁 {category.upper()}")
            print(f"     Path: {stats['directory']}")
            print(f"     Files: {stats['file_count']}")
            print(f"     Size: {stats['total_size_mb']:.2f} MB")

        print("\n  " + "-" * 66)
        summary = report["recordings"]["summary"]
        print(f"  📦 Total Files: {summary['total_files']}")
        print(f"  📦 Total Size: {summary['total_size_mb']:.2f} MB ({summary['total_size_gb']:.2f} GB)")

        limits = report["recordings"]["limits"]
        print(f"\n  ⚠️  Storage Limits:")
        print(f"     Current: {limits['total_size_gb']:.2f} GB / {limits['max_size_gb']} GB")
        if limits["size_limit_exceeded"]:
            print(f"     🔴 LIMIT EXCEEDED!")

    if screenshots and recordings:
        print("\n" + "=" * 70)
        print("📦 GRAND TOTAL")
        print(f"   Total Files: {report['total']['total_files']}")
        print(f"   Total Size: {report['total']['total_size_gb']:.2f} GB")

    print("\n" + "=" * 70)


def show_config():
    """Display storage configuration."""
    print("\n" + "=" * 70)
    print("⚙️  Storage Configuration")
    print("=" * 70)

    print(f"\n📂 Base Directory: {settings.APP_DATA_DIR}")

    print(f"\n📸 Screenshot Directories:")
    print(f"   Temp:    {settings.SCREENSHOTS_TEMP_DIR}")
    print(f"   Atlas:   {settings.SCREENSHOTS_ATLAS_DIR}")
    print(f"   Debug:   {settings.SCREENSHOTS_DEBUG_DIR}")
    print(f"   Dataset: {settings.SCREENSHOTS_DATASET_DIR}")

    print(f"\n🎬 Screen Recording Directories:")
    print(f"   Videos: {settings.SCREEN_RECORDINGS_DIR}")
    print(f"   Frames: {settings.SCREEN_RECORDING_FRAMES_DIR}")

    print(f"\n🗑️  Screenshot Retention Policies:")
    print(f"   Temp:    {settings.SCREENSHOT_TEMP_RETENTION_DAYS} days")
    print(f"   Atlas:   {settings.SCREENSHOT_ATLAS_RETENTION_DAYS} days")
    print(f"   Debug:   {settings.SCREENSHOT_DEBUG_RETENTION_DAYS} days")
    print(f"   Dataset: {settings.SCREENSHOT_DATASET_RETENTION_DAYS} days")

    print(f"\n🗑️  Screen Recording Retention Policies:")
    print(f"   Videos/Frames: {settings.SCREEN_RECORDING_RETENTION_DAYS} days")
    print(f"   Max Total Size: {settings.SCREEN_RECORDING_MAX_SIZE_GB} GB")
    print(f"   Max Duration: {settings.SCREEN_RECORDING_MAX_DURATION_MIN} minutes per recording")
    print(f"   Max File Size: {settings.SCREEN_RECORDING_MAX_SIZE_MB} MB per recording")

    print("\n" + "=" * 70)


def run_cleanup(
    dry_run: bool = False,
    screenshots: bool = True,
    recordings: bool = True
):
    """Run cleanup of expired storage."""
    action = "🔍 Preview" if dry_run else "🧹 Cleaning"

    if screenshots and recordings:
        print(f"\n{action} all expired storage...")
        result = cleanup_all(dry_run=dry_run)
        print(f"\nScreenshots: {result['screenshots']['total']} files")
        print(f"Recordings: {result['recordings']['total']} items")
    elif screenshots:
        print(f"\n{action} expired screenshots...")
        result = cleanup_screenshots(dry_run=dry_run)
        print(f"\n{'Would clean' if dry_run else 'Cleaned'} {result['total']} files:")
        for purpose, count in result["files_cleaned"].items():
            if count > 0:
                print(f"   {purpose}: {count} files")
    elif recordings:
        print(f"\n{action} expired screen recordings...")
        result = cleanup_screen_recordings(dry_run=dry_run)
        print(f"\n{'Would clean' if dry_run else 'Cleaned'} {result['total']} items:")
        for category, count in result["items_cleaned"].items():
            if count > 0:
                print(f"   {category}: {count} items")

    print("\n" + "=" * 70)


def test_storage():
    """Test storage functionality."""
    print("\n🧪 Testing storage functionality...")
    print("-" * 70)

    # Create a minimal PNG (1x1 pixel, transparent)
    minimal_png = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0x0F, 0x00, 0x00,
        0x01, 0x01, 0x00, 0x05, 0x18, 0xD8, 0x4E, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82
    ])

    # Test screenshots
    print("\n📸 Testing Screenshot Storage:")
    for purpose in ["temp", "atlas", "debug", "dataset"]:
        try:
            path = screenshot_storage.save_screenshot(
                image_data=minimal_png,
                purpose=purpose,
                platform="android",
                bundle_id="com.test.example" if purpose == "atlas" else None,
                suffix="test"
            )
            print(f"   ✅ {purpose}: {path}")
            if Path(path).exists():
                Path(path).unlink()
        except Exception as e:
            print(f"   ❌ {purpose}: {e}")

    # Test screen recordings
    print("\n🎬 Testing Screen Recording Storage:")

    # Test recording path
    try:
        path = screen_recording_storage.get_recording_path(
            session_id="test_session_123",
            timestamp=1709123456789
        )
        print(f"   ✅ Recording path: {path}")
    except Exception as e:
        print(f"   ❌ Recording path: {e}")

    # Test frame path
    try:
        path = screen_recording_storage.get_frame_path(
            session_id="test_session_123",
            timestamp_ms=1500
        )
        print(f"   ✅ Frame path: {path}")
        # Cleanup
        if Path(path).parent.exists():
            shutil.rmtree(Path(path).parent)
    except Exception as e:
        print(f"   ❌ Frame path: {e}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Manage screenshot and screen recording storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s stats                               # Show all statistics
    %(prog)s stats --screenshots                 # Show screenshots only
    %(prog)s stats --recordings                  # Show recordings only
    %(prog)s cleanup --dry-run                   # Preview cleanup
    %(prog)s cleanup                             # Actually clean expired files
    %(prog)s cleanup --screenshots               # Clean screenshots only
    %(prog)s cleanup --recordings                # Clean recordings only
    %(prog)s config                              # Show configuration
    %(prog)s test                                # Test storage functionality
        """
    )

    parser.add_argument(
        "command",
        choices=["stats", "cleanup", "config", "test"],
        help="Command to execute"
    )

    # Filter flags
    filter_group = parser.add_argument_group("filter options")
    filter_group.add_argument(
        "--screenshots",
        action="store_true",
        help="Operate on screenshots only"
    )
    filter_group.add_argument(
        "--recordings",
        action="store_true",
        help="Operate on screen recordings only"
    )

    # Other flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup without deleting (for cleanup command)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    # Determine what to operate on (default to both if no filter specified)
    screenshots = args.screenshots or not args.recordings
    recordings = args.recordings or not args.screenshots

    if args.command == "stats":
        if args.json:
            report = get_storage_report()
            print(json.dumps(report, indent=2))
        else:
            show_stats(screenshots=screenshots, recordings=recordings)

    elif args.command == "cleanup":
        run_cleanup(
            dry_run=args.dry_run,
            screenshots=screenshots,
            recordings=recordings
        )

    elif args.command == "config":
        if args.json:
            config = {
                "base_dir": settings.APP_DATA_DIR,
                "screenshots": {
                    "directories": {
                        "temp": settings.SCREENSHOTS_TEMP_DIR,
                        "atlas": settings.SCREENSHOTS_ATLAS_DIR,
                        "debug": settings.SCREENSHOTS_DEBUG_DIR,
                        "dataset": settings.SCREENSHOTS_DATASET_DIR,
                    },
                    "retention_days": {
                        "temp": settings.SCREENSHOT_TEMP_RETENTION_DAYS,
                        "atlas": settings.SCREENSHOT_ATLAS_RETENTION_DAYS,
                        "debug": settings.SCREENSHOT_DEBUG_RETENTION_DAYS,
                        "dataset": settings.SCREENSHOT_DATASET_RETENTION_DAYS,
                    }
                },
                "recordings": {
                    "directories": {
                        "videos": settings.SCREEN_RECORDINGS_DIR,
                        "frames": settings.SCREEN_RECORDING_FRAMES_DIR,
                    },
                    "retention_days": settings.SCREEN_RECORDING_RETENTION_DAYS,
                    "max_size_gb": settings.SCREEN_RECORDING_MAX_SIZE_GB,
                    "max_duration_min": settings.SCREEN_RECORDING_MAX_DURATION_MIN,
                    "max_file_size_mb": settings.SCREEN_RECORDING_MAX_SIZE_MB,
                }
            }
            print(json.dumps(config, indent=2))
        else:
            show_config()

    elif args.command == "test":
        test_storage()


if __name__ == "__main__":
    main()
