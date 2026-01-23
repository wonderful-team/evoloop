import { useNavigate } from "@tanstack/react-router"
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  Command,
  HelpCircle,
  MessageSquare,
  Monitor,
  Zap,
} from "lucide-react"
import { useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"

function QAItem({
  question,
  answer,
}: {
  question: string
  answer: React.ReactNode
}) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="border-b last:border-0 border-border/50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full py-4 text-left font-medium text-sm hover:text-primary transition-colors"
      >
        {question}
        {isOpen ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>
      {isOpen && (
        <div className="pb-4 text-sm text-muted-foreground leading-relaxed animate-in fade-in slide-in-from-top-1 duration-200">
          {answer}
        </div>
      )}
    </div>
  )
}

export function HelpScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <div className="flex flex-col h-full bg-background relative">
      {/* Header */}
      <div className="flex items-center p-4 border-b">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate({ to: "/profile" as any })}
        >
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <h1 className="text-lg font-bold ml-2">{t("help.title")}</h1>
      </div>

      <div className="p-4 overflow-y-auto pb-20">
        {/* Intro Card */}
        <div className="bg-primary/5 rounded-xl p-5 mb-6 border border-primary/10">
          <div className="flex items-center gap-3 mb-3">
            <HelpCircle className="w-6 h-6 text-primary" />
            <h2 className="text-lg font-semibold">{t("help.intro.title")}</h2>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">
            <Trans i18nKey="help.intro.desc" components={{ bold: <b /> }} />
          </p>
        </div>

        <div className="space-y-6">
          {/* Section 1: Capabilities */}
          <section>
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">
              {t("help.capabilities.title")}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-card border rounded-lg p-4 flex flex-col gap-2">
                <MessageSquare className="w-5 h-5 text-blue-500" />
                <h4 className="font-medium text-sm">
                  {t("help.capabilities.cloud.title")}
                </h4>
                <p className="text-xs text-muted-foreground">
                  {t("help.capabilities.cloud.desc")}
                </p>
              </div>
              <div className="bg-card border rounded-lg p-4 flex flex-col gap-2">
                <Monitor className="w-5 h-5 text-green-500" />
                <h4 className="font-medium text-sm">
                  {t("help.capabilities.device.title")}
                </h4>
                <p className="text-xs text-muted-foreground">
                  {t("help.capabilities.device.desc")}
                </p>
              </div>
            </div>
          </section>

          {/* Section 2: FAQ */}
          <section>
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">
              {t("help.faq.title")}
            </h3>
            <div className="bg-card border rounded-lg px-4">
              <QAItem question={t("help.faq.q1")} answer={t("help.faq.a1")} />
              <QAItem
                question={t("help.faq.q2")}
                answer={
                  <Trans
                    i18nKey="help.faq.a2"
                    components={{ bold: <b />, br: <br /> }}
                  />
                }
              />
              <QAItem question={t("help.faq.q3")} answer={t("help.faq.a3")} />
            </div>
          </section>

          {/* Section 3: Tips */}
          <section>
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">
              {t("help.tips.title")}
            </h3>
            <div className="bg-muted/30 rounded-lg p-4 space-y-3">
              <div className="flex gap-3">
                <Zap className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                <p className="text-sm">
                  <span className="font-medium">
                    {t("help.tips.gesture.title")}
                  </span>
                  <br />
                  {t("help.tips.gesture.desc")}
                </p>
              </div>
              <div className="flex gap-3">
                <Command className="w-4 h-4 text-purple-500 shrink-0 mt-0.5" />
                <p className="text-sm">
                  <span className="font-medium">
                    {t("help.tips.slash.title")}
                  </span>
                  <br />
                  <Trans
                    i18nKey="help.tips.slash.desc"
                    components={{ code: <code /> }}
                  />
                </p>
              </div>
            </div>
          </section>

          <div className="pt-8 text-center">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                localStorage.removeItem("evoloop_onboarding_seen")
                window.location.reload()
              }}
            >
              {t("help.replayParams")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
