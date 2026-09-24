import {useTheme} from "@evoloop/shared/components/theme-provider"
import {Label} from "@evoloop/shared/components/ui/label"
import {RadioGroup, RadioGroupItem,} from "@evoloop/shared/components/ui/radio-group"
import {Switch} from "@evoloop/shared/components/ui/switch"
import {Brain, Eye, Monitor, Moon, Palette, Sun} from "lucide-react"
import {useEffect, useState} from "react"
import {useTranslation} from "react-i18next"
import {SettingsCard} from "../Settings/SettingsCard"

const SHOW_THINKING_KEY = "evoloop:showThinking"

export function useShowThinking() {
  const [showThinking, setShowThinking] = useState(() => {
    if (typeof window === "undefined") return true
    const stored = localStorage.getItem(SHOW_THINKING_KEY)
    return stored === null ? true : stored === "true"
  })

  useEffect(() => {
    localStorage.setItem(SHOW_THINKING_KEY, String(showThinking))
  }, [showThinking])

  return { showThinking, setShowThinking }
}

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const { showThinking, setShowThinking } = useShowThinking()

  return (
    <div className="space-y-8">
      <SettingsCard
        icon={Palette}
        title={t("settings.appearance.title")}
        description={t("settings.appearance.description")}
      >
        <RadioGroup
          defaultValue={theme}
          onValueChange={(val) => setTheme(val as any)}
          className="grid grid-cols-1 sm:grid-cols-3 gap-6 pt-2"
        >
          <div className="text-center">
            <Label htmlFor="light" className="cursor-pointer group">
              <RadioGroupItem value="light" id="light" className="sr-only" />
              <div
                className={`overflow-hidden rounded-xl border-2 p-1.5 transition-all duration-200 group-hover:border-primary/50 ${theme === "light" ? "border-primary bg-primary/5" : "border-muted bg-transparent"}`}
              >
                <div className="space-y-2 rounded-lg bg-[#ecedef] p-2">
                  <div className="space-y-2 rounded-md bg-white p-2 shadow-sm">
                    <div className="h-2 w-[80%] rounded-lg bg-[#ecedef]" />
                    <div className="h-2 w-[100%] rounded-lg bg-[#ecedef]" />
                  </div>
                  <div className="flex items-center space-x-2 rounded-md bg-white p-2 shadow-sm">
                    <div className="h-4 w-4 rounded-full bg-primary/20" />
                    <div className="h-2 w-[60%] rounded-lg bg-[#ecedef]" />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center gap-2 pt-3">
                <Sun
                  className={cn(
                    "h-4 w-4 transition-colors",
                    theme === "light"
                      ? "text-primary"
                      : "text-muted-foreground",
                  )}
                />
                <span
                  className={cn(
                    "text-sm font-medium transition-colors",
                    theme === "light" ? "text-primary" : "text-foreground",
                  )}
                >
                  {t("settings.appearance.light")}
                </span>
              </div>
            </Label>
          </div>

          <div className="text-center">
            <Label htmlFor="dark" className="cursor-pointer group">
              <RadioGroupItem value="dark" id="dark" className="sr-only" />
              <div
                className={`overflow-hidden rounded-xl border-2 p-1.5 transition-all duration-200 group-hover:border-primary/50 ${theme === "dark" ? "border-primary bg-primary/5" : "border-muted bg-transparent"}`}
              >
                <div className="space-y-2 rounded-lg bg-slate-950 p-2">
                  <div className="space-y-2 rounded-md bg-slate-900 p-2 shadow-sm">
                    <div className="h-2 w-[80%] rounded-lg bg-slate-800" />
                    <div className="h-2 w-[100%] rounded-lg bg-slate-800" />
                  </div>
                  <div className="flex items-center space-x-2 rounded-md bg-slate-900 p-2 shadow-sm">
                    <div className="h-4 w-4 rounded-full bg-primary/40" />
                    <div className="h-2 w-[60%] rounded-lg bg-slate-800" />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center gap-2 pt-3">
                <Moon
                  className={cn(
                    "h-4 w-4 transition-colors",
                    theme === "dark" ? "text-primary" : "text-muted-foreground",
                  )}
                />
                <span
                  className={cn(
                    "text-sm font-medium transition-colors",
                    theme === "dark" ? "text-primary" : "text-foreground",
                  )}
                >
                  {t("settings.appearance.dark")}
                </span>
              </div>
            </Label>
          </div>

          <div className="text-center">
            <Label htmlFor="system" className="cursor-pointer group">
              <RadioGroupItem value="system" id="system" className="sr-only" />
              <div
                className={`overflow-hidden rounded-xl border-2 p-1.5 transition-all duration-200 group-hover:border-primary/50 ${theme === "system" ? "border-primary bg-primary/5" : "border-muted bg-transparent"}`}
              >
                <div className="space-y-2 rounded-lg bg-slate-950 p-2">
                  <div className="space-y-2 rounded-md bg-slate-900 p-2 shadow-sm">
                    <div className="h-2 w-[80%] rounded-lg bg-slate-800" />
                    <div className="h-2 w-[100%] rounded-lg bg-slate-800" />
                  </div>
                  <div className="flex items-center space-x-2 rounded-md bg-white p-2 shadow-sm">
                    <div className="h-4 w-4 rounded-full bg-primary/20" />
                    <div className="h-2 w-[60%] rounded-lg bg-[#ecedef]" />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center gap-2 pt-3">
                <Monitor
                  className={cn(
                    "h-4 w-4 transition-colors",
                    theme === "system"
                      ? "text-primary"
                      : "text-muted-foreground",
                  )}
                />
                <span
                  className={cn(
                    "text-sm font-medium transition-colors",
                    theme === "system" ? "text-primary" : "text-foreground",
                  )}
                >
                  {t("settings.appearance.system")}
                </span>
              </div>
            </Label>
          </div>
        </RadioGroup>
      </SettingsCard>

      {/* Thinking/Reasoning Display Toggle */}
      <SettingsCard
        icon={Eye}
        title={t("settings.appearance.chatDisplay")}
        description={t("settings.appearance.chatDisplayDesc")}
      >
        <div className="flex items-center justify-between p-4 rounded-md border border-border/50 bg-muted/10 transition-colors hover:bg-muted/20">
          <div className="flex items-center gap-4">
            <div className="rounded-md bg-primary/5 p-2 text-primary">
              <Brain className="h-4 w-4" />
            </div>
            <div className="space-y-1">
              <Label
                htmlFor="show-thinking"
                className="text-sm cursor-pointer font-medium"
              >
                {t("settings.appearance.showThinking")}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t("settings.appearance.showThinkingDesc")}
              </p>
            </div>
          </div>
          <Switch
            id="show-thinking"
            checked={showThinking}
            onCheckedChange={(checked) => setShowThinking(checked)}
          />
        </div>
      </SettingsCard>
    </div>
  )
}

function cn(...classes: any[]) {
  return classes.filter(Boolean).join(" ")
}
