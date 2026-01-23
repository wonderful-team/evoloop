import { AnimatePresence, motion } from "framer-motion"
import {
  Bug,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  Wrench,
  XCircle,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"

export interface TestReportData {
  status: "PASS" | "FAIL"
  summary: string
  root_cause?: string
  fix_suggestion?: string
  failures?: { name: string; message: string }[]
}

interface TestReportCardProps {
  data: TestReportData
}

export function TestReportCard({ data }: TestReportCardProps) {
  const { t } = useTranslation()
  const isPass = data.status === "PASS"
  const [expanded, setExpanded] = useState(!isPass) // Default expand if failed

  const copyFix = () => {
    if (data.fix_suggestion) {
      navigator.clipboard.writeText(data.fix_suggestion)
    }
  }

  return (
    <div
      className={cn(
        "rounded-xl border overflow-hidden my-2 max-w-2xl bg-card shadow-sm transition-all duration-300",
        isPass ? "border-green-500/20" : "border-red-500/20",
      )}
    >
      {/* Header */}
      <button
        type="button"
        className={cn(
          "flex items-center gap-2 p-3 w-full text-left transition-colors",
          isPass
            ? "bg-green-500/10 hover:bg-green-500/20"
            : "bg-red-500/10 hover:bg-red-500/20",
        )}
        onClick={() => setExpanded(!expanded)}
      >
        {isPass ? (
          <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
        ) : (
          <XCircle className="w-5 h-5 text-red-500 shrink-0" />
        )}

        <div className="flex-1 font-medium text-sm">
          {t("chat.artifacts.testReport", "Test Execution Report")}
        </div>

        <div
          className={cn(
            "text-xs px-2 py-0.5 rounded-full font-bold",
            isPass
              ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
              : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
          )}
        >
          {data.status}
        </div>

        {expanded ? (
          <ChevronDown size={16} className="opacity-50" />
        ) : (
          <ChevronRight size={16} className="opacity-50" />
        )}
      </button>

      {/* Content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 space-y-4 text-sm">
              {/* Summary */}
              <div className="bg-muted/30 p-3 rounded-lg text-muted-foreground leading-relaxed">
                {data.summary}
              </div>

              {/* Root Cause (If Fail) */}
              {data.root_cause && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <Bug size={12} />
                    {t("chat.artifacts.rootCause", "Root Cause Analysis")}
                  </div>
                  <div className="text-foreground pl-5 border-l-2 border-primary/20">
                    {data.root_cause}
                  </div>
                </div>
              )}

              {/* Fix Suggestion (If Fail) */}
              {data.fix_suggestion && (
                <div className="bg-primary/5 rounded-lg border border-primary/10 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-primary/10 border-b border-primary/10">
                    <div className="flex items-center gap-2 text-xs font-semibold text-primary">
                      <Wrench size={12} />
                      {t("chat.artifacts.fixSuggestion", "Suggested Fix")}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-primary hover:text-primary hover:bg-primary/20"
                      onClick={(e) => {
                        e.stopPropagation()
                        copyFix()
                      }}
                      title="Copy Code"
                    >
                      <Copy size={12} />
                    </Button>
                  </div>
                  <div className="p-3 font-mono text-xs overflow-x-auto bg-background/50">
                    <pre>{data.fix_suggestion}</pre>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
