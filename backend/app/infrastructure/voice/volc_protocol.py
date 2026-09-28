import gzip
import json
import logging

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 0b0001

# Message Type:
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010

SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
NO_SEQUENCE = 0b0000  # no check sequence
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010

MSG_WITH_EVENT = 0b0100

# Message Serialization
NO_SERIALIZATION = 0b0000
JSON = 0b0001

# Message Compression
NO_COMPRESSION = 0b0000
GZIP = 0b0001


def generate_header(
    version=PROTOCOL_VERSION,
    message_type=CLIENT_FULL_REQUEST,
    message_type_specific_flags=MSG_WITH_EVENT,
    serial_method=JSON,
    compression_type=GZIP,
    reserved_data=0x00,
    extension_header=b"",
):
    header = bytearray()
    header_size = int(len(extension_header) / 4) + 1
    header.append((version << 4) | header_size)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((serial_method << 4) | compression_type)
    header.append(reserved_data)
    header.extend(extension_header)
    return header


def parse_response(res):
    if isinstance(res, str):
        return {}
    if len(res) < 4:
        return {}
    header_size = res[0] & 0x0F
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0F
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0F
    payload = res[header_size * 4 :]
    result = {}
    payload_msg = None
    payload_size = 0
    start = 0
    if message_type == SERVER_FULL_RESPONSE or message_type == SERVER_ACK:
        result["message_type"] = "SERVER_FULL_RESPONSE"
        if message_type == SERVER_ACK:
            result["message_type"] = "SERVER_ACK"
        if message_type_specific_flags & NEG_SEQUENCE > 0:
            result["seq"] = int.from_bytes(payload[:4], "big", signed=False)
            start += 4
        if message_type_specific_flags & MSG_WITH_EVENT > 0:
            result["event"] = int.from_bytes(payload[:4], "big", signed=False)
            start += 4
        payload = payload[start:]
        if len(payload) < 4:
            return result
        session_id_size = int.from_bytes(payload[:4], "big", signed=True)
        if len(payload) < 4 + session_id_size:
            return result
        session_id = payload[4 : session_id_size + 4]
        try:
            result["session_id"] = session_id.decode("utf-8")
        except Exception:
            result["session_id"] = str(session_id)
        payload = payload[4 + session_id_size :]
        if len(payload) < 4:
            return result
        payload_size = int.from_bytes(payload[:4], "big", signed=False)
        payload_msg = payload[4:]
    elif message_type == SERVER_ERROR_RESPONSE:
        code = int.from_bytes(payload[:4], "big", signed=False)
        result["code"] = code
        payload_size = int.from_bytes(payload[4:8], "big", signed=False)
        payload_msg = payload[8:]
    if payload_msg is None:
        return result
    if message_compression == GZIP and len(payload_msg) > 0:
        try:
            payload_msg = gzip.decompress(payload_msg)
        except (OSError, ValueError):
            logger.warning("[volc-protocol] gzip decompress failed, keeping raw bytes", exc_info=True)
    if serialization_method == JSON and len(payload_msg) > 0:
        try:
            payload_msg = json.loads(payload_msg.decode("utf-8"))
        except (OSError, ValueError):
            logger.warning("[volc-protocol] JSON payload decode failed, keeping raw bytes", exc_info=True)
    elif serialization_method != NO_SERIALIZATION:
        try:
            payload_msg = payload_msg.decode("utf-8")
        except (OSError, ValueError):
            logger.warning("[volc-protocol] UTF-8 payload decode failed, keeping raw bytes", exc_info=True)
    result["payload_msg"] = payload_msg
    result["payload_size"] = payload_size
    return result
