import {
  Loader2,
  Bot,
  Search,
  Brain,
  ListTodo,
  HelpCircle
} from "lucide-react"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { VList, VListHandle } from "virtua"
import { useAugmentedMessages } from "../../hooks/useAugmentedMessages"
import { MessageItem, DateSeparator, StarterButton } from "./MessageItem"
import { ToolGroup } from "./ToolGroup"
import { ToolBlock } from "./ToolBlock"
import type { LogMessage } from "../../hooks/useEvoLoopWebSocket"

export type UnifiedItem = LogMessage & {
  type?: string
}

interface MessageListProps {
  messages: LogMessage[]
  isProjectInitialized: boolean
  isDeviceOnline: boolean
  highlight?: number | null
  onHITLResponse?: (threadId: string, response: string, commandId?: number) => void
  onStarterClick?: (content: string) => void
  showStarters?: boolean
}

export function MessageList({
  messages,
  isProjectInitialized,
  isDeviceOnline,
  highlight = null,
  onHITLResponse,
  onStarterClick,
  showStarters = false,
}: MessageListProps) {
  const { t } = useTranslation()
  const listRef = useRef<VListHandle>(null)
  const isAtBottomRef = useRef(true)

  const augmentedMessages = useAugmentedMessages(messages)

  // Auto-scroll logic
  useEffect(() => {
    if (listRef.current && isAtBottomRef.current && !highlight) {
      listRef.current.scrollToIndex(messages.length - 1, { align: "end" })
    }
  }, [messages.length, highlight])

  if (!isProjectInitialized) {
    return (
      <div className="h-full flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {t("chat.messageList.initializing")}
        </p>
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="h-full flex-1 flex flex-col items-center justify-center p-6 text-center animate-in fade-in slide-in-from-bottom-4 duration-500">
        <Bot size={56} className="mb-4 opacity-10 text-primary" />
        <h2 className="text-xl font-bold text-foreground">
          {isDeviceOnline ? t("chat.interface.welcome") : t("chat.messageList.offline")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1 mb-8 max-w-[240px]">
          {isDeviceOnline ? t("chat.interface.startPrompt") : t("chat.messageList.offlineDesc")}
        </p>

        {isDeviceOnline && showStarters && (
          <div className="grid grid-cols-2 gap-3 w-full max-w-sm animate-in fade-in slide-in-from-bottom-8 duration-700 delay-200">
            <StarterButton
              icon={<Search className="text-blue-500" />}
              label={t("chat.context.starter.analyzeLabel")}
              desc={t("chat.context.starter.analyzeDesc")}
              onClick={() => onStarterClick?.(t("chat.context.starter.analyze"))}
            />
            <StarterButton
              icon={<Brain className="text-purple-500" />}
              label={t("chat.context.starter.planLabel")}
              desc={t("chat.context.starter.planDesc")}
              onClick={() => onStarterClick?.(t("chat.context.starter.plan"))}
            />
            <StarterButton
              icon={<ListTodo className="text-green-500" />}
              label={t("chat.context.starter.tasksLabel")}
              desc={t("chat.context.starter.tasksDesc")}
              onClick={() => onStarterClick?.(t("chat.context.starter.tasks"))}
            />
            <StarterButton
              icon={<HelpCircle className="text-amber-500" />}
              label={t("chat.context.starter.helpLabel")}
              desc={t("chat.context.starter.helpDesc")}
              onClick={() => onStarterClick?.(t("chat.context.starter.help"))}
            />
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden relative">
      <VList
        ref={listRef}
        className="h-full p-4"
        onScroll={(offset) => {
          if (!listRef.current) return
          const isAtBottom = offset + (listRef.current as any).viewportSize >= (listRef.current as any).scrollSize - 50
          isAtBottomRef.current = isAtBottom
        }}
      >
        {augmentedMessages.map((item: any, i) => {
          if (item.type === "date-separator") {
            return <DateSeparator key={`date-${i}`} date={item.date} />
          }
          if (item.type === "tool-group") {
            return (
              <ToolGroup
                key={`group-${i}`}
                tools={item.tools}
                timestamp={item.timestamp}
                thought={item.thought}
              />
            )
          }
          if (item.type === "tool-block") {
            return (
              <ToolBlock
                key={`tool-block-${i}`}
                toolName={item.toolName}
                result={item.result}
                isFile={item.isFile}
                status={item.status}
                timestamp={item.timestamp}
              />
            )
          }

          if (item.type === "output" || item.type === "error") {
            return null
          }

          return (
            <div
              key={item.log_id || (item as any).id || i}
              id={item.log_id ? `log-${item.log_id}` : undefined}
            >
              <MessageItem
                msg={item}
                onHITLResponse={onHITLResponse}
                isGrouped={item.isRoleGrouped}
                showAvatar={item.showAvatar}
              />
            </div>
          )
        })}
      </VList>
    </div>
  )
}
