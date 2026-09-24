import {Button} from "@evoloop/shared/components/ui/button"
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
import {Form, FormControl, FormField, FormItem, FormLabel, FormMessage,} from "@evoloop/shared/components/ui/form"
import {Input} from "@evoloop/shared/components/ui/input"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import {zodResolver} from "@hookform/resolvers/zod"
import {useMutation} from "@tanstack/react-query"
import {Plus} from "lucide-react"
import {useState} from "react"
import {useForm} from "react-hook-form"
import {useTranslation} from "react-i18next"
import {z} from "zod"
import {ProjectsService} from "@/client"
import {useProjectStore} from "@/stores/projectStore"
import {handleError} from "@/utils"

const createSchema = (t: any) =>
  z.object({
    name: z
      .string()
      .min(1, { message: t("projects.create.errorNameRequired") }),
    sub_path: z.string().optional(),
  })

type CreateProjectForm = z.infer<ReturnType<typeof createSchema>>

export default function AddProject() {
  const [open, setOpen] = useState(false)
  const { fetchProjects } = useProjectStore()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { t } = useTranslation()
  const schema = createSchema(t)

  const form = useForm<CreateProjectForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      sub_path: "",
    },
  })

  const mutation = useMutation({
    mutationFn: (data: CreateProjectForm) => {
      return ProjectsService.createProject({
        requestBody: {
          name: data.name,
          sub_path: data.sub_path || undefined,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(t("projects.create.success"))
      setOpen(false)
      form.reset()
      fetchProjects()
    },
    onError: handleError.bind(showErrorToast),
  })

  const onSubmit = (data: CreateProjectForm) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" /> {t("projects.new")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{t("projects.create.title")}</DialogTitle>
          <DialogDescription>
            {t("projects.create.description")}
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
                  <FormLabel>{t("projects.create.nameLabel")}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t("projects.create.namePlaceholder")}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="sub_path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t("projects.create.subPathLabel") ||
                      t("projects.create.subPath") ||
                      "Subdirectory path (Optional)"}
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t("projects.create.subPathPlaceholder")}
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
                {t("projects.create.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
