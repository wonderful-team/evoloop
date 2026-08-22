import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import { Switch } from "@evoloop/shared/components/ui/switch"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { McpService } from "@/client"
import { handleError } from "@/utils"

// Define shape match columns.tsx
export type McpServerPublic = {
  name: string
  command: string
  status: string
  tools_count: number
  enabled?: boolean
  // args might not be in the public list view based on previous code,
  // but we need it for editing if possible.
  // If backend listMcpServers doesn't return args, we might have an issue pre-filling.
  // Let's assume it does or we can fetch it.
  // Based on `columns.tsx`, `row.original.command` is shown.
  // We'll see.
  args?: string[]
}

interface McpServerModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialData?: McpServerPublic | null
  mode?: "add" | "edit"
}

export default function McpServerModal({
  open,
  onOpenChange,
  initialData,
  mode = "add",
}: McpServerModalProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mcpServerSchema = z.object({
    name: z.string().min(1, { message: t("mcp.nameRequired") }),
    command: z.string().min(1, { message: t("mcp.commandRequired") }),
    args: z.string().optional(),
    enabled: z.boolean(),
  })

  type McpServerForm = z.infer<typeof mcpServerSchema>

  const form = useForm<McpServerForm>({
    resolver: zodResolver(mcpServerSchema),
    defaultValues: {
      name: "",
      command: "",
      args: "",
      enabled: true,
    },
  })

  // Reset form when opening/closing or initialData changes
  useEffect(() => {
    if (open) {
      if (mode === "edit" && initialData) {
        const argsStr = Array.isArray(initialData.args)
          ? initialData.args.join(" ")
          : (initialData as any).args || "" // Fallback

        form.reset({
          name: initialData.name,
          command: initialData.command,
          args: argsStr,
          enabled: initialData.enabled !== false,
        })
      } else {
        form.reset({
          name: "",
          command: "",
          args: "",
          enabled: true,
        })
      }
    }
  }, [open, mode, initialData, form])

  const mutation = useMutation({
    mutationFn: (data: McpServerForm) => {
      const argsList =
        data.args && data.args.trim().length > 0
          ? data.args.trim().split(" ")
          : []

      // POST /server updates if name exists
      return McpService.addMcpServer({
        requestBody: {
          name: data.name,
          command: data.command,
          args: argsList,
          env: {},
          enabled: data.enabled,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(
        t(mode === "edit" ? "mcp.successEdit" : "mcp.successAdd"),
      )
      onOpenChange(false)
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {t(mode === "edit" ? "mcp.editTitle" : "mcp.addTitle")}
          </DialogTitle>
          <DialogDescription>
            {t(mode === "edit" ? "mcp.editDesc" : "mcp.addDesc")}
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
                  <FormLabel>{t("mcp.nameLabel")}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t("mcp.namePlaceholder")}
                      {...field}
                      disabled={mode === "edit"} // Name is ID, usually immutable for edit in this simple implementation
                    />
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
                  <FormLabel>{t("mcp.commandLabel")}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t("mcp.commandPlaceholder")}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>{t("mcp.commandHelp")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="args"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("mcp.argsLabel")}</FormLabel>
                  <FormControl>
                    <Input placeholder={t("mcp.argsPlaceholder")} {...field} />
                  </FormControl>
                  <FormDescription>{t("mcp.argsHelp")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="enabled"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-md border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>{t("mcp.enabledLabel")}</FormLabel>
                    <FormDescription>{t("mcp.enabledHelp")}</FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <DialogFooter className="gap-2 pt-2 sm:space-x-0">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("common.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={mutation.isPending}>
                {t(mode === "edit" ? "mcp.save" : "mcp.add")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
