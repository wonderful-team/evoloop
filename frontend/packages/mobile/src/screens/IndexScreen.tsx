import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Logo } from "@evoloop/shared/components/Logo"
import { ChatInput } from "../components/chat/ChatInput"
// import { Menu } from "lucide-react"
// import { Button } from "@evoloop/shared/components/ui/button"
// import { ConversationDrawer } from "../components/ConversationDrawer"

export function IndexScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const handleInputSend = async (content: string) => {
    // Direct to Cloud Chat (Guests allowed)
    navigate({
      to: "/cloud-chat/new" as any,
      search: { initialMessage: content } as any,
    })
  }

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden">
      {/* Background Decoration */}
      <div className="absolute top-0 left-0 w-full h-[50%] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

      {/* Header (Removed Drawer, clean header) */}
      <div className="absolute top-0 left-0 right-0 p-4 flex justify-between z-20">
        {/* Empty header for spacing if needed, or remove completely */}
      </div>

      {/* Hero Section (Center) */}
      <div className="flex-1 flex flex-col items-center justify-center p-6 -mt-20 z-10">
        <div className="flex flex-col items-center mb-10 animate-in fade-in zoom-in duration-700">
          <div className="mb-6 scale-150">
            <Logo variant="icon" asLink={false} />
          </div>
          <h1 className="text-3xl font-bold text-foreground tracking-tight">
            EvoLoop AI
          </h1>
          <p className="text-sm text-muted-foreground mt-2 font-medium">
            {t("index.subtitle")}
          </p>
        </div>

        {/* Super Input */}
        <div className="w-full max-w-lg mb-8 animate-in slide-in-from-bottom-8 duration-700 delay-100">
          <ChatInput
            isConnected={true}
            isDeviceOnline={true}
            onSend={handleInputSend}
            placeholder={t("index.placeholder")}
            className="w-full"
            innerClassName="flex flex-col gap-3 bg-card/80 backdrop-blur-xl p-4 rounded-xl shadow-xl border border-primary/10 transition-all hover:shadow-2xl hover:border-primary/20"
          />
        </div>
      </div>
    </div>
  )
}
