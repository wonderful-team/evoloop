import { ScrollArea } from "@/components/ui/scroll-area"
import { Loader2 } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { ToolsService } from "@/client/ToolsService"

export function ToolsTab() {
    // 4. Tools
    const { data: tools, isLoading: isLoadingTools } = useQuery({
        queryKey: ["tools"],
        queryFn: async () => {
            return ToolsService.listRuntimeTools()
        }
    })

    return (
        <div className="h-full m-0 flex flex-col">
            <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
                <span className="text-xs font-medium text-muted-foreground">Runtime Tools</span>
            </div>
            <ScrollArea className="flex-1 p-3">
                {isLoadingTools ? (
                    <div className="flex justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                ) : tools && tools.length > 0 ? (
                    <div className="space-y-3">
                        {tools.map((tool: any, i: number) => (
                            <div key={i} className="border rounded-md p-2 bg-card">
                                <div className="flex items-center gap-2 mb-1">
                                    <div className="font-semibold text-xs text-primary">{tool.name}</div>
                                    <div className="text-[10px] bg-muted px-1 rounded text-muted-foreground">dynamic</div>
                                </div>
                                <div className="text-xs text-muted-foreground mb-2">
                                    {tool.description}
                                </div>
                                {/* Args Schema */}
                                <div className="bg-muted/30 p-1.5 rounded text-[10px] font-mono overflow-x-auto whitespace-pre">
                                    {JSON.stringify(tool.args_schema?.properties || {}, null, 2)}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center text-xs text-muted-foreground py-8">
                        No runtime tools found.
                    </div>
                )}
            </ScrollArea>
        </div>
    )
}
