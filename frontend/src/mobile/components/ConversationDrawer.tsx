import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Trash2, Plus } from "lucide-react"
import { useState, useEffect } from "react"
import { EvoLoopApi } from "@/client/evoloopClient"
import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"

interface ConversationDrawerProps {
    activeId?: number
    trigger: React.ReactNode
}

export function ConversationDrawer({ activeId, trigger }: ConversationDrawerProps) {
    const navigate = useNavigate()
    const [conversations, setConversations] = useState<any[]>([])
    const [isOpen, setIsOpen] = useState(false)

    const fetchConversations = () => {
        EvoLoopApi.AI.getConversations(1, 50).then(res => {
            if (res && res.list) {
                setConversations(res.list)
            }
        })
    }

    // Fetch when opened
    useEffect(() => {
        if (isOpen) fetchConversations()
    }, [isOpen])

    const handleDeleteConversation = async (e: any, id: number) => {
        e.stopPropagation()
        if (confirm('Are you sure you want to delete this conversation?')) {
            await EvoLoopApi.AI.deleteConversation(id)
            fetchConversations()
            if (Number(activeId) === id) {
                navigate({ to: '/cloud-chat/new' as any })
            }
        }
    }

    const handleSelectConversation = (id: number) => {
        navigate({ to: `/cloud-chat/${id}` as any })
        setIsOpen(false)
    }

    const handleNewChat = () => {
        navigate({ to: '/cloud-chat/new' as any })
        setIsOpen(false)
    }

    return (
        <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger asChild>
                {trigger}
            </SheetTrigger>
            <SheetContent side="left" className="w-[80vw] sm:w-[350px] p-0">
                <SheetHeader className="p-4 border-b">
                    <SheetTitle className="text-left flex items-center justify-between">
                        Conversations
                        <Button variant="ghost" size="sm" onClick={handleNewChat}>
                            <Plus className="w-4 h-4 mr-1" /> New
                        </Button>
                    </SheetTitle>
                </SheetHeader>
                <div className="overflow-y-auto h-full pb-20">
                    {conversations.map(c => (
                        <div
                            key={c.id}
                            className={`p-3 border-b cursor-pointer hover:bg-muted/50 flex items-center justify-between ${Number(activeId) === c.id ? 'bg-muted' : ''}`}
                            onClick={() => handleSelectConversation(c.id)}
                        >
                            <div className="truncate flex-1 pr-2">
                                <div className="font-medium text-sm truncate">{c.title || 'Untitled'}</div>
                                <div className="text-xs text-muted-foreground">{new Date(c.update_time * 1000).toLocaleString()}</div>
                            </div>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={(e) => handleDeleteConversation(e, c.id)}>
                                <Trash2 className="w-4 h-4" />
                            </Button>
                        </div>
                    ))}
                    {conversations.length === 0 && (
                        <div className="p-4 text-center text-muted-foreground text-sm">No conversations</div>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    )
}
