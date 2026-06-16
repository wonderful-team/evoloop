import { useQuery } from "@tanstack/react-query"
import { type SystemConfig, SystemService } from "@/client"

export function useSystemConfig() {
  return useQuery({
    queryKey: ["systemConfig"],
    queryFn: async () => {
      const response = await SystemService.getSystemConfig()
      const configMap: Record<string, string> = {}
      if (Array.isArray(response)) {
        ;(response as unknown as SystemConfig[]).forEach((item) => {
          configMap[item.key] = item.value
        })
      }
      return configMap
    },
    staleTime: 1000 * 60 * 2, // 2 minutes
  })
}
