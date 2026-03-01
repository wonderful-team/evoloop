import { useState } from "react"
import { useTranslation } from "react-i18next"
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
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { cn } from "@evoloop/shared/lib/utils"

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
        : [...prev, section]
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
      className="flex items-center justify-between w-full py-2 px-3 hover:bg-muted/50 rounded-lg transition-colors"
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium text-sm">{title}</span>
        {count !== undefined && (
          <Badge variant="secondary" className="text-xs">
            {count}
          </Badge>
        )}
      </div>
      {isExpanded(section) ? (
        <ChevronUp className="h-4 w-4 text-muted-foreground" />
      ) : (
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      )}
    </button>
  )

  return (
    <Card className="w-full max-w-3xl border-primary/20">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2 mb-2">
          <ClipboardList className="h-5 w-5 text-primary" />
          <Badge variant="outline" className="text-xs">
            {t("requirements.analysis.badge", "需求分析结果")}
          </Badge>
        </div>
        <CardTitle className="text-lg">
          {isEditing ? (
            <input
              type="text"
              value={editData.title || ""}
              onChange={(e) =>
                setEditData((prev) => ({ ...prev, title: e.target.value }))
              }
              className="w-full px-2 py-1 border rounded"
            />
          ) : (
            data.title || t("requirements.analysis.untitled", "未命名需求")
          )}
        </CardTitle>
        {data.summary && (
          <CardDescription>
            {isEditing ? (
              <Textarea
                value={editData.summary || ""}
                onChange={(e) =>
                  setEditData((prev) => ({ ...prev, summary: e.target.value }))
                }
                className="mt-2"
                rows={3}
              />
            ) : (
              data.summary
            )}
          </CardDescription>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Functional Requirements */}
        {data.functional_requirements &&
          data.functional_requirements.length > 0 && (
            <div className="border rounded-lg">
              <SectionHeader
                title={t("requirements.analysis.functionalRequirements", "功能需求")}
                icon={ListTodo}
                section="functional"
                count={data.functional_requirements.length}
              />
              {isExpanded("functional") && (
                <ScrollArea className="max-h-60">
                  <div className="p-3 space-y-3">
                    {data.functional_requirements.map((req) => (
                      <div
                        key={req.id}
                        className="p-3 bg-muted/50 rounded-lg"
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <span className="text-sm font-medium">{req.id}</span>
                          <Badge
                            className={cn("text-xs", getPriorityColor(req.priority))}
                          >
                            {req.priority}
                          </Badge>
                        </div>
                        <p className="text-sm mb-2">{req.description}</p>
                        {req.acceptance_criteria?.length > 0 && (
                          <ul className="text-xs text-muted-foreground space-y-1">
                            {req.acceptance_criteria.map((criteria, idx) => (
                              <li key={idx} className="flex items-start gap-1">
                                <Check className="h-3 w-3 mt-0.5 flex-shrink-0" />
                                {criteria}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          )}

        {/* User Stories */}
        {data.user_stories && data.user_stories.length > 0 && (
          <div className="border rounded-lg">
            <SectionHeader
              title={t("requirements.analysis.userStories", "用户故事")}
              icon={Users}
              section="stories"
              count={data.user_stories.length}
            />
            {isExpanded("stories") && (
              <ScrollArea className="max-h-60">
                <div className="p-3 space-y-3">
                  {data.user_stories.map((story) => (
                    <div key={story.id} className="p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium">{story.id}</span>
                      </div>
                      <p className="text-sm mb-2">
                        <span className="text-muted-foreground">{t("requirements.analysis.asA", "作为")}</span>{" "}
                        {story.role}，
                        <span className="text-muted-foreground">{t("requirements.analysis.iWant", "我想要")}</span>{" "}
                        {story.action}，
                        <span className="text-muted-foreground">{t("requirements.analysis.soThat", "以便")}</span>{" "}
                        {story.benefit}
                      </p>
                      {story.acceptance_criteria?.length > 0 && (
                        <ul className="text-xs text-muted-foreground space-y-1">
                          {story.acceptance_criteria.map((criteria, idx) => (
                            <li key={idx} className="flex items-start gap-1">
                              <Check className="h-3 w-3 mt-0.5 flex-shrink-0" />
                              {criteria}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>
        )}

        {/* Technical Suggestions */}
        {data.technical_suggestions &&
          data.technical_suggestions.length > 0 && (
            <div className="border rounded-lg">
              <SectionHeader
                title={t("requirements.analysis.technicalSuggestions", "技术建议")}
                icon={Lightbulb}
                section="technical"
                count={data.technical_suggestions.length}
              />
              {isExpanded("technical") && (
                <div className="p-3 space-y-3">
                  {data.technical_suggestions.map((suggestion, idx) => (
                    <div key={idx} className="p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="mb-2 text-xs">
                        {suggestion.area}
                      </Badge>
                      <p className="text-sm font-medium mb-1">
                        {suggestion.suggestion}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {suggestion.rationale}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        {/* Risks */}
        {data.risks && data.risks.length > 0 && (
          <div className="border rounded-lg">
            <SectionHeader
              title={t("requirements.analysis.risks", "风险与缓解")}
              icon={ShieldAlert}
              section="risks"
              count={data.risks.length}
            />
            {isExpanded("risks") && (
              <div className="p-3 space-y-3">
                {data.risks.map((risk, idx) => (
                  <div key={idx} className="p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge
                        className={cn("text-xs", getImpactColor(risk.impact))}
                      >
                        {risk.impact}
                      </Badge>
                    </div>
                    <p className="text-sm font-medium mb-1">{risk.description}</p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">{t("requirements.analysis.mitigation", "缓解措施")}:</span>{" "}
                      {risk.mitigation}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Dependencies */}
        {data.dependencies && data.dependencies.length > 0 && (
          <div className="border rounded-lg">
            <SectionHeader
              title={t("requirements.analysis.dependencies", "依赖项")}
              icon={CheckCircle}
              section="dependencies"
              count={data.dependencies.length}
            />
            {isExpanded("dependencies") && (
              <div className="p-3">
                <ul className="text-sm space-y-1">
                  {data.dependencies.map((dep, idx) => (
                    <li key={idx} className="flex items-center gap-2">
                      <span className="text-muted-foreground">•</span>
                      {dep}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Feedback Input */}
        {onRequestChanges && (
          <div className="pt-4 border-t">
            <label className="text-sm font-medium mb-2 block">
              {t("requirements.analysis.feedback", "修改意见")}
            </label>
            <Textarea
              placeholder={t(
                "requirements.analysis.feedbackPlaceholder",
                "如有修改意见，请在此输入..."
              )}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              rows={3}
            />
          </div>
        )}
      </CardContent>

      <CardFooter className="flex justify-between pt-4 border-t">
        <div className="flex gap-2">
          {onRequestChanges && (
            <Button
              variant="outline"
              onClick={handleRequestChanges}
              disabled={!feedback.trim()}
            >
              {t("requirements.analysis.requestChanges", "请求修改")}
            </Button>
          )}
          <Button variant="ghost" onClick={() => setIsEditing(!isEditing)}>
            {isEditing
              ? t("common.cancel", "取消编辑")
              : t("common.edit", "编辑")}
          </Button>
        </div>
        <Button onClick={handleConfirm} className="gap-2">
          <Check className="h-4 w-4" />
          {isEditing
            ? t("requirements.analysis.saveAndConfirm", "保存并确认")
            : t("requirements.analysis.confirm", "确认分析")}
        </Button>
      </CardFooter>
    </Card>
  )
}
