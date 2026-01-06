import { Monitor, Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useTheme } from "@/components/theme-provider"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()

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
    </div>
  )
}
