#!/usr/bin/env python3
"""
Demo script for Window Management Tools.

This demonstrates the window control capabilities of EvoLoop,
similar to Peekaboo's window management features.
"""
import asyncio

from app.infrastructure.drivers.macos_window import macos_window_driver, WindowInfo


def demo_list_windows():
    """Demonstrate listing all windows."""
    print("=" * 60)
    print("🪟 Window Listing Demo")
    print("=" * 60)

    windows = macos_window_driver.list_windows()

    print(f"\nFound {len(windows)} windows:")
    print("-" * 60)
    print(f"{'App':<20} {'Title':<30} {'Position'}")
    print("-" * 60)

    for win in windows[:10]:  # Show first 10
        title = (win.window_title or "")[:30]
        pos = f"({win.bounds['x']}, {win.bounds['y']})" if win.bounds else "N/A"
        print(f"{win.app_name:<20} {title:<30} {pos}")

    if len(windows) > 10:
        print(f"... and {len(windows) - 10} more")


def demo_active_window():
    """Demonstrate getting active window."""
    print("\n" + "=" * 60)
    print("🎯 Active Window Demo")
    print("=" * 60)

    window = macos_window_driver.get_active_window()

    if window:
        print(f"\nCurrent Active Window:")
        print(f"  App: {window.app_name}")
        if window.window_title:
            print(f"  Title: {window.window_title}")
        if window.bounds:
            print(f"  Position: ({window.bounds['x']}, {window.bounds['y']})")
            print(f"  Size: {window.bounds['width']}x{window.bounds['height']}")
        if window.window_id:
            print(f"  Window ID: {window.window_id}")
    else:
        print("No active window found")


def demo_window_info():
    """Demonstrate getting specific window info."""
    print("\n" + "=" * 60)
    print("📋 Window Info Demo")
    print("=" * 60)

    # Get Safari window info if available
    windows = macos_window_driver.list_windows()

    safari_windows = [w for w in windows if "Safari" in w.app_name]
    if safari_windows:
        win = safari_windows[0]
        print(f"\nSafari Window:")
        print(f"  Title: {win.window_title or 'N/A'}")
        if win.bounds:
            print(f"  Bounds: ({win.bounds['x']}, {win.bounds['y']}, "
                  f"{win.bounds['width']}, {win.bounds['height']})")
    else:
        print("\nNo Safari window found")

    # List all unique apps
    apps = sorted(set(w.app_name for w in windows))
    print(f"\nUnique Applications ({len(apps)}):")
    for app in apps[:10]:
        print(f"  - {app}")
    if len(apps) > 10:
        print(f"  ... and {len(apps) - 10} more")


def demo_usage_examples():
    """Show usage examples."""
    print("\n" + "=" * 60)
    print("💡 Window Management Tool Usage Examples")
    print("=" * 60)

    examples = """
# Focus/Activate a window
await window_focus(app_name="Safari")
await window_focus(app_name="WeChat", window_title="File Transfer")

# Resize a window
await window_resize(app_name="Safari", width=1200, height=800)

# Move a window
await window_move(app_name="Safari", x=100, y=50)

# Set position and size together
await window_set_bounds(app_name="Safari", x=0, y=0, width=1200, height=800)

# Minimize/Maximize
await window_minimize(app_name="Safari")
await window_maximize(app_name="Safari")

# Close a window
await window_close(app_name="Safari")

# List windows
await list_windows()
await list_windows(app_filter="Chrome")
await list_windows(include_hidden=True)

# Get window info
await get_active_window()
await get_window_info(app_name="Safari")
"""
    print(examples)


def demo_integration_with_atlas():
    """Show integration with Atlas."""
    print("=" * 60)
    print("🔗 Window Management + Atlas Integration")
    print("=" * 60)

    integration = """
Window Management works seamlessly with Atlas:

1. Focus window before element interaction:
   await window_focus(app_name="WeChat")
   await click_element(element_id="B1")

2. Ensure window is at expected position:
   await window_set_bounds(app_name="WeChat", x=100, y=100, width=800, height=600)
   elements = await get_state_elements("com.tencent.xinWeChat")

3. Multi-window workflows:
   await window_focus(app_name="Safari")
   await click_element(element_id="B1")  # Click in Safari
   await window_focus(app_name="WeChat")
   await click_element(element_id="B2")  # Click in WeChat

4. Window state tracking:
   Atlas can learn window positions and sizes,
   automatically restoring preferred layouts.
"""
    print(integration)


async def main():
    """Run all demos."""
    demo_list_windows()
    demo_active_window()
    demo_window_info()
    demo_usage_examples()
    demo_integration_with_atlas()

    print("\n" + "=" * 60)
    print("✨ Window Management Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
