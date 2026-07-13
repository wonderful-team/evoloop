import { useTranslation } from "react-i18next"

import { useAgentStore } from "@/stores/agentStore"

/**
 * Live macro execution step feed (macro_thought stream for the active chat
 * thread). Renders nothing when no macro has run; steps reset on each run
 * start (agentStore._handleRunStart).
 */
export function MacroRunFeed() {
  const { t } = useTranslation()
  const steps = useAgentStore((s) => s.macroSteps)

  if (steps.length === 0) return null

  return (
    <div className="shrink-0 border-b bg-muted/30 px-3 py-2 max-h-32 overflow-y-auto">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
        {t("learning.macroRun.title")}
      </div>
      <div className="font-mono text-xs space-y-0.5">
        {steps.map((s, i) => (
          <div key={i} className="text-muted-foreground truncate">
            {s.text}
          </div>
        ))}
      </div>
    </div>
  )
}
