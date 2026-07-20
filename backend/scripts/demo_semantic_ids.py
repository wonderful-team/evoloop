#!/usr/bin/env python3
"""
Demo script for Semantic Element ID system.

This demonstrates how the new element_id system works to provide
stable references to UI elements, inspired by OpenClaw's Peekaboo.
"""
import asyncio

from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState
from app.core.atlas.element_id import ElementIdGenerator


def demo_element_id_generation():
    """Demonstrate semantic ID generation for a typical UI."""
    print("=" * 60)
    print("🎯 Semantic Element ID Generation Demo")
    print("=" * 60)

    # Simulate a typical login form UI
    elements = [
        AtlasElement(role="statictext", label="Username Label", bounds={"x": 50, "y": 50, "width": 100, "height": 20}),
        AtlasElement(role="textfield", label="Username Input", bounds={"x": 50, "y": 80, "width": 200, "height": 30}),
        AtlasElement(role="statictext", label="Password Label", bounds={"x": 50, "y": 130, "width": 100, "height": 20}),
        AtlasElement(role="textfield", label="Password Input", bounds={"x": 50, "y": 160, "width": 200, "height": 30}),
        AtlasElement(role="checkbox", label="Remember Me", bounds={"x": 50, "y": 210, "width": 150, "height": 20}),
        AtlasElement(role="button", label="Login", bounds={"x": 50, "y": 250, "width": 80, "height": 35}),
        AtlasElement(role="button", label="Cancel", bounds={"x": 150, "y": 250, "width": 80, "height": 35}),
        AtlasElement(role="link", label="Forgot Password", bounds={"x": 50, "y": 300, "width": 120, "height": 20}),
    ]

    print(f"\n📋 Raw elements (before ID generation):")
    for el in elements:
        print(f"  - {el.role}: '{el.label}'")

    # Generate semantic IDs
    elements = ElementIdGenerator.generate_ids_for_elements(elements)

    print(f"\n✅ Elements with semantic IDs:")
    print("-" * 60)
    print(f"{'ID':<6} {'Type':<15} {'Label':<25} {'Position'}")
    print("-" * 60)

    for el in elements:
        type_desc = ElementIdGenerator.get_element_type_description(el.element_id)
        pos = f"({el.bounds['x']}, {el.bounds['y']})"
        print(f"{el.element_id:<6} {type_desc:<15} {el.label:<25} {pos}")

    print("-" * 60)


def demo_atlas_state_lookup():
    """Demonstrate looking up elements by semantic ID."""
    print("\n" + "=" * 60)
    print("🔍 Atlas State Element Lookup Demo")
    print("=" * 60)

    # Create a state with elements
    elements = [
        AtlasElement(role="button", label="Send", element_id="B1", bounds={"x": 100, "y": 200, "width": 60, "height": 30}),
        AtlasElement(role="button", label="Cancel", element_id="B2", bounds={"x": 180, "y": 200, "width": 70, "height": 30}),
        AtlasElement(role="textfield", label="Message", element_id="T1", bounds={"x": 100, "y": 150, "width": 300, "height": 30}),
    ]

    state = AtlasState(
        state_id="chat_window_v1",
        window_title="Chat Application",
        elements=elements
    )

    print(f"\n📱 State: {state.window_title}")
    print(f"   Total elements: {len(state.elements)}")

    # Demonstrate lookups
    print("\n🔎 Lookup by element_id:")

    # Find B1
    found = state.get_element_by_id("B1")
    if found:
        print(f"  B1 -> '{found.label}' ({found.role})")

    # Find T1
    found = state.get_element_by_id("T1")
    if found:
        print(f"  T1 -> '{found.label}' ({found.role})")

    # Find non-existent
    found = state.get_element_by_id("B99")
    print(f"  B99 -> {'Found' if found else 'Not found'}")

    print("\n🔎 Lookup by label:")
    found = state.get_element_by_label("Send")
    if found:
        print(f"  'Send' -> ID: {found.element_id}, Coords: ({found.bounds['x']}, {found.bounds['y']})")


def demo_click_element_usage():
    """Demonstrate how click_element tool would use semantic IDs."""
    print("\n" + "=" * 60)
    print("🖱️  Click Element Tool Usage Demo")
    print("=" * 60)

    print("""
The new click_element tool supports multiple ways to target elements:

1️⃣  By Semantic ID (RECOMMENDED - most stable):
   click_element(element_id="B1")
   -> Clicks the first button regardless of position changes

2️⃣  By Element Name:
   click_element(element_name="发送", element_role="button")
   -> Looks up in Atlas first, then falls back to live AX tree

3️⃣  With Atlas Context:
   click_element(element_id="B1", use_atlas=True)
   -> Queries App Atlas for historical location data

Priority Resolution Order:
   ┌─────────────────────────────────────┐
   │ 1. element_id (Semantic ID)         │ ← Most stable
   │ 2. Atlas lookup (historical data)   │
   │ 3. Live AX tree (real-time)         │
   │ 4. Vision/OCR (fallback)            │ ← Least stable
   └─────────────────────────────────────┘
""")


def demo_comparison_with_coordinates():
    """Compare semantic IDs vs coordinate-based clicking."""
    print("\n" + "=" * 60)
    print("📊 Semantic IDs vs Coordinates Comparison")
    print("=" * 60)

    print("""
❌ Old Way (Coordinates):
   desktop_control(action="click", x=150, y=300)

   Problems:
   • Breaks when window moves
   • Breaks on different screen resolutions
   • Breaks when UI layout changes
   • No context about what was clicked

✅ New Way (Semantic IDs):
   click_element(element_id="B1")

   Benefits:
   • Stable across window movements
   • Works across different resolutions
   • Self-documenting (B1 = first button)
   • Atlas learns and improves over time
   • Falls back gracefully if needed

Real-world Example - WeChat:
   • Coordinate approach: click at (500, 300)
     - Works once, fails if window moved

   • Semantic ID approach: click_element(element_id="B1")
     - B1 always maps to the primary action button
     - Atlas remembers: "B1 on WeChat chat screen = Send button"
""")


async def main():
    """Run all demos."""
    demo_element_id_generation()
    demo_atlas_state_lookup()
    demo_click_element_usage()
    demo_comparison_with_coordinates()

    print("\n" + "=" * 60)
    print("✨ Demo Complete!")
    print("=" * 60)
    print("""
Next Steps:
1. Use get_state_elements(bundle_id) to see available elements
2. Use click_element(element_id="B1") for stable interactions
3. Atlas automatically learns and improves element mappings
""")


if __name__ == "__main__":
    asyncio.run(main())
