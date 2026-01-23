import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Plus, Server } from "lucide-react"
import * as React from "react"
// import { useState, useMemo } from "react"
import { useTranslation } from "react-i18next"

import { McpService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { getColumns } from "@/components/Mcp/columns"
import McpServerModal, {
  type McpServerPublic,
} from "@/components/Mcp/McpServerModal"
import { Button } from "@evoloop/shared/components/ui/button"

export const Route = createFileRoute("/_layout/mcp")({
  component: McpPage,
})

function McpPage() {
  const [modalOpen, setModalOpen] = React.useState(false)
  const [modalMode, setModalMode] = React.useState<"add" | "edit">("add")
  const [selectedServer, setSelectedServer] =
    React.useState<McpServerPublic | null>(null)

  const { t } = useTranslation()

  const { data: servers, isLoading } = useQuery({
    queryKey: ["mcpServers"],
    queryFn: () => McpService.listMcpServers(),
  })

  // Safe cast and format
  const serverList: any[] = Array.isArray(servers)
    ? servers
    : (servers as any)?.servers || []

  const handleAdd = () => {
    setModalMode("add")
    setSelectedServer(null)
    setModalOpen(true)
  }

  const handleEdit = (server: McpServerPublic) => {
    setModalMode("edit")
    setSelectedServer(server)
    setModalOpen(true)
  }

  const columns = React.useMemo(
    () => getColumns({ onEdit: handleEdit, t }),
    [t, handleEdit],
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("mcp.title")}
          </h1>
          <p className="text-muted-foreground">{t("mcp.description")}</p>
        </div>
        <Button onClick={handleAdd}>
          <Plus className="mr-2 h-4 w-4" /> {t("mcp.add")}
        </Button>
      </div>

      {isLoading ? (
        <div>{t("common.loading")}</div>
      ) : (
        <DataTable columns={columns} data={serverList} />
      )}

      <McpServerModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        mode={modalMode}
        initialData={selectedServer}
      />

      <div className="mt-8 border-t pt-6">
        <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
          <Server className="h-5 w-5" />
          {t("mcp.serverTitle")}
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          {t("mcp.serverInstruction")}
        </p>
        <div className="bg-muted p-4 rounded-md font-mono text-xs overflow-x-auto">
          uv run python -m app.mcp_server
        </div>
      </div>
    </div>
  )
}
