import { useMutation, useQuery } from "@tanstack/react-query"
import {
    ExternalLink,
    FileText,
    Loader2,
    Plus,
    RefreshCw,
    X,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type ResourceResponse, ResourcesService } from "@/client"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"

interface ResourcesTabProps {
    projectId?: number
}

export function ResourcesTab({ projectId }: ResourcesTabProps) {
    const { t } = useTranslation()

    const [newLinkName, setNewLinkName] = useState("")
    const [newLinkUrl, setNewLinkUrl] = useState("")

    // 5. Resources (Pinned & Links)
    const {
        data: resources,
        isLoading: isLoadingResources,
        refetch: refetchResources,
    } = useQuery({
        queryKey: ["projectResources", projectId],
        queryFn: async () => {
            if (typeof projectId !== "number" || Number.isNaN(projectId)) return []
            return ResourcesService.listResources({ projectId })
        },
        enabled: typeof projectId === "number" && !Number.isNaN(projectId),
    })

    const addLinkMutation = useMutation({
        mutationFn: async () => {
            if (!projectId) throw new Error("No project")
            return ResourcesService.createResource({
                projectId,
                requestBody: {
                    type: "link",
                    name: newLinkName,
                    content: newLinkUrl,
                },
            })
        },
        onSuccess: () => {
            toast.success("Link added")
            setNewLinkName("")
            setNewLinkUrl("")
            refetchResources()
        },
        onError: () => toast.error("Failed to add link"),
    })

    const deleteResourceMutation = useMutation({
        mutationFn: async (id: number) => {
            if (!projectId) throw new Error("No project")
            return ResourcesService.deleteResource({ projectId, resourceId: id })
        },
        onSuccess: () => {
            toast.success("Resource removed")
            refetchResources()
        },
    })

    if (!projectId) return null

    return (
        <div className="h-full m-0 flex flex-col">
            <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
                <span className="text-xs font-medium text-muted-foreground">
                    {t("chat.context.resourcesTitle")}
                </span>
                <div className="flex gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={() => refetchResources()}
                    >
                        <RefreshCw
                            className={`h-3 w-3 ${isLoadingResources ? "animate-spin" : ""}`}
                        />
                    </Button>
                    <Dialog>
                        <DialogTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title={t("chat.context.addLink")}
                            >
                                <Plus className="h-3 w-3" />
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>
                                    {t("chat.context.addLinkTitle", "Add External Link")}
                                </DialogTitle>
                            </DialogHeader>
                            <div className="grid gap-4 py-4">
                                <div className="grid gap-2">
                                    <Label htmlFor="linkName">{t("common.name")}</Label>
                                    <Input
                                        id="linkName"
                                        placeholder="e.g. API Docs"
                                        value={newLinkName}
                                        onChange={(e) => setNewLinkName(e.target.value)}
                                    />
                                </div>
                                <div className="grid gap-2">
                                    <Label htmlFor="linkUrl">{t("common.url")}</Label>
                                    <Input
                                        id="linkUrl"
                                        placeholder="https://..."
                                        value={newLinkUrl}
                                        onChange={(e) => setNewLinkUrl(e.target.value)}
                                    />
                                </div>
                            </div>
                            <DialogFooter>
                                <Button
                                    onClick={() => addLinkMutation.mutate()}
                                    disabled={!newLinkName || !newLinkUrl}
                                >
                                    {t("common.add")}
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </div>
            </div>
            <ScrollArea className="flex-1 p-3">
                <div className="space-y-6">
                    {/* Pinned Files */}
                    <div>
                        <h4 className="text-xs font-semibold text-muted-foreground mb-2 uppercase flex items-center gap-1">
                            <FileText className="h-3 w-3" />{" "}
                            {t("chat.context.pinnedFiles", "Pinned Files")}
                        </h4>
                        {isLoadingResources ? (
                            <div className="flex justify-center p-2">
                                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                            </div>
                        ) : resources &&
                            resources.filter((r: ResourceResponse) => r.type === "file")
                                .length > 0 ? (
                            <div className="space-y-1">
                                {resources
                                    .filter((r: ResourceResponse) => r.type === "file")
                                    .map((res: ResourceResponse) => (
                                        <div
                                            key={res.id}
                                            className="flex items-center gap-2 text-xs p-1.5 hover:bg-muted rounded group relative"
                                        >
                                            <FileText className="h-3.5 w-3.5 text-blue-500" />
                                            <span
                                                className="truncate flex-1 font-mono"
                                                title={res.content}
                                            >
                                                {res.name}
                                            </span>
                                            <span className="text-[10px] text-muted-foreground truncate max-w-[100px]">
                                                {res.content}
                                            </span>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-5 w-5 opacity-0 group-hover:opacity-100 absolute right-1 bg-muted/80"
                                                onClick={() => deleteResourceMutation.mutate(res.id)}
                                            >
                                                <X className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                                            </Button>
                                        </div>
                                    ))}
                            </div>
                        ) : (
                            <div className="text-xs text-muted-foreground italic border-2 border-dashed rounded p-4 text-center">
                                {t(
                                    "chat.context.noPinnedFiles",
                                    "Right click files in file explorer to pin them here.",
                                )}
                            </div>
                        )}
                    </div>

                    {/* External Links */}
                    <div>
                        <h4 className="text-xs font-semibold text-muted-foreground mb-2 uppercase flex items-center gap-1">
                            <ExternalLink className="h-3 w-3" />{" "}
                            {t("chat.context.externalLinks", "External Links")}
                        </h4>
                        <div className="space-y-1">
                            <Button
                                variant="outline"
                                className="w-full justify-start gap-2 h-8 text-xs mb-2"
                                onClick={() => window.open("/imagicbox", "_blank")}
                            >
                                <ExternalLink className="h-3 w-3" />
                                {t("chat.context.openImagicBox")}
                            </Button>

                            {resources
                                ?.filter((r: ResourceResponse) => r.type === "link")
                                .map((res: ResourceResponse) => (
                                    <div
                                        key={res.id}
                                        className="flex items-center gap-2 text-xs p-1.5 hover:bg-muted rounded group relative"
                                    >
                                        <a
                                            href={res.content}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-2 text-xs flex-1 text-foreground hover:text-foreground no-underline"
                                        >
                                            <ExternalLink className="h-3.5 w-3.5 text-green-500" />
                                            <span className="truncate flex-1 font-medium">
                                                {res.name}
                                            </span>
                                            <span className="text-[10px] text-muted-foreground truncate max-w-[150px]">
                                                {res.content}
                                            </span>
                                        </a>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-5 w-5 opacity-0 group-hover:opacity-100 absolute right-1 bg-muted/80"
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                deleteResourceMutation.mutate(res.id)
                                            }}
                                        >
                                            <X className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                                        </Button>
                                    </div>
                                ))}
                        </div>
                    </div>
                </div>
            </ScrollArea>
        </div>
    )
}
