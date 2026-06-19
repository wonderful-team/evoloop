import unittest
from datetime import datetime

from app.core.engine.message.extractor import attachment_extractor
from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock


class TestMessageLogicAudit(unittest.TestCase):
    """
    Audit of the core message processing logic: Extraction, Factory Mapping, and Mobile Conversion.
    """

    def test_attachment_extraction_formats(self):
        """Test extraction formats: Markdown links, code block artifacts, and JSON artifacts."""
        content = """
        I have created several files for you:
        1. [Project Report](file:///absolute/path/report.pdf) (Markdown link)
        2. ![System Architecture](file:///absolute/path/diagram.png) (Markdown image)

        And here is a chart:
        ```mermaid
        graph TD;
            A[Start] --> B[End];
        ```

        And a JSON artifact:
        ```json
        {
            "type": "artifact",
            "artifact_type": "echarts",
            "data": {"title": "Sales"}
        }
        ```
        """
        refs = attachment_extractor.extract_from_ai_response(content)

        # Verify counts: file + image + 2 artifacts (code block + json)
        self.assertEqual(len(refs), 4)

        types = [r["type"] for r in refs]
        self.assertIn("file", types)
        self.assertIn("image", types)
        self.assertIn("artifact", types)

        # Verify standard ref details
        img_ref = next(r for r in refs if r["target_name"] == "System Architecture")
        self.assertEqual(img_ref["target_name"], "System Architecture")
        self.assertEqual(img_ref["target_id"], "file:///absolute/path/diagram.png")

        file_ref = next(r for r in refs if r["target_name"] == "Project Report")
        self.assertEqual(file_ref["type"], "file")
        self.assertEqual(file_ref["target_id"], "file:///absolute/path/report.pdf")

    def test_factory_orm_mapping(self):
        """Test MessageBlockFactory handles ORM objects with nested references."""
        class MockRef:
            def __init__(self, id, type, target_id, target_name, meta_data):
                self.id = id
                self.type = type
                self.target_id = target_id
                self.target_name = target_name
                self.meta_data = meta_data

        class MockMessage:
            def __init__(self):
                self.id = "msg-123"
                self.role = "ai"
                self.content = "Hello"
                self.thinking = "Thinking..."
                self.status = "completed"
                self.created_at = datetime.now()
                self.thread_id = "thread-abc"
                self.meta_data = {}
                self.tool_calls = []
                self.references = [
                    MockRef("ref-1", "artifact", "art-1", "Chart", {"artifact_type": "echarts"})
                ]

        msg = MockMessage()
        block = MessageBlockFactory.from_orm(msg)

        self.assertEqual(block.role, "ai")
        self.assertEqual(len(block.references), 1)
        self.assertEqual(block.references[0].type, "artifact")
        self.assertEqual(block.references[0].meta_data["artifact_type"], "echarts")

    def test_mobile_conversion_parity(self):
        """Verify BlockMapper.to_mobile adheres to Unix timestamp and visible int rules."""
        block = MessageBlock(
            id="msg-1",
            thread_id="thread-1",
            role="ai",
            content="Hello Mobile",
            created_at="2024-05-15T10:00:00Z",
            is_visible=True,
            status="completed"
        )

        mobile_data = BlockMapper.to_mobile(block)

        # Check Unix timestamp conversion
        self.assertIsInstance(mobile_data["created_at"], int)
        self.assertTrue(mobile_data["created_at"] > 0)

        # Check visibility conversion
        self.assertEqual(mobile_data["is_visible"], 1)

        # Check exclusion of None fields
        self.assertNotIn("thinking", mobile_data)

if __name__ == "__main__":
    unittest.main()
