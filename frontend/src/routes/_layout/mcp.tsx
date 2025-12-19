import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Server } from "lucide-react"


import { McpService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import AddMcpServer from "@/components/Mcp/AddMcpServer"
import { columns } from "@/components/Mcp/columns"

export const Route = createFileRoute("/_layout/mcp")({
    component: McpPage,
})

function McpTableContent() {
    const { data: servers, isLoading } = useQuery({
        queryKey: ["mcpServers"],
        queryFn: () => McpService.listMcpServers(),
    })

    // Safe cast and format
    const serverList: any[] = Array.isArray(servers) ? servers : (servers as any)?.servers || []

    if (isLoading) {
        return <div>Loading...</div>
    }

    // Always show table, even if empty (DataTable handles empty state nicely)
    return <DataTable columns={columns} data={serverList} />
}

function McpPage() {
    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">MCP Servers</h1>
                    <p className="text-muted-foreground">
                        Connect and manage external Model Context Protocol servers.
                    </p>
                </div>
                <AddMcpServer />
            </div>

            <McpTableContent />

            <div className="mt-8 border-t pt-6">
                <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
                    <Server className="h-5 w-5" />
                    EvoLoop MCP Server
                </h2>
                <p className="text-sm text-muted-foreground mb-4">
                    To use EvoLoop as an MCP Server in other tools (like Claude Desktop), configure it with the following command:
                </p>
                <div className="bg-muted p-4 rounded-md font-mono text-xs overflow-x-auto">
                    uv run python -m app.mcp_server
                </div>
            </div>
        </div>
    )
}
