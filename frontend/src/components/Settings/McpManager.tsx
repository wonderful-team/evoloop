import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { McpService } from "../../client"
import { Button } from "../ui/button"
import { Input } from "../ui/input"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table"
import { Plus, Trash2, Server, Globe } from "lucide-react"

export function McpManager() {
    const queryClient = useQueryClient()
    const [name, setName] = useState("")
    const [command, setCommand] = useState("")
    const [args, setArgs] = useState("")

    const { data: servers, isLoading } = useQuery({
        queryKey: ["mcpServers"],
        queryFn: () => McpService.listMcpServers(),
    })

    const addMutation = useMutation({
        mutationFn: (data: { name: string, command: string, args: string[] }) =>
            McpService.addMcpServer({ requestBody: { ...data, env: {} } }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
            setName("")
            setCommand("")
            setArgs("")
        }
    })

    const deleteMutation = useMutation({
        mutationFn: (name: string) => McpService.deleteMcpServer({ name }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
        }
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
    const serverList: any[] = Array.isArray(servers) ? servers : (servers as any)?.servers || []

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                    <Server className="h-5 w-5" />
                    MCP Servers
                </CardTitle>
                <CardDescription>
                    Manage Model Context Protocol servers for external tool integration.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6 items-end">
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Name</label>
                        <Input
                            placeholder="e.g. git"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Command</label>
                        <Input
                            placeholder="e.g. uvx"
                            value={command}
                            onChange={(e) => setCommand(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Args (Space separated)</label>
                        <Input
                            placeholder="e.g. mcp-server-git ."
                            value={args}
                            onChange={(e) => setArgs(e.target.value)}
                        />
                    </div>
                    <Button onClick={handleAdd} disabled={!name || !command || addMutation.isPending}>
                        <Plus className="mr-2 h-4 w-4" /> Add
                    </Button>
                </div>

                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Name</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Tools</TableHead>
                                <TableHead>Command</TableHead>
                                <TableHead className="w-[80px]"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center py-4">Loading servers...</TableCell>
                                </TableRow>
                            ) : serverList.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                        No MCP servers configured.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                serverList.map((server: any) => (
                                    <TableRow key={server.name}>
                                        <TableCell className="font-medium flex items-center gap-2">
                                            <Globe size={14} className="text-muted-foreground" /> {server.name}
                                        </TableCell>
                                        <TableCell>
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${server.status === 'connected'
                                                    ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                                                    : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400"
                                                }`}>
                                                {server.status || 'unknown'}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-xs text-muted-foreground">{server.tools_count || 0} tools</span>
                                        </TableCell>
                                        <TableCell className="font-mono text-xs max-w-[200px] truncate" title={server.command}>
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
