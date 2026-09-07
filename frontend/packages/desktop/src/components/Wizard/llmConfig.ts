/**
 * Whether the wizard LLM step is required given the current system config.
 *
 * Platform mode routes through the EvoLoop Gateway, which assigns a default
 * model on the remote side, so there is no local LLM step to run. Only custom
 * mode (user-provided endpoint) needs a model AND a base URL to be present.
 */
export function needsLlmStepForConfig(config: Record<string, string>): boolean {
  const configType = config.LLM_CONFIG_TYPE || "platform"
  if (configType === "platform") {
    return false
  }
  const hasModel = !!config.LLM_MODEL && config.LLM_MODEL !== ""
  return !hasModel || !config.LLM_BASE_URL || config.LLM_BASE_URL === ""
}
