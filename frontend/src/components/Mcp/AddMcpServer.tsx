import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { Plus } from "lucide-react"
import { useState } from "react"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"

import { McpService } from "@/client"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

const mcpServerSchema = z.object({
    name: z.string().min(1, { message: "Name is required" }),
    command: z.string().min(1, { message: "Command is required" }),
    args: z.string().optional(),
})

type McpServerForm = z.infer<typeof mcpServerSchema>

export default function AddMcpServer() {
    const [open, setOpen] = useState(false)
    const queryClient = useQueryClient()
    const { showSuccessToast, showErrorToast } = useCustomToast()

    const form = useForm<McpServerForm>({
        resolver: zodResolver(mcpServerSchema),
        defaultValues: {
            name: "",
            command: "",
            args: "",
        },
    })

    const mutation = useMutation({
        mutationFn: (data: McpServerForm) => {
            // Parse args string to list
            const argsList = data.args && data.args.trim().length > 0
                ? data.args.trim().split(" ")
                : []

            return McpService.addMcpServer({
                requestBody: {
                    name: data.name,
                    command: data.command,
                    args: argsList,
                    env: {}
                }
            })
        },
        onSuccess: () => {
            showSuccessToast("MCP Server added successfully")
            setOpen(false)
            form.reset()
        },
        onError: handleError.bind(showErrorToast),
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ["mcpServers"] })
        },
    })

    const onSubmit = (data: McpServerForm) => {
        mutation.mutate(data)
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className="mr-2 h-4 w-4" /> Add Server
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Add MCP Server</DialogTitle>
                    <DialogDescription>
                        Connect a new Model Context Protocol server.
                    </DialogDescription>
                </DialogHeader>
                <Form {...form}>
                    <form
                        onSubmit={form.handleSubmit(onSubmit)}
                        className="flex flex-col gap-4"
                    >
                        <FormField
                            control={form.control}
                            name="name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Name</FormLabel>
                                    <FormControl>
                                        <Input placeholder="e.g. git" {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="command"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Command</FormLabel>
                                    <FormControl>
                                        <Input placeholder="e.g. uvx" {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="args"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Args (Space separated)</FormLabel>
                                    <FormControl>
                                        <Input placeholder="e.g. mcp-server-git ." {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <DialogFooter className="gap-2 pt-2 sm:space-x-0">
                            <DialogClose asChild>
                                <Button type="button" variant="outline">
                                    Cancel
                                </Button>
                            </DialogClose>
                            <Button type="submit" disabled={mutation.isPending}>
                                Add Server
                            </Button>
                        </DialogFooter>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    )
}
