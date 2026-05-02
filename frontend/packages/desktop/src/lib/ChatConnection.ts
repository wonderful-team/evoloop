import { OpenAPI } from "@/client/core/OpenAPI";

export interface ChatConnectionCallbacks {
    onConnectionChange: (connected: boolean, status: string) => void;
    onToken: (token: string) => void;
    onActivity: (activity: any) => void;  // Lightweight run metadata only (no steps)
    onArtifact: (artifact: any) => void;  // Incremental artifact update
    onStatus: (status: any) => void;      // Incremental status update
    onHumanRequest: (request: any) => void;
    onMessage: (message: any) => void; // Real-time message sync
    onStream?: (streamEvent: any) => void; // Enhanced stream events (thinking, progress, errors)
    onError: (error: string) => void;
    onUnauthorized?: () => void; // 401 未授权回调
}

export class ChatConnection {
    private static instance: ChatConnection;
    private eventSource: EventSource | null = null;
    private currentThreadId: string | null = null;
    private callbacks: ChatConnectionCallbacks | null = null;

    private constructor() { }

    public static getInstance(): ChatConnection {
        if (!ChatConnection.instance) {
            ChatConnection.instance = new ChatConnection();
        }
        return ChatConnection.instance;
    }

    public setCallbacks(callbacks: ChatConnectionCallbacks) {
        this.callbacks = callbacks;
    }

    public async connect(threadId: string | null) {
        // Clean up existing if no threadId
        if (!threadId) {
            this.disconnect();
            return;
        }

        // If already connected to same thread, do nothing
        if (this.eventSource && this.currentThreadId === threadId && this.eventSource.readyState !== EventSource.CLOSED) {
            console.log("[ChatConnection] Already connected to thread", threadId);
            return;
        }

        // Clean up existing
        this.disconnect();

        this.currentThreadId = threadId;
        this.notifyConnectionChange(false, 'connecting');

        // Consolidated Token-based Auth for SSE (EventSource doesn't support headers)
        let token: string | undefined;
        try {
            token = typeof OpenAPI.TOKEN === 'function' ? await (OpenAPI.TOKEN as any)() : OpenAPI.TOKEN;
        } catch (e) {
            console.warn("[ChatConnection] Failed to retrieve auth token", e);
        }

        let url = `${OpenAPI.BASE}/api/v1/stream/chat/${threadId}`;
        const params = new URLSearchParams();
        if (token) {
            params.append('token', token);
        }
        
        // Also try to attach guest_id from localStorage if present as fallback
        const guestId = localStorage.getItem('evoloop-guest-id');
        if (guestId) {
            params.append('guest_id', guestId);
        }

        const queryString = params.toString();
        if (queryString) {
            url += `?${queryString}`;
        }

        console.log(`[ChatConnection] Connecting to ${url}`);

        try {
            this.eventSource = new EventSource(url, { withCredentials: true });
            this.setupListeners(this.eventSource);
        } catch (e) {
            console.error("[ChatConnection] Failed to create EventSource", e);
            this.notifyError("Failed to create connection");
            this.notifyConnectionChange(false, 'error');
        }
    }

    private handleUnauthorized() {
        console.log("[ChatConnection] Handling 401 unauthorized");
        this.disconnect();
        // 触发401回调
        this.callbacks?.onUnauthorized?.();
    }

    public disconnect() {
        if (this.eventSource) {
            console.log("[ChatConnection] Disconnecting");
            this.eventSource.close();
            this.eventSource = null;
        }
        this.currentThreadId = null;
        this.notifyConnectionChange(false, 'disconnected');
    }

    private setupListeners(sse: EventSource) {
        sse.onopen = () => {
            console.log("[ChatConnection] Connected");
            this.notifyConnectionChange(true, 'connected');
        };

        sse.onerror = (e) => {
            // EventSource usually auto-reconnects, but 'error' event fires on network issues
            console.warn("[ChatConnection] Connection Error", e);

            // Check readyState
            if (sse.readyState === EventSource.CLOSED) {
                // Desktop uses Cookie Session; auth errors are handled via stream events.
                this.notifyConnectionChange(false, 'disconnected');
            } else if (sse.readyState === EventSource.CONNECTING) {
                this.notifyConnectionChange(false, 'reconnecting');
            }
        };

        // Custom Events
        sse.addEventListener("token", (e) => {
            try {
                const data = JSON.parse(e.data);
                // Backend sends structured token events
                if (data && typeof data.content === 'string') {
                    this.callbacks?.onToken(data.content);
                } else if (typeof data === 'string') {
                    // Fallback for raw legacy
                    this.callbacks?.onToken(data);
                }
            } catch (err) {
                // Fallback for raw text
                if (e.data) this.callbacks?.onToken(e.data);
            }
        });

        sse.addEventListener("human_request", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onHumanRequest(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse human_request", err);
            }
        });

        // Initial full snapshot (sent once on connect)
        sse.addEventListener("activity", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onActivity(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse activity", err);
            }
        });

        // Incremental updates (no re-fetch needed)
        sse.addEventListener("artifact", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onArtifact(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse artifact", err);
            }
        });

        sse.addEventListener("status", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onStatus(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse status", err);
            }
        });

        // Real-time Message Sync
        sse.addEventListener("message", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onMessage(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse message", err);
            }
        });

        // Enhanced Stream Events (thinking, tool_start, tool_progress, etc.)
        sse.addEventListener("stream", (e) => {
            try {
                const data = JSON.parse(e.data);
                // 检测 EvoLoop 平台认证过期事件，直接触发 401 处理
                if (data.type === 'auth_expired') {
                    console.warn("[ChatConnection] Received auth_expired event");
                    this.handleUnauthorized();
                    return;
                }
                this.callbacks?.onStream?.(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse stream event", err);
            }
        });

        sse.addEventListener("error", (e: any) => {
            try {
                if (e.data) {
                    const data = JSON.parse(e.data);
                    if (data.error) {
                        // 检查是否是401未授权错误
                        if (data.status === 401 || data.code === 'UNAUTHORIZED' || 
                            data.error?.includes?.('401') || data.error?.includes?.('unauthorized')) {
                            console.warn("[ChatConnection] Received 401 error from server");
                            this.handleUnauthorized();
                            return;
                        }
                        this.notifyError(data.error);
                    }
                }
            } catch (err) {
                // ignore
            }
        });

        sse.addEventListener("done", () => {
            // Backend signals separate 'done', but we often keep connection alive for subsequent updates
            // If we wanted to close:
            // this.disconnect();
        });
    }

    private notifyConnectionChange(connected: boolean, status: string) {
        this.callbacks?.onConnectionChange(connected, status);
    }

    private notifyError(msg: string) {
        this.callbacks?.onError(msg);
    }
}
