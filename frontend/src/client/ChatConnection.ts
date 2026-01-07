import { OpenAPI } from "./core/OpenAPI";

export interface ChatConnectionCallbacks {
    onConnectionChange: (connected: boolean, status: string) => void;
    onToken: (token: string) => void;
    onActivity: (activity: any) => void;
    onHumanRequest: (request: any) => void;
    onError: (error: string) => void;
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

    public async connect(threadId: string) {
        // If already connected to same thread, do nothing
        if (this.eventSource && this.currentThreadId === threadId && this.eventSource.readyState !== EventSource.CLOSED) {
            console.log("[ChatConnection] Already connected to thread", threadId);
            return;
        }

        // Clean up existing
        this.disconnect();

        this.currentThreadId = threadId;
        this.notifyConnectionChange(false, 'connecting');

        let token = "";
        try {
            if (typeof OpenAPI.TOKEN === 'function') {
                const result = (OpenAPI.TOKEN as any)();
                if (result instanceof Promise) {
                    token = await result;
                } else {
                    token = result as string;
                }
            } else {
                token = (OpenAPI.TOKEN as string) || "";
            }
        } catch (e) {
            console.warn("[ChatConnection] Failed to get token", e);
        }

        const url = `${OpenAPI.BASE}/api/v1/stream/chat/${threadId}?token=${token}`;
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
                this.notifyConnectionChange(false, 'disconnected');
            } else if (sse.readyState === EventSource.CONNECTING) {
                this.notifyConnectionChange(false, 'reconnecting');
            }
        };

        // Custom Events
        sse.addEventListener("token", (e) => {
            try {
                const data = JSON.parse(e.data);
                // Phase 3 Refactor: Backend now sends { content: "..." }
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

        sse.addEventListener("activity", (e) => {
            try {
                const data = JSON.parse(e.data);
                this.callbacks?.onActivity(data);
            } catch (err) {
                console.error("[ChatConnection] Failed to parse activity", err);
            }
        });

        sse.addEventListener("error", (e: any) => {
            try {
                if (e.data) {
                    const data = JSON.parse(e.data);
                    if (data.error) {
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
