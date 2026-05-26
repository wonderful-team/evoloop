import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add backend to path to resolve imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.engine.message.reference import ReferenceService
from app.core.engine.message.schemas import ReferenceContext

async def test_process_references():
    service = ReferenceService()
    
    # Mock session
    session = AsyncMock()
    # Mock a message in DB
    mock_msg = MagicMock()
    mock_msg.content = "Hello world " * 100 # Long content
    session.get.return_value = mock_msg
    
    # Mock document reader
    from app.core.file.document_reader import document_reader_service
    original_read = document_reader_service.read_document
    document_reader_service.read_document = AsyncMock(return_value="File content " * 300)
    
    try:
        references_input = [
            {"type": "message", "id": "msg_1", "name": "Msg 1"},
            {"type": "file", "url": "test.txt", "name": "test.txt"},
            {"type": "image", "url": "http://img.jpg", "name": "img.jpg"},
            {"type": "audio", "url": "http://audio.mp3", "name": "audio.mp3"},
            {"type": "skill", "id": "skill_1", "name": "Skill 1", "metadata": {"skill_id": "skill_1", "skill_name": "Skill 1"}},
            {"type": "file", "url": "test.zip", "name": "test.zip"}, # Binary
        ]
        
        result = await service.process_references(
            message_text="User message",
            references_input=references_input,
            session=session,
            root_path="/tmp",
            thread_id="thread_1",
            project_id=1
        )
        
        assert isinstance(result, ReferenceContext)
        with open("test_output.txt", "w") as f:
            f.write(f"Content blocks: {result.content_blocks}\n")
        assert len(result.content_blocks) == 3 # Main text, Image, Audio
        
        # Check text block
        text = result.content_blocks[0]["text"]
        assert "Msg 1" in text
        assert "test.txt" in text
        assert "audio.mp3" in text
        assert "Skill 1" in text
        
        # Check image block
        assert result.content_blocks[1]["type"] == "image_url"
        assert result.content_blocks[1]["image_url"]["url"] == "http://img.jpg"
        
        # Check notes
        notes = result.reference_notes
        assert any("Quoted Message: Msg 1" in note for note in notes)
        assert any("Referencing File: test.txt" in note for note in notes)
        assert any("Image Reference: img.jpg" in note for note in notes)
        assert any("Audio Reference: audio.mp3" in note for note in notes)
        assert any("Skill: Skill 1" in note for note in notes)
        assert any("Referencing Binary File" in note for note in notes)
        
        print("✅ Test process_references passed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original document reader
        document_reader_service.read_document = original_read

if __name__ == "__main__":
    asyncio.run(test_process_references())
