import { Brain, Monitor, Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useTheme } from "@evoloop/shared/components/theme-provider"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Label } from "@evoloop/shared/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@evoloop/shared/components/ui/radio-group"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { useEffect, useState } from "react"

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
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.title")}</CardTitle>
          <CardDescription>
            {t("settings.appearance.description")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RadioGroup
            defaultValue={theme}
            onValueChange={(val) => setTheme(val as any)}
            className="grid max-w-md grid-cols-3 gap-8 pt-2"
          >
            <div className="text-center">
              <Label htmlFor="light" className="cursor-pointer">
                <RadioGroupItem value="light" id="light" className="sr-only" />
                <div
                  className={`items-center rounded-md border-2 p-1 hover:border-accent ${theme === "light" ? "border-primary" : "border-muted"}`}
                >
                  <div className="space-y-2 rounded-sm bg-[#ecedef] p-2">
                    <div className="space-y-2 rounded-md bg-white p-2 shadow-sm">
                      <div className="h-2 w-[80px] rounded-lg bg-[#ecedef]" />
                      <div className="h-2 w-[100px] rounded-lg bg-[#ecedef]" />
                    </div>
                    <div className="flex items-center space-x-2 rounded-md bg-white p-2 shadow-sm">
                      <div className="h-4 w-4 rounded-full bg-[#ecedef]" />
                      <div className="h-2 w-[100px] rounded-lg bg-[#ecedef]" />
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-center gap-2 pt-2">
                  <Sun className="h-4 w-4" />
                  <span className="block text-sm font-medium">
                    {t("settings.appearance.light")}
                  </span>
                </div>
              </Label>
            </div>

            <div className="text-center">
              <Label htmlFor="dark" className="cursor-pointer">
                <RadioGroupItem value="dark" id="dark" className="sr-only" />
                <div
                  className={`items-center rounded-md border-2 p-1 hover:border-accent ${theme === "dark" ? "border-primary" : "border-muted"}`}
                >
                  <div className="space-y-2 rounded-sm bg-slate-950 p-2">
                    <div className="space-y-2 rounded-md bg-slate-800 p-2 shadow-sm">
                      <div className="h-2 w-[80px] rounded-lg bg-slate-400" />
                      <div className="h-2 w-[100px] rounded-lg bg-slate-400" />
                    </div>
                    <div className="flex items-center space-x-2 rounded-md bg-slate-800 p-2 shadow-sm">
                      <div className="h-4 w-4 rounded-full bg-slate-400" />
                      <div className="h-2 w-[100px] rounded-lg bg-slate-400" />
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-center gap-2 pt-2">
                  <Moon className="h-4 w-4" />
                  <span className="block text-sm font-medium">
                    {t("settings.appearance.dark")}
                  </span>
                </div>
              </Label>
            </div>

            <div className="text-center">
              <Label htmlFor="system" className="cursor-pointer">
                <RadioGroupItem
                  value="system"
                  id="system"
                  className="sr-only"
                />
                <div
                  className={`items-center rounded-md border-2 p-1 hover:border-accent ${theme === "system" ? "border-primary" : "border-muted"}`}
                >
                  <div className="space-y-2 rounded-sm bg-slate-950 p-2">
                    <div className="space-y-2 rounded-md bg-slate-800 p-2 shadow-sm">
                      <div className="h-2 w-[80px] rounded-lg bg-slate-400" />
                      <div className="h-2 w-[100px] rounded-lg bg-slate-400" />
                    </div>
                    <div className="flex items-center space-x-2 rounded-md bg-white p-2 shadow-sm">
                      <div className="h-4 w-4 rounded-full bg-[#ecedef]" />
                      <div className="h-2 w-[100px] rounded-lg bg-[#ecedef]" />
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-center gap-2 pt-2">
                  <Monitor className="h-4 w-4" />
                  <span className="block text-sm font-medium">
                    {t("settings.appearance.system")}
                  </span>
                </div>
              </Label>
            </div>
          </RadioGroup>
        </CardContent>
      </Card>

      {/* Thinking/Reasoning Display Toggle */}
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance.chatDisplay")}</CardTitle>
          <CardDescription>
            {t("settings.appearance.chatDisplayDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Brain className="h-5 w-5 text-muted-foreground" />
              <div className="space-y-0.5">
                <Label htmlFor="show-thinking">
                  {t("settings.appearance.showThinking")}
                </Label>
                <p className="text-sm text-muted-foreground">
                  {t("settings.appearance.showThinkingDesc")}
                </p>
              </div>
            </div>
            <Checkbox
              id="show-thinking"
              checked={showThinking}
              onCheckedChange={(checked) => setShowThinking(checked === true)}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
