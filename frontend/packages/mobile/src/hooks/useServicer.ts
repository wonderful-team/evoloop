/**
 * Mobile-specific Servicer Hook
 * Provides customer support contact functionality
 */
import { useQuery } from "@tanstack/react-query"
import { ConfigService } from "../client"
import useCustomToast from "./useCustomToast"

type Platform = "mobile" | "desktop"

export const useServicer = (platform: Platform = "mobile") => {
  const { showErrorToast } = useCustomToast()

  const { data: config, isLoading } = useQuery({
    queryKey: ["servicerConfig"],
    queryFn: async () => {
      try {
        const res = await ConfigService.getAiConfig()
        return res.data as any
      } catch {
        return null
      }
    },
    staleTime: 1000 * 60 * 60, // 1 hour
  })

  const handleContactSupport = () => {
    if (!config) return

    let url = ""

    // Mobile prioritizes H5 config
    const h5 = config.h5
    if (h5?.type === "wxwork") {
      url = h5.wxwork_url
    } else if (h5?.type === "third") {
      url = h5.third_url
    }

    if (url) {
      window.open(url, "_blank")
    } else {
      showErrorToast("Support not configured.")
    }
  }

  const hasSupport = () => {
    if (!config) return false
    return config.h5?.type === "wxwork" || config.h5?.type === "third"
  }

  return {
    config,
    isLoading,
    handleContactSupport,
    hasSupport: hasSupport(),
  }
}
