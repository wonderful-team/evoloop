import { v4 as uuidv4 } from "uuid"
import { AgentService } from "@/mobile/client"
import { OpenAPI } from "@/client"

interface StreamChatParams {
  message: string
  conversation_id?: string // If undefined, new conversation
  attachments?: any[]
}

/**
 * Helper to stream chat from /api/v1/stream/chat/{thread_id}
 */
export const streamChat = async (
  params: StreamChatParams,
  onChunk: (chunk: string, meta?: any) => void,
): Promise<void> => {
  let threadId = params.conversation_id
  if (!threadId || threadId === "new") {
    threadId = uuidv4()
  }

  // Call Chat Endpoint
  await AgentService.chatEndpoint({
    message: params.message,
    thread_id: threadId,
    attachments: params.attachments
  })

  // 2. Subscribe to Valid Stream
  let token = ""
  try {
    if (typeof OpenAPI.TOKEN === "function") {
      const result = (OpenAPI.TOKEN as any)()
      if (result instanceof Promise) {
        token = await result
      } else {
        token = result as string
      }
    } else {
      token = (OpenAPI.TOKEN as string) || ""
    }
  } catch (e) {
    console.warn("[streamHelper] Failed to get token", e)
  }

  // URL: /api/v1/stream/chat/{thread_id}?token={token}
  const evtSource = new EventSource(
    `${OpenAPI.BASE}/api/v1/stream/chat/${threadId}?token=${token}`,
    {
      withCredentials: true,
    },
  )

  return new Promise((resolve, reject) => {
    evtSource.onmessage = (_event) => {
      // "message" event is usually not used by starlette-sse?
      // Depends on backend. Our backend sends "token", "done", "error".
    }

    evtSource.addEventListener("token", (event) => {
      try {
        // Event data is JSON string? Or just text?
        // data: "token_content"
        // Parse it just in case
        const data = JSON.parse(event.data)
        // Based on backend implementation: yield Event(data=json.dumps(content), event="token")
        onChunk(data)
      } catch (_e) {
        // If not json, maybe raw text?
        onChunk(event.data)
      }
    })

    evtSource.addEventListener("done", (_event) => {
      evtSource.close()
      resolve()
    })

    evtSource.addEventListener("error", (event: any) => {
      // Check if it is a real error or just connection closed
      // If we got 'done' before, we are good.
      // But 'error' event usually means connection failed.
      if (event.data) {
        try {
          const errData = JSON.parse(event.data)
          if (errData.error) {
            evtSource.close()
            reject(new Error(errData.error))
            return
          }
        } catch { }
      }
      // Often SSE "error" event has no data and just fires on disconnect.
      // We assume safe close if we haven't resolved yet.
      // For 401/403 or connection refused, we should FAIL fast to avoid zombies.

      console.warn("SSE Error", event)

      // Check readyState
      if (evtSource.readyState === EventSource.CLOSED) {
        reject(new Error("Stream connection closed unexpectedly"))
      } else {
        // Force close on generic error to prevent infinite retry loop in browser
        evtSource.close()
        reject(new Error("Stream connection failed"))
      }
    })

    // Safety timeout?
  })
}
