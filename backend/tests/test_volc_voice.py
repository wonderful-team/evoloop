import pytest
from unittest.mock import AsyncMock, patch

from app.infrastructure.voice.volc_protocol import generate_header, parse_response
from app.infrastructure.voice.volc_dialog import VolcDialogClient
from app.api.routes.voice_ws import generate_volc_tts


def test_volc_protocol_header_generation():
    """Verify that protocol header generation produces exactly 4 bytes with correct metadata."""
    header = generate_header()
    assert len(header) == 4
    # Check Protocol Version (0b0001) and Header Size (1)
    assert header[0] == 0x11
    # Check Message Type (CLIENT_FULL_REQUEST = 0b0001) and specific flags (MSG_WITH_EVENT = 0b0100)
    assert header[1] == 0x14


def test_volc_protocol_response_parsing():
    """Verify that parsing server responses maps types and decompresses payloads properly."""
    # Mock a SERVER_FULL_RESPONSE with no payload compression
    # Byte 0: version 1, header size 1 (0x11)
    # Byte 1: message type SERVER_FULL_RESPONSE (0b1001), specific flag MSG_WITH_EVENT (0b0100) -> 0x94
    # Byte 2: JSON serialization (0b0001), no compression (0b0000) -> 0x10
    # Byte 3: reserved (0x00)
    header = bytes([0x11, 0x94, 0x10, 0x00])
    
    # Event field (4 bytes, e.g. 450)
    event_bytes = (450).to_bytes(4, 'big')
    
    # Session ID size (4 bytes) + Session ID string
    session_id = b"test-session-123"
    session_bytes = len(session_id).to_bytes(4, 'big') + session_id
    
    # Payload size (4 bytes) + Payload bytes (JSON encoded)
    payload_data = json_bytes = b'{"asr_result": "hello"}'
    payload_bytes = len(payload_data).to_bytes(4, 'big') + payload_data
    
    msg = header + event_bytes + session_bytes + payload_bytes
    parsed = parse_response(msg)
    
    assert parsed.get("message_type") == "SERVER_FULL_RESPONSE"
    assert parsed.get("event") == 450
    assert parsed.get("session_id") == "test-session-123"
    assert parsed.get("payload_msg") == {"asr_result": "hello"}


def test_volc_client_instantiation():
    """Verify VolcDialogClient instantiation parameters."""
    client = VolcDialogClient(app_id="app-123", access_key="key-abc", session_id="session-xyz")
    assert client.app_id == "app-123"
    assert client.access_key == "key-abc"
    assert client.session_id == "session-xyz"
    assert client.ws is None


@pytest.mark.asyncio
@patch("app.infrastructure.config.service.SystemConfigService.get_value")
async def test_generate_volc_tts_not_configured(mock_get_value):
    """Verify generate_volc_tts raises ValueError when credentials are not configured."""
    mock_get_value.return_value = None
    with pytest.raises(ValueError, match="火山引擎未配置 AppID/AccessKey"):
        await generate_volc_tts("测试", "")
