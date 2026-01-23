/**
 * Mobile-specific Stream Helper
 * Uses the mobile client API for cloud chat streaming
 */
import { v4 as uuidv4 } from "uuid"
import { AgentService } from "../client"

interface StreamChatParams {
  message: string
  conversation_id?: string // If undefined, new conversation
  attachments?: any[]
}

// Get the cloud API base URL
const getBaseUrl = () => {
  return import.meta.env.VITE_EVOCLOUD_API_URL || "https://mall.imagicbox.cn"
}

/**
 * Helper to stream chat from cloud API
 */
export const streamChat = async (
  params: StreamChatParams,
  onChunk: (chunk: string, meta?: any) => void,
): Promise<void> => {
  let threadId = params.conversation_id
  if (!threadId || threadId === "new") {
    threadId = uuidv4()
  }

  // Call Chat Endpoint via mobile client
  await AgentService.chatEndpoint({
    message: params.message,
    thread_id: threadId,
    attachments: params.attachments
  })

  // Get token from localStorage (mobile auth)
  const token = localStorage.getItem("evoloop_token") || ""

  // Subscribe to SSE stream from cloud
  const baseUrl = getBaseUrl()
  const evtSource = new EventSource(
    `${baseUrl}/api/v1/stream/chat/${threadId}?token=${token}`,
    {
      withCredentials: true,
    },
  )

  return new Promise((resolve, reject) => {
    evtSource.addEventListener("token", (event) => {
      try {
        const data = JSON.parse(event.data)
        onChunk(data)
      } catch (_e) {
        onChunk(event.data)
      }
    })

    evtSource.addEventListener("done", (_event) => {
      evtSource.close()
      resolve()
    })

    evtSource.addEventListener("error", (event: any) => {
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

      console.warn("SSE Error", event)

      if (evtSource.readyState === EventSource.CLOSED) {
        reject(new Error("Stream connection closed unexpectedly"))
      } else {
        evtSource.close()
        reject(new Error("Stream connection failed"))
      }
    })
  })
}
