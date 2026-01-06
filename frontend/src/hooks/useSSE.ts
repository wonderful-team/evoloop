/**
 * React hook for SSE (Server-Sent Events) chat streaming.
 * Provides real-time token streaming and status updates.
 */
import { useEffect, useState, useRef, useCallback } from 'react'

interface UseSSEOptions {
    threadId: string
    enabled: boolean
    onToken?: (token: string) => void
    onStatus?: (status: string) => void
    onActivity?: (data: any) => void
    onDone?: () => void
}

interface SSEState {
    isConnected: boolean
    streamedContent: string
    status: string
}

export function useSSE({ threadId, enabled, onToken, onStatus, onActivity, onDone }: UseSSEOptions): SSEState {
    const [state, setState] = useState<SSEState>({
        isConnected: false,
        streamedContent: '',
        status: 'idle'
    })

    const eventSourceRef = useRef<EventSource | null>(null)

    const connect = useCallback(() => {
        if (!threadId || !enabled) return

        // Close existing connection
        if (eventSourceRef.current) {
            eventSourceRef.current.close()
        }

        const url = `/api/v1/stream/chat/${threadId}`
        const es = new EventSource(url)
        eventSourceRef.current = es

        es.onopen = () => {
            setState(prev => ({ ...prev, isConnected: true, status: 'connected' }))
        }

        es.addEventListener('token', (event) => {
            try {
                const data = JSON.parse(event.data)
                if (data.content) {
                    setState(prev => ({
                        ...prev,
                        streamedContent: prev.streamedContent + data.content
                    }))
                    onToken?.(data.content)
                }
            } catch (e) {
                console.error('Failed to parse token event:', e)
            }
        })

        es.addEventListener('status', (event) => {
            try {
                const data = JSON.parse(event.data)
                setState(prev => ({ ...prev, status: data.status }))
                onStatus?.(data.status)
            } catch (e) {
                console.error('Failed to parse status event:', e)
            }
        })

        es.addEventListener('activity', (event) => {
            try {
                const data = JSON.parse(event.data)
                onActivity?.(data)
            } catch (e) {
                console.error('Failed to parse activity event:', e)
            }
        })

        es.addEventListener('done', () => {
            es.close()
            setState(prev => ({ ...prev, isConnected: false, status: 'done' }))
            onDone?.()
        })

        es.addEventListener('error', () => {
            setState(prev => ({ ...prev, status: 'error' }))
        })

        es.onerror = () => {
            es.close()
            setState(prev => ({ ...prev, isConnected: false, status: 'disconnected' }))
        }

    }, [threadId, enabled, onToken, onStatus, onActivity, onDone])

    useEffect(() => {
        connect()

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close()
            }
        }
    }, [connect])

    // Reset streamed content when thread changes
    useEffect(() => {
        setState(prev => ({ ...prev, streamedContent: '' }))
    }, [threadId])

    return state
}
