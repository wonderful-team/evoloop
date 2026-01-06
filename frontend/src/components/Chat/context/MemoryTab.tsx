import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Plus, RefreshCw } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { MemoryService } from "@/client"
import type { ConceptResponse } from "@/client/types.gen"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useChatStore } from "@/stores/chatStore" // Phase 7
import { MessageContent } from "../MessageContent"

interface MemoryTabProps {
  projectId?: number
}

export function MemoryTab({ projectId }: MemoryTabProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Phase 7: Get active memories from store
  const activeMemories = useChatStore((s) => s.activeMemories)
  const isActive = (conceptName: string) => {
    return activeMemories.some((m) =>
      m.name?.toLowerCase().includes(conceptName.toLowerCase()),
    )
  }

  // Add Memory State
  const [isAddMemoryOpen, setIsAddMemoryOpen] = useState(false)
  const [newMemoryName, setNewMemoryName] = useState("")
  const [newMemoryDesc, setNewMemoryDesc] = useState("")

  // 1. Memory Concepts
  const {
    data: concepts,
    isLoading: isLoadingMemory,
    refetch: refetchMemory,
  } = useQuery({
    queryKey: ["projectMemory", projectId],
    queryFn: async () => {
      if (typeof projectId !== "number" || Number.isNaN(projectId)) return []
      // Using search with empty string to get all (as per backend impl)
      const res = await MemoryService.listConcepts({ projectId })
      return res as ConceptResponse[]
    },
    enabled: typeof projectId === "number" && !Number.isNaN(projectId),
  })

  // Add Memory Mutation
  const addMemoryMutation = useMutation({
    mutationFn: async () => {
      if (typeof projectId !== "number" || Number.isNaN(projectId))
        throw new Error("No project selected")
      return MemoryService.addConcept({
        projectId,
        requestBody: {
          name: newMemoryName,
          description: newMemoryDesc,
          related_files: [],
        },
      })
    },
    onSuccess: () => {
      toast.success(t("chat.context.addMemory.success"))
      setIsAddMemoryOpen(false)
      setNewMemoryName("")
      setNewMemoryDesc("")
      queryClient.invalidateQueries({ queryKey: ["projectMemory", projectId] })
    },
    onError: (err) => {
      console.error(err)
      toast.error(t("common.error.message"))
    },
  })

  const handleAddMemory = () => {
    if (!newMemoryName.trim()) return
    addMemoryMutation.mutate()
  }

  if (!projectId) return null

  return (
    <div className="h-full m-0 flex flex-col">
      <div className="p-2 border-b flex justify-between items-center bg-muted/20">
        <span className="text-xs font-medium text-muted-foreground">
          {t("chat.context.memoryTitle")}
        </span>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => refetchMemory()}
          >
            <RefreshCw
              className={`h-3 w-3 ${isLoadingMemory ? "animate-spin" : ""}`}
            />
          </Button>

          <Dialog open={isAddMemoryOpen} onOpenChange={setIsAddMemoryOpen}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6">
                <Plus className="h-3 w-3" />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("chat.context.addMemory.title")}</DialogTitle>
                <DialogDescription />
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">
                    {t("chat.context.addMemory.name")}
                  </Label>
                  <Input
                    id="name"
                    value={newMemoryName}
                    onChange={(e) => setNewMemoryName(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="desc">
                    {t("chat.context.addMemory.desc")}
                  </Label>
                  <textarea
                    id="desc"
                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    value={newMemoryDesc}
                    onChange={(e) => setNewMemoryDesc(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsAddMemoryOpen(false)}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={handleAddMemory}
                  disabled={
                    addMemoryMutation.isPending || !newMemoryName.trim()
                  }
                >
                  {addMemoryMutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  {t("common.save")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-3">
          {isLoadingMemory ? (
            <div className="flex justify-center p-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : concepts?.length === 0 ? (
            <div className="text-center text-xs text-muted-foreground py-8">
              {t("chat.context.noConcepts")}
            </div>
          ) : (
            concepts?.map((c, i) => {
              const active = isActive(c.name)
              return (
                <div
                  key={i}
                  className={`mb-4 pb-4 border-b last:border-0 last:pb-0 px-1 transition-all duration-300 rounded-md ${
                    active
                      ? "bg-primary/10 border-primary ring-2 ring-primary/30 p-2"
                      : ""
                  }`}
                >
                  <div
                    className={`text-sm font-medium mb-1 flex items-center gap-2 ${active ? "text-primary" : ""}`}
                  >
                    {active && (
                      <span className="inline-block animate-pulse">●</span>
                    )}
                    {c.name}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    <MessageContent content={c.description} />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
