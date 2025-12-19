import { useMutation, useQueryClient } from "@tanstack/react-query"
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

const createProjectSchema = z.object({
    name: z.string()
        .min(1, { message: "Project name is required" })
        .regex(dirNameRegex, { message: "Project name must contain only letters, numbers, underscores, or hyphens" }),
})

type CreateProjectForm = z.infer<typeof createProjectSchema>

export default function AddProject() {
    const [open, setOpen] = useState(false)
    // const queryClient = useQueryClient() // We use store instead
    const { fetchProjects } = useProjectStore()
    const { showSuccessToast, showErrorToast } = useCustomToast()

    const form = useForm<CreateProjectForm>({
        resolver: zodResolver(createProjectSchema),
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
            showSuccessToast("Project created successfully")
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
                    <Plus className="mr-2 h-4 w-4" /> New Project
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>Create New Project</DialogTitle>
                    <DialogDescription>
                        Create a new project directory. This will also sync with the Member Center.
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
                                    <FormLabel>Project Name</FormLabel>
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
                                    Cancel
                                </Button>
                            </DialogClose>
                            <Button type="submit" disabled={mutation.isPending}>
                                Create Project
                            </Button>
                        </DialogFooter>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    )
}
