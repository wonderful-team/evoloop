import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Globe, Plus, Server, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { McpService } from "../../client"
import { Button } from "../ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card"
import { Input } from "../ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table"

export function McpManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [command, setCommand] = useState("")
  const [args, setArgs] = useState("")

  const { data: servers, isLoading } = useQuery({
    queryKey: ["mcpServers"],
    queryFn: () => McpService.listMcpServers(),
  })

  const addMutation = useMutation({
    mutationFn: (data: { name: string; command: string; args: string[] }) =>
      McpService.addMcpServer({ requestBody: { ...data, env: {} } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
      setName("")
      setCommand("")
      setArgs("")
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => McpService.deleteMcpServer({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
    },
  })

  const handleAdd = () => {
    if (name && command) {
      // Simple space split for args, handles basic cases
      const argsList = args.trim().length > 0 ? args.trim().split(" ") : []
      addMutation.mutate({ name, command, args: argsList })
    }
  }

  // servers response might be generic object, need to check structure.
  // Assuming backend returns { servers: [...] } or just [...]
  // Previous view_file didn't show response type.
  // Usually list endpoints return array or object with list.
  // safe cast
  const serverList: any[] = Array.isArray(servers)
    ? servers
    : (servers as any)?.servers || []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Server className="h-5 w-5" />
          {t("settings.mcp.title")}
        </CardTitle>
        <CardDescription>{t("settings.mcp.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6 items-end">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t("settings.mcp.name")}
            </label>
            <Input
              placeholder={t("settings.mcp.table.name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t("settings.mcp.command")}
            </label>
            <Input
              placeholder={t("settings.mcp.table.command")}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t("settings.mcp.args")}
            </label>
            <Input
              placeholder="e.g. mcp-server-git ."
              value={args}
              onChange={(e) => setArgs(e.target.value)}
            />
          </div>
          <Button
            onClick={handleAdd}
            disabled={!name || !command || addMutation.isPending}
          >
            <Plus className="mr-2 h-4 w-4" /> {t("settings.mcp.add")}
          </Button>
        </div>

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("settings.mcp.table.name")}</TableHead>
                <TableHead>{t("settings.mcp.table.status")}</TableHead>
                <TableHead>{t("settings.mcp.table.tools")}</TableHead>
                <TableHead>{t("settings.mcp.table.command")}</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-4">
                    {t("settings.mcp.loading")}
                  </TableCell>
                </TableRow>
              ) : serverList.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center py-8 text-muted-foreground"
                  >
                    {t("settings.mcp.noServers")}
                  </TableCell>
                </TableRow>
              ) : (
                serverList.map((server: any) => (
                  <TableRow key={server.name}>
                    <TableCell className="font-medium flex items-center gap-2">
                      <Globe size={14} className="text-muted-foreground" />{" "}
                      {server.name}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          server.status === "connected"
                            ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400"
                        }`}
                      >
                        {server.status || t("settings.mcp.unknown")}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {server.tools_count || 0} {t("settings.mcp.toolsCount")}
                      </span>
                    </TableCell>
                    <TableCell
                      className="font-mono text-xs max-w-[200px] truncate"
                      title={server.command}
                    >
                      {server.command}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => deleteMutation.mutate(server.name)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
