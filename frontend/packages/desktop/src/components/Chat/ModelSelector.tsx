import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { cn } from "@evoloop/shared/lib/utils"
import { Brain, Cpu, Eye, Globe, Loader2, Server } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { isLoggedIn } from "@/hooks/useAuth"
import { type LLMModel, llmPlatformService } from "@/services/llmPlatform"

interface ModelSelectorProps {
  value: string | null
  onChange: (value: string | null) => void
  disabled?: boolean
}

export function ModelSelector({
  value,
  onChange,
  disabled,
}: ModelSelectorProps) {
  const { t } = useTranslation()
  const [models, setModels] = useState<LLMModel[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const authenticated = isLoggedIn()

  useEffect(() => {
    // Only fetch models if user is logged in
    if (authenticated) {
      loadModels()
    }
  }, [authenticated])

  const loadModels = async () => {
    setIsLoading(true)
    try {
      const all = await llmPlatformService.fetchModels()
      setModels(all)
    } catch (error) {
      console.error("[ModelSelector] Failed to load models:", error)
    } finally {
      setIsLoading(false)
    }
  }

  // 分组模型
  const platformModels = models.filter((m) => m.type === "platform")
  const customModels = models.filter((m) => m.type === "custom")
  // Local models are those discovered from lm-studio/ollama/gguf
  const localProviders = new Set(["lm-studio", "ollama", "gguf", "local"])
  const localModels = models.filter((m) => localProviders.has(m.provider || ""))

  const sourceIcons: Record<string, typeof Cpu> = {
    "lm-studio": Server,
    ollama: Globe,
    gguf: Cpu,
    custom: Brain,
  }

  // 获取当前选中的模型信息 (使用 id 而不是 model，以区分 platform 和 custom)
  const selectedModel = models.find((m) => m.id === value)

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center">
            <Select
              value={value || ""}
              onValueChange={(val) => onChange(val || null)}
              disabled={disabled || isLoading}
            >
              <SelectTrigger
                className={cn(
                  "h-8 w-auto min-w-[120px] max-w-[260px] px-2 text-xs border-0 bg-transparent hover:bg-muted/50 focus:ring-0 focus:ring-offset-0 font-medium",
                  disabled && "opacity-50 cursor-not-allowed",
                )}
              >
                {isLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <Brain className="h-3.5 w-3.5 mr-1 text-muted-foreground" />
                )}
                <SelectValue placeholder={t("chat.modelSelector.placeholder")}>
                  {selectedModel ? (
                    <span className="flex items-center gap-1 truncate">
                      {selectedModel.name}
                      {/*selectedModel.quota_required && (
                        <Star className="h-3 w-3 text-amber-500 fill-amber-500" />
                      )*/}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("chat.modelSelector.selectModel")}
                    </span>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent align="start" className="w-[280px]">
                {/* 平台模型 */}
                {platformModels.length > 0 && (
                  <SelectGroup>
                    <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                      {t("chat.modelSelector.platformModels")}
                    </SelectLabel>
                    {platformModels.map((model) => (
                      <SelectItem
                        key={model.id}
                        value={model.id}
                        className="text-xs py-2"
                      >
                        <span className="flex items-center gap-2 w-full min-w-0">
                          {model.supports_vision ? (
                            <Eye className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          ) : (
                            <Brain className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          )}
                          <span className="flex-1 truncate">{model.name}</span>
                          {/*model.quota_required && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Star className="h-3 w-3 text-amber-500 fill-amber-500 flex-shrink-0" />
                                </TooltipTrigger>
                                <TooltipContent side="right">
                                  <p className="text-xs">{t("chat.modelSelector.requiresQuota")}</p>
                                </TooltipContent>
                              </Tooltip>
                            )*/}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}

                {/* 自定义模型 */}
                {customModels.length > 0 && (
                  <SelectGroup>
                    <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                      {t("chat.modelSelector.customModels")}
                    </SelectLabel>
                    {customModels.map((model) => (
                      <SelectItem
                        key={model.id}
                        value={model.id}
                        className="text-xs py-2"
                      >
                        <span className="flex items-center gap-2 w-full min-w-0">
                          <Brain className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          <span className="flex-1 truncate">{model.name}</span>
                          <span className="text-[10px] text-muted-foreground flex-shrink-0">
                            {model.provider}
                            {model.provider_type &&
                              model.provider_type !== "openai" && (
                                <span className="ml-1 px-1 py-0.5 bg-muted rounded text-[9px]">
                                  {model.provider_type}
                                </span>
                              )}
                          </span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}

                {/* 本地自动发现模型 */}
                {localModels.length > 0 && (
                  <SelectGroup>
                    <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                      {t("chat.modelSelector.localModels")}
                    </SelectLabel>
                    {localModels.map((model) => {
                      const SrcIcon = sourceIcons[model.provider || ""] || Cpu
                      const color =
                        model.provider === "lm-studio"
                          ? "text-amber-500"
                          : model.provider === "ollama"
                            ? "text-green-500"
                            : model.provider === "gguf"
                              ? "text-purple-500"
                              : "text-muted-foreground"
                      return (
                        <SelectItem
                          key={model.id}
                          value={model.id}
                          className="text-xs py-2"
                        >
                          <span className="flex items-center gap-2 w-full min-w-0">
                            <SrcIcon className={`h-3.5 w-3.5 ${color} shrink-0`} />
                            <span className="flex-1 truncate">{model.name}</span>
                            <span className="text-[10px] text-muted-foreground flex-shrink-0">
                              {model.provider}
                            </span>
                          </span>
                        </SelectItem>
                      )
                    })}
                  </SelectGroup>
                )}

                {models.length === 0 && !isLoading && (
                  <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                    {t("chat.modelSelector.noModels")}
                  </div>
                )}
              </SelectContent>
            </Select>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top">
          <p className="text-xs">
            {selectedModel?.description || t("chat.modelSelector.tooltip")}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
