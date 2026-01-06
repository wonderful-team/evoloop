import { AgentService, OpenAPI } from "@/client"

interface StreamChatParams {
  message: string
  conversation_id?: string // If undefined, new conversation
}

/**
 * Helper to stream chat from /api/v1/stream/chat/{thread_id}
 * 1. Post user message to /api/v1/chat (unified endpoint)
 * 2. Connect to SSE stream
 */
export const streamChat = async (
  params: StreamChatParams,
  onChunk: (chunk: string, meta?: any) => void,
): Promise<void> => {
  // 1. Send Message
  // If conversation_id is "new" or undefined, we need to generate one?
  // AgentService.chatEndpoint requires guest_id/token.
  // However, if we are internal (authenticated via token), we might not need guest_id?
  // SDK uses OpenAPI.TOKEN for auth.
  // The chatEndpoint takes query params: guest_id, token.
  // But it also takes headers.

  // We need to know the thread_id AHEAD of time to subscribe to correct stream?
  // Or chatEndpoint returns it?
  // chatEndpoint returns `AgentChatEndpointResponse`.

  // For "new" conversation, usually frontend generates UUID.
  // TODO: Fix deprecated usage of crypto.randomUUID
  let threadId = params.conversation_id
  if (!threadId || threadId === "new") {
    threadId = crypto.randomUUID()
  }

  // Call Chat Endpoint
  // Payload: message (str), thread_id
  await AgentService.chatEndpoint({
    requestBody: {
      message: params.message,
      thread_id: threadId,
    },
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
      // But if we haven't received 'done', it might be error.
      // Let's rely on 'done' event to resolve.
      // If error happens without done, we reject (timeout?)
      // For now, log it.
      console.warn("SSE Error", event)
      // evtSource.close();
      // reject(new Error("Stream connection failed"));
    })

    // Safety timeout?
  })
}
