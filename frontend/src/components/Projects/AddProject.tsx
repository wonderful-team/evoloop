import { useMutation } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useForm } from "react-hook-form"
import { Plus } from "lucide-react"
import { useState } from "react"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"

import { ProjectsService } from "@/client"
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
import { useProjectStore } from "@/stores/projectStore"

// Regex for valid directory name (alphanumeric, underscores, hyphens)
const dirNameRegex = /^[a-zA-Z0-9_-]+$/

const createSchema = (t: any) => z.object({
    name: z.string()
        .min(1, { message: t('projects.create.errorNameRequired') })
        .regex(dirNameRegex, { message: t('projects.create.errorNameFormat') }),
})

type CreateProjectForm = z.infer<ReturnType<typeof createSchema>>

export default function AddProject() {
    const [open, setOpen] = useState(false)
    // const queryClient = useQueryClient() // We use store instead
    const { fetchProjects } = useProjectStore()
    const { showSuccessToast, showErrorToast } = useCustomToast()
    const { t } = useTranslation()
    const schema = createSchema(t)

    const form = useForm<CreateProjectForm>({
        resolver: zodResolver(schema),
        defaultValues: {
            name: "",
        },
    })

    const mutation = useMutation({
        mutationFn: (data: CreateProjectForm) => {
            return ProjectsService.createProject({
                requestBody: {
                    name: data.name
                }
            })
        },
        onSuccess: () => {
            showSuccessToast(t('projects.create.success'))
            setOpen(false)
            form.reset()
            // Refresh the store
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
                    <Plus className="mr-2 h-4 w-4" /> {t('projects.new')}
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>{t('projects.create.title')}</DialogTitle>
                    <DialogDescription>
                        {t('projects.create.description')}
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
                                    <FormLabel>{t('projects.create.nameLabel')}</FormLabel>
                                    <FormControl>
                                        <Input placeholder="my-awesome-project" {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <DialogFooter className="gap-2 pt-2 sm:space-x-0">
                            <DialogClose asChild>
                                <Button type="button" variant="outline">
                                    {t('common.cancel')}
                                </Button>
                            </DialogClose>
                            <Button type="submit" disabled={mutation.isPending}>
                                {t('projects.create.submit')}
                            </Button>
                        </DialogFooter>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    )
}
