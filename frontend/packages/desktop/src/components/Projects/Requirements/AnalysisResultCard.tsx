import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { cn } from "@evoloop/shared/lib/utils"
import {
  Check,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Lightbulb,
  ListTodo,
  ShieldAlert,
  Users,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

interface Requirement {
  id: string
  description: string
  priority: string
  category: string
  acceptance_criteria: string[]
}

interface UserStory {
  id: string
  role: string
  action: string
  benefit: string
  acceptance_criteria: string[]
}

interface TechnicalSuggestion {
  area: string
  suggestion: string
  rationale: string
}

interface Risk {
  description: string
  impact: string
  mitigation: string
}

interface AnalysisData {
  title?: string
  summary?: string
  functional_requirements?: Requirement[]
  non_functional_requirements?: Requirement[]
  user_stories?: UserStory[]
  technical_suggestions?: TechnicalSuggestion[]
  risks?: Risk[]
  dependencies?: string[]
}

interface AnalysisResultCardProps {
  analysisId: string
  data: AnalysisData
  onConfirm: (modifications?: Partial<AnalysisData>) => void
  onRequestChanges?: (feedback: string) => void
}

export function AnalysisResultCard({
  analysisId,
  data,
  onConfirm,
  onRequestChanges,
}: AnalysisResultCardProps) {
  const { t } = useTranslation()
  const [expandedSections, setExpandedSections] = useState<string[]>([
    "summary",
    "functional",
  ])
  const [isEditing, setIsEditing] = useState(false)
  const [editData, setEditData] = useState<AnalysisData>(data)
  const [feedback, setFeedback] = useState("")

  const toggleSection = (section: string) => {
    setExpandedSections((prev) =>
      prev.includes(section)
        ? prev.filter((s) => s !== section)
        : [...prev, section],
    )
  }

  const isExpanded = (section: string) => expandedSections.includes(section)

  const handleConfirm = () => {
    if (isEditing) {
      onConfirm(editData)
    } else {
      onConfirm()
    }
  }

  const handleRequestChanges = () => {
    if (feedback.trim()) {
      onRequestChanges?.(feedback)
    }
  }

  const getPriorityColor = (priority: string) => {
    const colors: Record<string, string> = {
      high: "bg-red-100 text-red-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-green-100 text-green-800",
      urgent: "bg-purple-100 text-purple-800",
    }
    return colors[priority.toLowerCase()] || "bg-gray-100 text-gray-800"
  }

  const getImpactColor = (impact: string) => {
    const colors: Record<string, string> = {
      high: "bg-red-100 text-red-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-green-100 text-green-800",
    }
    return colors[impact.toLowerCase()] || "bg-gray-100 text-gray-800"
  }

  const SectionHeader = ({
    title,
    icon: Icon,
    section,
    count,
  }: {
    title: string
    icon: React.ElementType
    section: string
    count?: number
  }) => (
    <button
      onClick={() => toggleSection(section)}
      className="flex items-center justify-between w-full py-3 px-4 hover:bg-muted/30 rounded-xl transition-all group/header"
    >
      <div className="flex items-center gap-3">
        <div className="p-1.5 rounded-lg bg-muted/50 group-hover/header:bg-primary/10 transition-colors">
          <Icon className="h-4 w-4 text-muted-foreground group-hover/header:text-primary transition-colors" />
        </div>
        <span className="font-bold text-sm tracking-tight">{title}</span>
        {count !== undefined && (
          <span className="text-[10px] bg-muted px-2 py-0.5 rounded-full text-muted-foreground font-bold">
            {count}
          </span>
        )}
      </div>
      <div className="opacity-30 group-hover/header:opacity-100 transition-opacity">
        {isExpanded(section) ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </div>
    </button>
  )

  return (
    <div className="w-full max-w-4xl bg-muted/5 border border-[var(--doc-border)] rounded-xl overflow-hidden shadow-sm my-6 animate-in fade-in slide-in-from-top-2 duration-500">
      <div className="p-6 border-b border-[var(--doc-border)] bg-muted/10">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <ClipboardList className="h-5 w-5 text-primary" />
          </div>
          <span className="uppercase tracking-[0.2em] text-[10px] font-bold text-primary/60">
            {t("requirements.analysis.badge", "Requirement Analysis Report")}
          </span>
        </div>

        <h2 className="text-xl font-bold tracking-tight mb-2">
          {isEditing ? (
            <input
              type="text"
              value={editData.title || ""}
              onChange={(e) =>
                setEditData((prev) => ({ ...prev, title: e.target.value }))
              }
              className="w-full bg-background/50 px-3 py-1.5 border border-primary/20 rounded-md focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          ) : (
            data.title ||
            t("requirements.analysis.untitled", "Untitled Requirement")
          )}
        </h2>

        {data.summary && (
          <div className="text-sm text-muted-foreground/80 leading-relaxed max-w-3xl">
            {isEditing ? (
              <Textarea
                value={editData.summary || ""}
                onChange={(e) =>
                  setEditData((prev) => ({ ...prev, summary: e.target.value }))
                }
                className="mt-2 bg-background/50 border-primary/10"
                rows={3}
              />
            ) : (
              data.summary
            )}
          </div>
        )}
      </div>

      <div className="p-6 space-y-6">
        {/* Functional Requirements */}
        {data.functional_requirements &&
          data.functional_requirements.length > 0 && (
            <div className="space-y-3">
              <SectionHeader
                title={t(
                  "requirements.analysis.functionalRequirements",
                  "Functional Requirements",
                )}
                icon={ListTodo}
                section="functional"
                count={data.functional_requirements.length}
              />
              {isExpanded("functional") && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-2">
                  {data.functional_requirements.map((req) => (
                    <div
                      key={req.id}
                      className="p-4 bg-background border border-[var(--doc-border)] rounded-xl hover:border-primary/20 transition-all group/req"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <span className="text-[10px] font-mono font-bold opacity-30 group-hover/req:opacity-100 transition-opacity">
                          {req.id}
                        </span>
                        <Badge
                          variant="secondary"
                          className={cn(
                            "text-[10px] font-bold uppercase tracking-tighter px-1.5 py-0",
                            getPriorityColor(req.priority),
                          )}
                        >
                          {req.priority}
                        </Badge>
                      </div>
                      <p className="text-sm font-medium mb-3">
                        {req.description}
                      </p>
                      {req.acceptance_criteria?.length > 0 && (
                        <div className="space-y-1.5 border-t border-border/40 pt-3">
                          {req.acceptance_criteria.map((criteria, idx) => (
                            <div
                              key={idx}
                              className="flex items-start gap-2 text-[11px] text-muted-foreground/70"
                            >
                              <Check className="h-3 w-3 mt-0.5 text-primary/50 shrink-0" />
                              <span>{criteria}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        {/* User Stories */}
        {data.user_stories && data.user_stories.length > 0 && (
          <div className="space-y-3">
            <SectionHeader
              title={t("requirements.analysis.userStories", "User Stories")}
              icon={Users}
              section="stories"
              count={data.user_stories.length}
            />
            {isExpanded("stories") && (
              <div className="space-y-3 pl-2">
                {data.user_stories.map((story) => (
                  <div
                    key={story.id}
                    className="p-4 bg-background border border-[var(--doc-border)] rounded-xl"
                  >
                    <div className="text-[10px] font-mono font-bold opacity-30 mb-2">
                      {story.id}
                    </div>
                    <div className="text-[15px] leading-relaxed">
                      <span className="text-muted-foreground font-medium italic">
                        {t("requirements.analysis.asA", "As a")}
                      </span>{" "}
                      <span className="font-bold underline decoration-primary/20">
                        {story.role}
                      </span>
                      ,{" "}
                      <span className="text-muted-foreground font-medium italic">
                        {t("requirements.analysis.iWant", "I want to")}
                      </span>{" "}
                      <span className="font-bold">{story.action}</span>,{" "}
                      <span className="text-muted-foreground font-medium italic">
                        {t("requirements.analysis.soThat", "so that")}
                      </span>{" "}
                      <span className="text-muted-foreground">
                        {story.benefit}
                      </span>
                    </div>
                    {story.acceptance_criteria?.length > 0 && (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {story.acceptance_criteria.map((criteria, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-muted/30 text-[11px] text-muted-foreground border border-border/40"
                          >
                            <Check className="h-3 w-3 text-primary/40" />
                            {criteria}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Technical Suggestions & Risks */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {data.technical_suggestions &&
            data.technical_suggestions.length > 0 && (
              <div className="space-y-3">
                <SectionHeader
                  title={t(
                    "requirements.analysis.technicalSuggestions",
                    "Technical Suggestions",
                  )}
                  icon={Lightbulb}
                  section="technical"
                />
                {isExpanded("technical") && (
                  <div className="space-y-3 pl-2">
                    {data.technical_suggestions.map((suggestion, idx) => (
                      <div
                        key={idx}
                        className="p-3 bg-muted/20 border-l-2 border-primary/20 rounded-r-lg"
                      >
                        <span className="text-[10px] font-bold uppercase tracking-widest text-primary/60 block mb-1">
                          {suggestion.area}
                        </span>
                        <p className="text-sm font-bold mb-1 leading-snug">
                          {suggestion.suggestion}
                        </p>
                        <p className="text-xs text-muted-foreground/70 italic">
                          {suggestion.rationale}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          {data.risks && data.risks.length > 0 && (
            <div className="space-y-3">
              <SectionHeader
                title={t("requirements.analysis.risks", "Risks & Mitigations")}
                icon={ShieldAlert}
                section="risks"
              />
              {isExpanded("risks") && (
                <div className="space-y-3 pl-2">
                  {data.risks.map((risk, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-red-500/5 border-l-2 border-red-500/40 rounded-r-lg"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[9px] font-bold uppercase",
                            getImpactColor(risk.impact),
                          )}
                        >
                          {risk.impact} Impact
                        </Badge>
                      </div>
                      <p className="text-sm font-bold mb-1">
                        {risk.description}
                      </p>
                      <div className="text-xs text-muted-foreground/80 mt-2 bg-background/50 p-2 rounded border border-red-500/10">
                        <span className="font-bold text-[9px] uppercase tracking-tighter mr-1">
                          {t("requirements.analysis.mitigation", "Mitigation")}:
                        </span>{" "}
                        {risk.mitigation}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Feedback Input */}
        {onRequestChanges && (
          <div className="pt-8 border-t border-[var(--doc-border)]">
            <label className="text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground/60 mb-3 block">
              {t("requirements.analysis.feedback", "Revision Feedback")}
            </label>
            <Textarea
              placeholder={t(
                "requirements.analysis.feedbackPlaceholder",
                "Enter your feedback here if you need any adjustments...",
              )}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              rows={3}
              className="bg-background border-border/60 focus:border-primary/40 focus:ring-primary/10 rounded-xl"
            />
          </div>
        )}
      </div>

      <div className="p-6 bg-muted/10 border-t border-[var(--doc-border)] flex flex-wrap justify-between items-center gap-4">
        <div className="flex gap-3">
          {onRequestChanges && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRequestChanges}
              disabled={!feedback.trim()}
              className="rounded-full px-5 border-red-500/20 text-red-600 hover:bg-red-50 font-bold"
            >
              {t("requirements.analysis.requestChanges", "Request Changes")}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsEditing(!isEditing)}
            className="text-muted-foreground hover:text-foreground font-bold"
          >
            {isEditing
              ? t("common.cancel", "Cancel Edit")
              : t("common.edit", "Edit Content")}
          </Button>
        </div>
        <Button
          onClick={handleConfirm}
          className="gap-2 rounded-full px-8 font-bold shadow-lg shadow-primary/20"
        >
          <CheckCircle className="h-4 w-4" />
          {isEditing
            ? t("requirements.analysis.saveAndConfirm", "Save & Confirm")
            : t("requirements.analysis.confirm", "Confirm Analysis")}
        </Button>
      </div>
    </div>
  )
}
