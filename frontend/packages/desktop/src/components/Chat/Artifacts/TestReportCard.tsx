import {Button} from "@evoloop/shared/components/ui/button"
import {cn} from "@evoloop/shared/lib/utils"
import {AnimatePresence, motion} from "framer-motion"
import {Bug, CheckCircle2, ChevronDown, ChevronRight, Copy, Wrench, XCircle,} from "lucide-react"
import {useState} from "react"
import {useTranslation} from "react-i18next"

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
        "rounded-xl border border-[var(--doc-border)] overflow-hidden my-6 w-full bg-muted/5 transition-all duration-300",
        isPass ? "border-green-500/20" : "border-red-500/20",
      )}
    >
      {/* Header */}
      <button
        type="button"
        className={cn(
          "flex items-center gap-3 p-4 w-full text-left transition-all group/report",
          isPass
            ? "bg-green-500/5 hover:bg-green-500/10"
            : "bg-red-500/5 hover:bg-red-500/10",
        )}
        onClick={() => setExpanded(!expanded)}
      >
        <div
          className={cn(
            "p-2 rounded-lg transition-transform group-hover/report:scale-110",
            isPass
              ? "bg-green-500/10 text-green-600"
              : "bg-red-500/10 text-red-600",
          )}
        >
          {isPass ? (
            <CheckCircle2 className="w-5 h-5" />
          ) : (
            <XCircle className="w-5 h-5" />
          )}
        </div>

        <div className="flex-1">
          <div className="text-[10px] font-bold uppercase tracking-widest opacity-40 mb-0.5">
            {t("chat.artifacts.testReport")}
          </div>
          <div className="font-bold text-sm">
            {data.status === "PASS"
              ? t("chat.artifact.validationSuccessful")
              : t("chat.artifact.validationFailed")}
          </div>
        </div>

        {expanded ? (
          <ChevronDown size={18} className="opacity-20" />
        ) : (
          <ChevronRight size={18} className="opacity-20" />
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
                    {t("chat.artifacts.rootCause")}
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
                      {t("chat.artifacts.fixSuggestion")}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-primary hover:text-primary hover:bg-primary/20"
                      onClick={(e) => {
                        e.stopPropagation()
                        copyFix()
                      }}
                      title={t("common.copyCode")}
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
