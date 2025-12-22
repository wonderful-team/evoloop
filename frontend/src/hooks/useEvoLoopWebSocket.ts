import { useEffect, useRef, useState, useCallback } from 'react';
import { EvoLoopApi } from '@/client/evoloopClient';
import { toast } from 'sonner';

const WS_URL = import.meta.env.VITE_EVOLOOP_WS_URL || "wss://mall.imagicbox.cn/wss/";

export interface LogMessage {
    type: 'thought' | 'tool' | 'output' | 'error' | 'user';
    content: string;
    thread_id?: string;
    timestamp: number;
}

export function useEvoLoopWebSocket(deviceId: number | null) {
    const [isConnected, setIsConnected] = useState(false);
    const [messages, setMessages] = useState<LogMessage[]>([]);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<any>(null);

    const addMessage = useCallback((msg: LogMessage) => {
        setMessages(prev => [...prev, msg]);
    }, []);

    const connect = useCallback(() => {
        if (!deviceId) return;

        try {
            const ws = new WebSocket(WS_URL);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('[EvoLoop] WS Connected');
                setIsConnected(true);
            };

            ws.onmessage = async (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'init') {
                        const clientId = data.data.client_id;
                        console.log('[EvoLoop] Got client_id:', clientId);
                        // Bind mobile client to user
                        try {
                            await EvoLoopApi.bindMobile(clientId);
                            console.log('[EvoLoop] Mobile Bound');
                        } catch (e) {
                            console.error('[EvoLoop] Bind failed', e);
                            toast.error("Failed to bind to server notifications");
                        }
                    } else if (data.type === 'ping') {
                        // ignore or pong
                    } else if (data.type === 'new_logs') {
                        // Handle batched logs from backend "new_logs" event via Gateway
                        const logs = data.data.logs || [];
                        if (Array.isArray(logs)) {
                            setMessages(prev => {
                                const newMsgs = logs.map((log: any) => ({
                                    type: log.type,
                                    content: log.content,
                                    thread_id: log.thread_id,
                                    timestamp: Date.now() // or log.create_time ?
                                }));
                                return [...prev, ...newMsgs];
                            });
                        }
                    } else if (['thought', 'tool', 'output', 'error'].includes(data.type)) {
                        setMessages(prev => [...prev, {
                            type: data.type,
                            content: data.content,
                            thread_id: data.thread_id,
                            timestamp: Date.now()
                        }]);
                    }
                } catch (e) {
                    console.error('[EvoLoop] WS Parse Error', e);
                }
            };

            ws.onclose = () => {
                console.log('[EvoLoop] WS Closed');
                setIsConnected(false);
                // Simple reconnect
                reconnectTimeoutRef.current = setTimeout(connect, 3000);
            };

            ws.onerror = (e) => {
                console.error('[EvoLoop] WS Error', e);
            };

        } catch (e) {
            console.error('[EvoLoop] Connection failed', e);
        }
    }, [deviceId]);

    useEffect(() => {
        if (deviceId) {
            connect();
        }
        return () => {
            if (wsRef.current) {
                // Prevent reconnect logic from firing on intentional cleanup
                wsRef.current.onclose = null;
                wsRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
    }, [deviceId, connect]);

    const sendMessage = useCallback((msg: any) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
        }
    }, []);

    return { isConnected, messages, sendMessage, addMessage, setMessages, clearMessages: () => setMessages([]) };
}
