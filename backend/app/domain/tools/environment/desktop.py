"""
Desktop Control Tool - MacOS desktop interaction capability.
Provides the Agent with the ability to see and interact with the Mac desktop.
"""

import logging
from typing import Literal

from app.core.tools import evoloop_tool
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


@evoloop_tool
async def desktop_control(
    action: Literal["screenshot", "click", "double_click", "type_text", "key_press", "open_app", "applescript", "get_info", "list_apps"],
    x: int | None = None,
    y: int | None = None,
    text: str | None = None,
    key: str | None = None,
    app_name: str | None = None,
    script: str | None = None,
    region: str | None = None,
) -> str:
    """
    Control the MacOS desktop - screenshot, click, type, and more.
    
    This tool enables direct interaction with the Mac desktop environment.
    Use in combination with analyze_image for vision-guided automation.
    
    Args:
        action: The action to perform:
            - "screenshot": Capture the screen. Returns the path to the image file.
            - "click": Click at coordinates (x, y).
            - "double_click": Double-click at coordinates (x, y).
            - "type_text": Type the given text string.
            - "key_press": Press a special key (enter, escape, tab, etc.).
            - "open_app": Open or focus an application by name.
            - "applescript": Execute raw AppleScript code.
            - "get_info": Get system hardware and OS environment info.
            - "list_apps": List installed applications in /Applications.
        x: X coordinate for click action.
        y: Y coordinate for click action.
        text: Text to type for type_text action.
        key: Key name or combination for key_press action (e.g., "enter", "tab", "a", "command+a", "shift+tab").
        app_name: Application name for open_app action (e.g., "Safari", "Terminal").
        script: AppleScript code for applescript action.
        region: Optional region "x,y,w,h" for screenshot action.
    
    Returns:
        Success message or file path (for screenshot).
    
    Example:
        # Take a screenshot
        desktop_control(action="screenshot")
        
        # Open Safari and search
        desktop_control(action="open_app", app_name="Safari")
        desktop_control(action="click", x=400, y=100)  # Click URL bar
        desktop_control(action="type_text", text="deepmind.google")
        desktop_control(action="key_press", key="enter")
    """
    try:
        if action == "screenshot":
            filepath = macos_driver.screenshot(region=region)
            return f"Screenshot saved to: {filepath}\n\nUse analyze_image tool to understand what's on screen."
        
        elif action == "click":
            if x is None or y is None:
                return "Error: 'x' and 'y' coordinates are required for click action."
            
            # Validate coordinates
            screen_w, screen_h = macos_driver.get_screen_size()
            if not (0 <= x <= screen_w and 0 <= y <= screen_h):
                return f"Error: Coordinates ({x}, {y}) are out of screen bounds ({screen_w}x{screen_h})."
            
            macos_driver.click(x, y)
            return f"Clicked at ({x}, {y})."
        
        elif action == "double_click":
            if x is None or y is None:
                return "Error: 'x' and 'y' coordinates are required for double_click action."
            
            # Validate coordinates
            screen_w, screen_h = macos_driver.get_screen_size()
            if not (0 <= x <= screen_w and 0 <= y <= screen_h):
                return f"Error: Coordinates ({x}, {y}) are out of screen bounds ({screen_w}x{screen_h})."
            
            macos_driver.double_click(x, y)
            return f"Double-clicked at ({x}, {y})."
        
        elif action == "type_text":
            if not text:
                return "Error: 'text' is required for type_text action."
            
            macos_driver.type_text(text)
            return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"
            
        elif action == "get_info":
            info = macos_driver.get_system_info()
            return f"System Info: {info}"
            
        elif action == "list_apps":
            apps = macos_driver.list_installed_apps()
            return f"Installed Apps: {apps}"
        
        elif action == "key_press":
            if not key:
                return "Error: 'key' is required for key_press action."
            
            macos_driver.key_press(key)
            return f"Pressed key: {key}"
        
        elif action == "open_app":
            if not app_name:
                return "Error: 'app_name' is required for open_app action."
            
            macos_driver.open_app(app_name)
            return f"Opened application: {app_name}"
        
        elif action == "applescript":
            if not script:
                return "Error: 'script' is required for applescript action."
            
            output = macos_driver.run_applescript(script)
            
            # Intelligent Output Processing
            from app.constants import MAX_OUTPUT_LENGTH
            
            if output:
                # 1. Detect HTML-like content (common in Notes.app output)
                if "</div>" in output or "</body>" in output or "<br>" in output:
                    try:
                        import markdownify
                        # Convert HTML to Markdown (strips extensive tags & base64 images usually)
                        # heading_style="ATX" ensures # Header format
                        md_output = markdownify.markdownify(output, heading_style="ATX")
                        if md_output.strip():
                            output = f"[Converted from HTML to Markdown]\n{md_output}"
                    except ImportError:
                        pass # Fallback to raw output if lib missing
                    except Exception as e:
                        logger.warning(f"Markdown conversion failed: {e}")
            
                # 2. Truncate if still too long
                if len(output) > MAX_OUTPUT_LENGTH:
                    truncated_len = len(output)
                    output = output[:MAX_OUTPUT_LENGTH] + f"\n... [Output truncated, length: {truncated_len}]"
                
            return f"AppleScript executed.\nOutput: {output}" if output else "AppleScript executed successfully."
        
        else:
            return f"Error: Unknown action '{action}'."
    
    except PermissionError as e:
        return f"⚠️ PERMISSION ERROR: {e}\n\nPlease grant Accessibility access to the terminal/application running this backend."
    
    except Exception as e:
        logger.error(f"Desktop control error: {e}")
        return f"Error: {str(e)}"
