"""Generate wake response PCM via Volcengine TTS (direct WebSocket protocol).

Usage: cd evoloop && no_proxy="*" uv run --with websockets python scripts/gen_wake_tts.py
"""
import asyncio, json, gzip, uuid, sys
from pathlib import Path
import websockets

sys.path.insert(0, str(Path.home() / 'Projects/develop-assistant.cn/realtime_dialog'))
import config as volc_cfg

OUTPUT = Path.home() / '.evoloop' / 'sounds'
REPLIES = ["我在", "嗯哼", "请说", "你说"]

def hdr(msg_type=0x01, flags=0x04, serial=0x01, compress=0x01):
    return bytes([(1<<4)|1, (msg_type<<4)|flags, (serial<<4)|compress, 0])

def parse(data: bytes) -> dict:
    if len(data) < 4: return {}
    hs = data[0] & 0x0f
    mt = data[1] >> 4
    fl = data[1] & 0x0f
    sr = data[2] >> 4
    cp = data[2] & 0x0f
    pl = data[hs*4:]

    r = {}
    r['message_type'] = {0x0b: 'SERVER_ACK', 0x09: 'SERVER_FULL_RESPONSE'}.get(mt, '?')
    off = 0
    if fl & 0x02: off += 4
    if fl & 0x04:
        r['event'] = int.from_bytes(pl[off:off+4], 'big')
        off += 4
    pl = pl[off:]
    if len(pl) < 4: return r
    sid_len = int.from_bytes(pl[:4], 'big', signed=True)
    if sid_len > 0:
        r['session_id'] = pl[4:4+sid_len].decode('utf-8', errors='replace')
    pl = pl[4+sid_len:]
    if len(pl) < 4: return r
    psz = int.from_bytes(pl[:4], 'big')
    pm = pl[4:4+psz]
    if cp == 0x01 and pm:
        try: pm = gzip.decompress(pm)
        except: pass
    if sr == 0x01 and pm:
        try: pm = json.loads(pm.decode('utf-8'))
        except: pass
    r['payload_msg'] = pm
    return r

async def gen_one(text: str) -> bool:
    out = OUTPUT / f'{text}.pcm'
    if out.exists(): return True

    async with websockets.connect(
        volc_cfg.ws_connect_config['base_url'],
        additional_headers=volc_cfg.ws_connect_config['headers'],
        ping_interval=5,
    ) as ws:

        # StartConnection
        body = gzip.compress(b'{}')
        await ws.send(bytearray(hdr()) + (1).to_bytes(4,'big') + len(body).to_bytes(4,'big') + body)
        await asyncio.wait_for(ws.recv(), timeout=10)

        # StartSession
        sid = uuid.uuid4().hex[:16]
        params = {
            "asr": {"extra": {}},
            "dialog": {
                "bot_name": "EvoLoop",
                "system_role": "你是 EvoLoop。",
                "extra": {"input_mod": "text", "recv_timeout": 60},
            },
            "tts": {
                "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}
            },
        }
        body = gzip.compress(json.dumps(params).encode())
        req = bytearray(hdr()) + (100).to_bytes(4,'big') + len(sid).to_bytes(4,'big') + sid.encode() + len(body).to_bytes(4,'big') + body
        await ws.send(req)
        await asyncio.wait_for(ws.recv(), timeout=10)

        # Send a text query to trigger ASR (required before ChatTTSText can work)
        text_query = json.dumps({"content": "你好"}).encode()
        body = gzip.compress(text_query)
        await ws.send(bytearray(hdr()) + (501).to_bytes(4,'big') + len(sid).to_bytes(4,'big') + sid.encode() + len(body).to_bytes(4,'big') + body)

        # Wait for ASR result (event 459)
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if not isinstance(raw, bytes): continue
            r = parse(raw)
            if r.get('message_type') == 'SERVER_FULL_RESPONSE' and r.get('event') == 459:
                break

        # ChatTTSText: now the dialog session is ready
        for start_flag, end_flag, content in [
            (True, False, text),
            (False, True, ''),
        ]:
            body = gzip.compress(json.dumps({"start": start_flag, "end": end_flag, "content": content}).encode())
            req = bytearray(hdr()) + (500).to_bytes(4,'big') + len(sid).to_bytes(4,'big') + sid.encode() + len(body).to_bytes(4,'big') + body
            await ws.send(req)

        # Receive
        audio = bytearray()
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            if not isinstance(raw, bytes): continue
            r = parse(raw)
            mt = r.get('message_type')
            ev = r.get('event')
            pm = r.get('payload_msg')
            if mt == 'SERVER_ACK' and isinstance(pm, bytes):
                audio.extend(pm)
            elif mt == 'SERVER_FULL_RESPONSE' and ev == 359:
                break

    pcm = bytes(audio)
    if not pcm: return False
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pcm)
    print(f'  OK: {len(pcm)} bytes')
    return True

async def main():
    print('Generating wake sounds via Volcengine TTS...')
    for text in REPLIES:
        print(f'"{text}":', end=' ', flush=True)
        await gen_one(text)
    print(f'Done! Files in {OUTPUT}')

if __name__ == '__main__':
    asyncio.run(main())
