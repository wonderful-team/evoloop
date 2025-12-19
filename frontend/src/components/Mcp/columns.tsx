import type { ColumnDef } from "@tanstack/react-table"
import { Trash2, Globe } from "lucide-react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { McpService } from "@/client"
import { Button } from "@/components/ui/button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

// Needs to match backend response or transformed data
export type McpServerPublic = {
    name: string
    command: string
    status: string
    tools_count: number
}

function DeleteServer({ name }: { name: string }) {
    const queryClient = useQueryClient()
    const { showSuccessToast, showErrorToast } = useCustomToast()

    const deleteMutation = useMutation({
        mutationFn: (name: string) => McpService.deleteMcpServer({ name }),
        onSuccess: () => {
            showSuccessToast("MCP Server removed successfully")
            queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
        },
        onError: handleError.bind(showErrorToast)
    })

    return (
        <Button
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={() => deleteMutation.mutate(name)}
            disabled={deleteMutation.isPending}
        >
            <Trash2 className="h-4 w-4" />
        </Button>
    )
}

export const columns: ColumnDef<McpServerPublic>[] = [
    {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
            <div className="flex items-center gap-2 font-medium">
                <Globe size={14} className="text-muted-foreground" />
                {row.original.name}
            </div>
        ),
    },
    {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${row.original.status === 'connected'
                ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400"
                }`}>
                {row.original.status || 'unknown'}
            </span>
        ),
    },
    {
        accessorKey: "tools_count",
        header: "Tools",
        cell: ({ row }) => (
            <span className="text-xs text-muted-foreground">{row.original.tools_count || 0} tools</span>
        ),
    },
    {
        accessorKey: "command",
        header: "Command",
        cell: ({ row }) => (
            <span className="font-mono text-xs max-w-[200px] truncate block" title={row.original.command}>
                {row.original.command}
            </span>
        ),
    },
    {
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
            <div className="flex justify-end">
                <DeleteServer name={row.original.name} />
            </div>
        ),
    },
]
