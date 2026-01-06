import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useMemo } from "react"
import { ToolsService } from "@/client"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useChatStore } from "@/stores/chatStore"

export function ToolsTab() {
  // Get current tasks from chat store
  const tasks = useChatStore((state) => state.tasks)

  // Extract actively executing tools from tasks
  const activeTools = useMemo(() => {
    const toolSet = new Set<string>()
    tasks.forEach((task) => {
      // Check if task is a tool call based on name patterns and running status
      if (task.name && task.status === "running") {
        // Common tool call patterns
        const toolPatterns = [
          "read_",
          "write_",
          "search_",
          "run_",
          "manage_",
          "create_",
          "delete_",
          "view_",
          "list_",
        ]
        if (toolPatterns.some((p) => task.name.toLowerCase().includes(p))) {
          toolSet.add(task.name.toLowerCase())
        }
        // Also check details for tool names (e.g. "📄 Read `foo.tsx`")
        if (task.details) {
          const match = task.details.match(/`([^`]+)`/)
          if (match) toolSet.add(match[1].toLowerCase())
        }
      }
    })
    return toolSet
  }, [tasks])

  // Fetch available tools
  const { data: tools, isLoading: isLoadingTools } = useQuery({
    queryKey: ["tools"],
    queryFn: async () => {
      return ToolsService.listRuntimeTools()
    },
  })

  // Check if a tool is currently active
  const isToolActive = (toolName: string) => {
    const lowerName = toolName.toLowerCase()
    return (
      activeTools.has(lowerName) ||
      Array.from(activeTools).some(
        (at) => lowerName.includes(at) || at.includes(lowerName),
      )
    )
  }

  return (
    <div className="h-full m-0 flex flex-col">
      <div className="p-2 border-b bg-muted/20 flex justify-between items-center">
        <span className="text-xs font-medium text-muted-foreground">
          Runtime Tools
        </span>
        {activeTools.size > 0 && (
          <span className="text-[10px] bg-primary/20 text-primary px-1.5 rounded-full animate-pulse">
            {activeTools.size} active
          </span>
        )}
      </div>
      <ScrollArea className="flex-1 p-3">
        {isLoadingTools ? (
          <div className="flex justify-center p-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tools && tools.length > 0 ? (
          <div className="space-y-3">
            {/* Sort active tools to top */}
            {[...tools]
              .sort((a: any, b: any) => {
                const aActive = isToolActive(a.name)
                const bActive = isToolActive(b.name)
                if (aActive && !bActive) return -1
                if (!aActive && bActive) return 1
                return 0
              })
              .map((tool: any, i: number) => {
                const active = isToolActive(tool.name)
                return (
                  <div
                    key={i}
                    className={`border rounded-md p-2 transition-all duration-300 ${
                      active
                        ? "bg-primary/10 border-primary ring-2 ring-primary/30"
                        : "bg-card"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div
                        className={`font-semibold text-xs ${active ? "text-primary" : "text-muted-foreground"}`}
                      >
                        {active && (
                          <span className="inline-block animate-pulse mr-1">
                            ●
                          </span>
                        )}
                        {tool.name}
                      </div>
                      {active ? (
                        <div className="text-[10px] bg-primary/20 px-1 rounded text-primary animate-pulse">
                          active
                        </div>
                      ) : (
                        <div className="text-[10px] bg-muted px-1 rounded text-muted-foreground">
                          dynamic
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mb-2">
                      {tool.description}
                    </div>
                    {/* Args Schema - collapsed for active tools to save space */}
                    {!active && (
                      <div className="bg-muted/30 p-1.5 rounded text-[10px] font-mono overflow-x-auto whitespace-pre">
                        {JSON.stringify(
                          tool.args_schema?.properties || {},
                          null,
                          2,
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
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
