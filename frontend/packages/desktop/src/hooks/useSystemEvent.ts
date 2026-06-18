import { useEffect } from "react"
import { type SystemEvent, systemSSEClient } from "@/lib/SystemSSEClient"

export function useSystemEvent(
  eventType: string,
  handler: (event: SystemEvent) => void,
) {
  useEffect(() => {
    systemSSEClient.on(eventType, handler)
    return () => systemSSEClient.off(eventType, handler)
  }, [eventType, handler])
}
