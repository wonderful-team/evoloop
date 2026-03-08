import { useQuery } from "@tanstack/react-query"
import { Plus, Server } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { McpService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { getColumns } from "@/components/Mcp/columns"
import McpServerModal, {
    type McpServerPublic,
} from "@/components/Mcp/McpServerModal"
import { Button } from "@evoloop/shared/components/ui/button"

export function McpView() {
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
        <div className="flex flex-col h-full gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <Server className="h-5 w-5 text-primary" />
                        {t("mcp.title")}
                    </h2>
                    <p className="text-sm text-muted-foreground">{t("mcp.description")}</p>
                </div>
                <Button onClick={handleAdd} size="sm" className="h-9">
                    <Plus className="mr-2 h-4 w-4" /> {t("mcp.add")}
                </Button>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center py-20 text-muted-foreground animate-pulse">
                    {t("common.loading")}
                </div>
            ) : (
                <div className="border rounded-xl bg-card shadow-sm overflow-hidden">
                    <DataTable columns={columns} data={serverList} />
                </div>
            )}

            <McpServerModal
                open={modalOpen}
                onOpenChange={setModalOpen}
                mode={modalMode}
                initialData={selectedServer}
            />

        </div>
    )
}
