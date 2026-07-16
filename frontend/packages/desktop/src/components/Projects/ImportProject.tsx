import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { FolderPlus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { ProjectsService } from "@/client"
import { isTauri } from "@/lib/tauri"
import { useProjectStore } from "@/stores/projectStore"
import { handleError } from "@/utils"

const importSchema = (t: any) =>
  z.object({
    path: z
      .string()
      .min(1, { message: t("projects.import.errorPathRequired") }),
    name: z.string().optional(),
  })

type ImportProjectForm = z.infer<ReturnType<typeof importSchema>>

export default function ImportProject() {
  const [open, setOpen] = useState(false)
  const { fetchProjects } = useProjectStore()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { t } = useTranslation()
  const schema = importSchema(t)

  const form = useForm<ImportProjectForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      path: "",
      name: "",
    },
  })

  const handleBrowse = async () => {
    if (!isTauri()) {
      toast.info(
        t("settings.general.webBrowseHint") ||
          "Directory browsing is only supported in the desktop app.",
      )
      return
    }
    try {
      const { open } = await import("@tauri-apps/plugin-dialog")
      const selected = await open({
        directory: true,
        multiple: false,
      })
      if (typeof selected === "string") {
        form.setValue("path", selected)
      }
    } catch (_error) {
      toast.error(
        t("settings.general.browseError") || "Failed to select directory",
      )
    }
  }

  const mutation = useMutation({
    mutationFn: (data: ImportProjectForm) => {
      return ProjectsService.importProjectByPath({
        requestBody: {
          path: data.path,
          name: data.name || undefined,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(t("projects.import.success"))
      setOpen(false)
      form.reset()
      fetchProjects()
    },
    onError: handleError.bind(showErrorToast),
  })

  const onSubmit = (data: ImportProjectForm) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <FolderPlus className="mr-2 h-4 w-4" />{" "}
          {t("projects.import.manualImport")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{t("projects.import.title")}</DialogTitle>
          <DialogDescription>
            {t("projects.import.description")}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-4"
          >
            <FormField
              control={form.control}
              name="path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("projects.import.pathLabel")}</FormLabel>
                  <div className="flex gap-2">
                    <FormControl>
                      <Input
                        placeholder={t("projects.import.pathPlaceholder")}
                        {...field}
                      />
                    </FormControl>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-10 shrink-0"
                      onClick={handleBrowse}
                      disabled={!isTauri()}
                      title={
                        !isTauri()
                          ? t("settings.general.webBrowseHint") ||
                            "Only available in desktop app"
                          : ""
                      }
                    >
                      {t("settings.general.browse") || "Browse"}
                    </Button>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("projects.import.nameLabel")}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t("projects.import.namePlaceholder")}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
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
                {t("projects.import.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
