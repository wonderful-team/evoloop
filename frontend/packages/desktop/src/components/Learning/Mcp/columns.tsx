import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import { Edit, Globe, MoreHorizontal, Trash2 } from "lucide-react"
import { Switch } from "@evoloop/shared/components/ui/switch"
import { McpService } from "@/client"
import { handleError } from "@/utils"

// Needs to match backend response or transformed data
export type McpServerPublic = {
  name: string
  command: string
  status: string
  tools_count: number
  enabled?: boolean
  // Allow optional args if backend starts providing it
  args?: string[]
}

import { useTranslation } from "react-i18next"

function DeleteServer({ name }: { name: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const deleteMutation = useMutation({
    mutationFn: (name: string) => McpService.deleteMcpServer({ name }),
    onSuccess: () => {
      showSuccessToast(t("mcp.deleteSuccess"))
      queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <DropdownMenuItem
      className="text-destructive focus:text-destructive"
      onClick={() => deleteMutation.mutate(name)}
      disabled={deleteMutation.isPending}
    >
      <Trash2 className="mr-2 h-4 w-4" /> {t("mcp.delete")}
    </DropdownMenuItem>
  )
}

function ToggleEnabled({ server }: { server: McpServerPublic }) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: (enabled: boolean) =>
      McpService.addMcpServer({
        requestBody: {
          name: server.name,
          command: server.command,
          args: server.args || [],
          env: {},
          enabled,
        },
      }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <Switch
      checked={server.enabled !== false}
      disabled={mutation.isPending}
      onCheckedChange={(checked) => mutation.mutate(checked)}
    />
  )
}

interface ColumnProps {
  onEdit: (server: McpServerPublic) => void
  t: any // Using any for simplicity with i18next TFunction
}

export const getColumns = ({
  onEdit,
  t,
}: ColumnProps): ColumnDef<McpServerPublic>[] => [
  {
    accessorKey: "name",
    header: t("mcp.table.name"),
    cell: ({ row }) => (
      <div className="flex items-center gap-2 font-medium">
        <Globe size={14} className="text-muted-foreground" />
        {row.original.name}
      </div>
    ),
  },
  {
    accessorKey: "status",
    header: t("mcp.table.status"),
    cell: ({ row }) => (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
          row.original.status === "connected"
            ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
            : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400"
        }`}
      >
        {row.original.status
          ? t([`mcp.status.${row.original.status}`, row.original.status] as any)
          : t("mcp.table.unknown")}
      </span>
    ),
  },
  {
    accessorKey: "tools_count",
    header: t("mcp.table.tools"),
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        {t("mcp.table.toolsCount", { count: row.original.tools_count || 0 })}
      </span>
    ),
  },
  {
    accessorKey: "enabled",
    header: t("mcp.table.enabled"),
    cell: ({ row }) => <ToggleEnabled server={row.original} />,
  },
  {
    accessorKey: "command",
    header: t("mcp.table.command"),
    cell: ({ row }) => (
      <span
        className="font-mono text-xs max-w-[200px] truncate block"
        title={row.original.command}
      >
        {row.original.command}
      </span>
    ),
  },
  {
    id: "actions",
    cell: ({ row }) => {
      const server = row.original

      return (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">{t("common.actions")}</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t("common.actions")}</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onEdit(server)}>
                <Edit className="mr-2 h-4 w-4" /> {t("common.edit")}
              </DropdownMenuItem>
              <DeleteServer name={server.name} />
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )
    },
  },
]
