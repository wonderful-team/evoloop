
const http = require('http');
const { URL } = require('url');

const THREAD_ID = "383918d5-3b6a-433b-8813-79a6f1625860";
const BASE_URL = "http://127.0.0.1:20160/api/v1";
const GUEST_ID = "test-guest-id-123";

console.log(`[TEST] Starting full flow simulation for thread: ${THREAD_ID}`);

// 1. Setup SSE Listener
function startSSE() {
    console.log("[SSE] Connecting...");
    const url = new URL(`${BASE_URL}/stream/chat/${THREAD_ID}?guest_id=${GUEST_ID}`);
    const options = {
        method: 'GET',
        headers: {
            'Accept': 'text/event-stream',
            'x-guest-id': GUEST_ID
        }
    };

    const req = http.request(url, options, (res) => {
        console.log(`[SSE Response Status] ${res.statusCode}`);
        res.on('data', (chunk) => {
            const lines = chunk.toString().split('\n');
            lines.forEach(line => {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        if (data.role === 'ai') {
                            console.log(`\x1b[32m[SSE Message] Role: ai, Status: ${data.status}, Content Snippet: ${data.content?.substring(0, 20)}...\x1b[0m`);
                        } else if (data.type === 'thinking') {
                            console.log(`\x1b[33m[SSE Thinking] ${data.message?.substring(0, 30)}...\x1b[0m`);
                        } else if (data.type === 'progress') {
                            console.log(`\x1b[36m[SSE Progress] ${data.message}\x1b[0m`);
                        }
                    } catch (e) { }
                }
            });
        });
    });
    req.on('error', (e) => console.error(`[SSE Error] ${e.message}`));
    req.end();
}

// 2. Trigger Chat
function triggerChat() {
    console.log("[POST] Triggering chat...");
    const url = new URL(`${BASE_URL}/chat`);
    const postData = JSON.stringify({
        thread_id: THREAD_ID,
        message: "你好，请确认你可以正常讲一个笑话，并告诉我你现在的状态。"
    });

    const options = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData),
            'x-guest-id': GUEST_ID
        }
    };

    const req = http.request(url, options, (res) => {
        let body = '';
        res.on('data', d => body += d);
        res.on('end', () => {
            console.log(`[POST Response] Status: ${res.statusCode}, Body: ${body}`);
        });
    });
    req.on('error', (e) => console.error(`[POST Error] ${e.message}`));
    req.write(postData);
    req.end();
}

// 3. Verify History
function verifyHistory() {
    setTimeout(() => {
        console.log("[GET] Verifying history loading (MessageItem fix)...");
        const url = new URL(`${BASE_URL}/conversations/${THREAD_ID}/messages`);
        const options = {
            headers: { 'x-guest-id': GUEST_ID }
        };
        http.get(url, options, (res) => {
            let body = '';
            res.on('data', d => body += d);
            res.on('end', () => {
                if (res.statusCode === 200) {
                    console.log("\x1b[32m[SUCCESS] History loaded successfully! MessageItem conflict resolved.\x1b[0m");
                    // Check if last message has status
                    try {
                        const data = JSON.parse(body);
                        const lastMsg = data.items[data.items.length - 1];
                        console.log(`[History Check] Last Message Status: ${lastMsg.status}`);
                    } catch (e) { }
                } else {
                    console.log(`\x1b[31m[FAILED] History loading failed with status ${res.statusCode}: ${body}\x1b[0m`);
                }
                process.exit(0);
            });
        }).on('error', (e) => console.error(`[History Error] ${e.message}`));
    }, 15000);
}

startSSE();
setTimeout(triggerChat, 1000);
verifyHistory();
