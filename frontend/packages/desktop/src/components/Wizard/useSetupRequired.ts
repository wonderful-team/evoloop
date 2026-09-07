import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { type SystemConfig, SystemService } from "@/client"
import useAuth from "@/hooks/useAuth"
import { needsLlmStepForConfig } from "./llmConfig"

interface SetupStatus {
  /** Whether setup wizard is required */
  required: boolean
  /** Whether still loading config */
  loading: boolean
  /** Which items are missing */
  missingItems: {
    llm: boolean
    workspaceRoot: boolean
  }
}

/**
 * Hook to determine if the setup wizard should be shown
 */
export function useSetupRequired(): SetupStatus {
  const { user } = useAuth()

  const { data: config, isLoading } = useQuery({
    queryKey: ["systemConfig"],
    queryFn: () => SystemService.getSystemConfig(),
    enabled: !!user,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
  })

  return useMemo(() => {
    if (isLoading || !config) {
      return {
        required: false,
        loading: true,
        missingItems: { llm: false, workspaceRoot: false },
      }
    }

    // Convert config array to map
    const configMap: Record<string, string> = {}
    if (Array.isArray(config)) {
      ;(config as unknown as SystemConfig[]).forEach((item) => {
        configMap[item.key] = item.value
      })
    }

    // Check P0 required configurations
    // Platform mode routes through the EvoLoop Gateway which assigns a default
    // model remotely, so there is no local LLM config to require (LLM_MODEL is
    // intentionally cleared on platform apply). Only custom mode needs a model
    // and a user-provided base URL to be present.
    const missingLLM = needsLlmStepForConfig(configMap)

    const missingWorkspaceRoot =
      !configMap.WORKSPACE_ROOT || configMap.WORKSPACE_ROOT === ""

    // Also check if setup was explicitly completed
    const setupCompleted =
      typeof window !== "undefined" &&
      localStorage.getItem("evoloop_setup_completed") === "true"

    return {
      required: !setupCompleted && (missingLLM || missingWorkspaceRoot),
      loading: false,
      missingItems: {
        llm: missingLLM,
        workspaceRoot: missingWorkspaceRoot,
      },
    }
  }, [config, isLoading])
}

/**
 * Mark setup as completed
 */
export function markSetupCompleted() {
  if (typeof window !== "undefined") {
    localStorage.setItem("evoloop_setup_completed", "true")
  }
}

/**
 * Reset setup completed flag (for testing)
 */
export function resetSetupCompleted() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("evoloop_setup_completed")
  }
}
