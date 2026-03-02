"""
Mock implementations for Vision LLM testing.

These mocks simulate multimodal LLM responses for testing purposes,
avoiding actual API calls and associated costs.
"""

from typing import List, Optional
from unittest.mock import MagicMock

from langchain_core.messages import BaseMessage


class MockVisionLLMResponse:
    """Mock response generator for Vision LLM."""

    # Template responses for different task types
    TEMPLATES = {
        "wechat": """
---
name: send_wechat_message
namespace: os/macos/wechat
description: Send a message to a contact in WeChat application
trigger_patterns:
  - "send message to {{contact}} in WeChat"
  - "message {{contact}} on WeChat"
  - "text {{contact}} using WeChat"
parameters:
  - name: contact
    type: string
    required: true
    description: "Name of the contact to message"
  - name: message
    type: string
    required: false
    description: "Message content to send"
---

# 🧠 Expert Skill Guide

## 1. Mental Model
This skill sends a message to a contact in WeChat. The key insight is that WeChat uses a custom UI rendering engine, so we must use visual reasoning (OCR + spatial coordinates) rather than accessibility APIs.

## 2. Visual Anchors
- **Window Title**: Look for "WeChat" or "微信" in the title bar
- **App Icon**: Green speech bubble icon in the dock
- **Search Icon**: Magnifying glass (🔍) in the top-left of the chat list

## 3. Execution Workflow

### Phase 1: Focus and Search
1. **Activate**: Click on WeChat icon or use Cmd+Tab to bring to front
2. **Visual Scan**: Look for the search box at the top of the contact list
3. **Action**: Click the search box (usually contains placeholder "搜索")
4. **Type**: Enter the contact name

### Phase 2: Select Contact
1. **Wait**: Allow 1 second for search results to appear
2. **Visual Scan**: Look for the contact name in the results list
3. **Action**: Click on the matching contact entry
4. **Verify**: Confirm chat window opens with contact name in header

### Phase 3: Send Message
1. **Locate**: Find the message input box at the bottom of the chat window
2. **Action**: Click the input box
3. **Type**: Enter the message content
4. **Send**: Press Enter or click the send button

## 4. Common Pitfalls
- **Timing Issue**: Search results may take 1-2 seconds to load. Don't click immediately after typing.
- **False Positive**: Multiple contacts may match. Check the avatar to confirm correct contact.
- **Hidden Input**: The input box may be covered by the emoji picker. Press Escape to close it.

## 5. Error Recovery
- If search returns no results → Check spelling or try partial name
- If contact not found → Contact may be in "Contacts" tab instead of "Chats"
- If message won't send → Check network connection indicator
""",
        "browser": """
---
name: search_and_navigate
namespace: web/browser
description: Search for a term in the browser and navigate to results
trigger_patterns:
  - "search for {{query}} on Google"
  - "look up {{query}} in browser"
parameters:
  - name: query
    type: string
    required: true
    description: "Search query to execute"
---

# 🧠 Expert Skill Guide

## 1. Mental Model
This skill performs a web search using the browser's address bar or search field.

## 2. Visual Anchors
- **Address Bar**: Look for URL field at top of browser window
- **Search Suggestions**: Dropdown appears below address bar after typing

## 3. Execution Workflow
1. **Focus**: Click on address bar (Cmd+L shortcut)
2. **Type**: Enter search query
3. **Submit**: Press Enter
4. **Wait**: Allow page to load

## 4. Common Pitfalls
- **Focus Issue**: Ensure address bar is focused (highlighted)
- **Wrong Search Engine**: Check which search engine is default
""",
        "default": """
---
name: generic_automation_skill
namespace: misc
description: A generic automation skill based on user demonstration
trigger_patterns:
  - "perform the recorded task"
parameters:
  - name: param1
    type: string
    required: false
    description: "Parameter for the task"
---

# 🧠 Expert Skill Guide

## 1. Mental Model
This skill automates a task based on the observed user demonstration.

## 2. Visual Anchors
- Observe the UI elements visible in the screenshots
- Note the window titles and application names

## 3. Execution Workflow
1. **Analyze**: Understand the current UI state
2. **Locate**: Find the target elements
3. **Interact**: Perform the demonstrated actions
4. **Verify**: Confirm the expected outcome

## 4. Common Pitfalls
- Timing issues: UI may need time to respond
- Coordinate variations: Use relative positions

## 5. Error Recovery
- If element not found, try scrolling
- If action fails, take screenshot to diagnose
"""
    }

    @classmethod
    def get_response(
        cls,
        task_description: str,
        frames_count: int = 5,
        events_count: int = 10
    ) -> str:
        """
        Generate a mock response based on task description.

        Args:
            task_description: The task being automated
            frames_count: Number of frames in the recording
            events_count: Number of events in the recording

        Returns:
            Mock YAML + Markdown response
        """
        task_lower = task_description.lower()

        # Select template based on keywords
        if any(word in task_lower for word in ["wechat", "微信", "message", "send"]):
            return cls.TEMPLATES["wechat"]
        elif any(word in task_lower for word in ["browser", "search", "google", "web"]):
            return cls.TEMPLATES["browser"]
        else:
            return cls.TEMPLATES["default"]


class MockVisionLLM:
    """
    Mock Vision LLM for testing.

    Usage:
        with patch('app.infrastructure.llm.vision.VisionLLMFactory') as mock:
            mock.create_vision_llm.return_value = MockVisionLLM()
    """

    def __init__(self, response_template: Optional[str] = None):
        self.response_template = response_template
        self.calls = []

    async def ainvoke(self, messages: List[BaseMessage]) -> MagicMock:
        """
        Mock async invoke.

        Records the call and returns a mock response.
        """
        self.calls.append(messages)

        # Extract task description from messages
        task_description = ""
        for msg in messages:
            if hasattr(msg, 'content') and isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text = item.get('text', '')
                        if 'Task Description' in text:
                            task_description = text
                            break

        # Generate response
        if self.response_template:
            content = self.response_template
        else:
            content = MockVisionLLMResponse.get_response(task_description)

        # Create mock response
        mock_response = MagicMock()
        mock_response.content = content
        return mock_response

    def assert_called_with_images(self, min_images: int = 1):
        """Assert that the LLM was called with at least N images."""
        for call in self.calls:
            image_count = sum(
                1 for msg in call
                if hasattr(msg, 'content') and isinstance(msg.content, list)
                for item in msg.content
                if isinstance(item, dict) and item.get('type') == 'image_url'
            )
            assert image_count >= min_images, f"Expected at least {min_images} images, got {image_count}"

    def assert_called_with_text(self, expected_text: str):
        """Assert that the LLM was called with specific text."""
        for call in self.calls:
            for msg in call:
                if hasattr(msg, 'content'):
                    content_str = str(msg.content)
                    if expected_text in content_str:
                        return
        raise AssertionError(f"Expected text '{expected_text}' not found in any call")


def create_mock_vision_llm_factory():
    """
    Create a mock VisionLLMFactory for patching.

    Returns:
        A mock factory class that can be used with @patch
    """
    mock_factory = MagicMock()
    mock_factory.create_vision_llm.return_value = MockVisionLLM()
    return mock_factory
