import { useNavigate } from "@tanstack/react-router"
import { Plus, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ConversationsService } from "@/client/sdk.gen"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

interface ConversationDrawerProps {
  activeId?: any
  trigger: React.ReactNode
}

export function ConversationDrawer({
  activeId,
  trigger,
}: ConversationDrawerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [conversations, setConversations] = useState<any[]>([])
  const [isOpen, setIsOpen] = useState(false)

  const fetchConversations = () => {
    // List conversations (new API doesn't use page for listConversations? Check ConversationsService.listConversations)
    // sdk.gen.ts: listConversations(data: { projectId?: ... })
    // It returns list.
    ConversationsService.listConversations().then((res: any) => {
      // new endpoint returns { count, conversations: [...] } or just array?
      // conversations.py: return {"count": ..., "conversations": ...} ? No, wait.
      // conversations.py `list_conversations`: returns `List[ConversationListItem]`.
      // So res IS the array.
      // Legacy expect { list: [] }.
      if (Array.isArray(res)) {
        setConversations(res)
      } else if (res && Array.isArray(res.conversations)) {
        setConversations(res.conversations)
      } else if (res && Array.isArray(res.list)) {
        setConversations(res.list)
      }
    })
  }

  // Fetch when opened
  useEffect(() => {
    if (isOpen) fetchConversations()
  }, [isOpen, fetchConversations])

  const handleDeleteConversation = async (e: any, id: any) => {
    e.stopPropagation()
    if (confirm(t("conversation.deleteConfirm"))) {
      // ID can be string UUID
      await ConversationsService.deleteConversation({ threadId: id })
      fetchConversations()
      if (activeId === id) {
        navigate({ to: "/cloud-chat/new" as any })
      }
    }
  }

  const handleSelectConversation = (id: any) => {
    navigate({ to: `/cloud-chat/${id}` as any })
    setIsOpen(false)
  }

  const handleNewChat = () => {
    navigate({ to: "/cloud-chat/new" as any })
    setIsOpen(false)
  }

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="left" className="w-[80vw] sm:w-[350px] p-0">
        <SheetHeader className="p-4 border-b">
          <SheetTitle className="text-left flex items-center justify-between">
            {t("conversation.list")}
            <Button variant="ghost" size="sm" onClick={handleNewChat}>
              <Plus className="w-4 h-4 mr-1" /> {t("conversation.new")}
            </Button>
          </SheetTitle>
        </SheetHeader>
        <div className="overflow-y-auto h-full pb-20">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`p-3 border-b cursor-pointer hover:bg-muted/50 flex items-center justify-center ${activeId === c.id ? "bg-muted" : ""} justify-between`}
              onClick={() => handleSelectConversation(c.id)}
            >
              <div className="truncate flex-1 pr-2">
                <div className="font-medium text-sm truncate">
                  {c.title || t("conversation.untitled")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {new Date(
                    c.updated_at || c.update_time * 1000,
                  ).toLocaleString()}
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={(e) => handleDeleteConversation(e, c.id)}
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          ))}
          {conversations.length === 0 && (
            <div className="p-4 text-center text-muted-foreground text-sm">
              {t("conversation.empty")}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
