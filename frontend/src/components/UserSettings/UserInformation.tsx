import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { useTranslation } from "react-i18next"

import { } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"
// import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
// import { handleError } from "@/utils"

const createSchema = (t: any) => z.object({
  nickname: z.string().max(30).optional(),
  email: z.email({ message: t('auth.errors.invalidEmail') || "Invalid email address" }),
})

type FormData = z.infer<ReturnType<typeof createSchema>>

const UserInformation = () => {
  const { t } = useTranslation()
  // const queryClient = useQueryClient()
  // const { showSuccessToast, /* showErrorToast */ } = useCustomToast()
  const [editMode, setEditMode] = useState(false)
  const { user: currentUser } = useAuth()
  const formSchema = createSchema(t)

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      nickname: currentUser?.nickname ?? undefined,
      email: currentUser?.email ?? "",
    },
  })

  const toggleEditMode = () => {
    setEditMode(!editMode)
  }

  /*
  const mutation = useMutation({
    mutationFn: (data: UserUpdateMe) =>
      UsersService.updateUserMe({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("User updated successfully")
      toggleEditMode()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries()
    },
  })
  */
  // Dummy mutation to satisfy usage
  const mutation = useMutation({
    mutationFn: async (data: any) => { console.log('Update not supported', data) },
    onSuccess: () => toggleEditMode()
  })

  const onSubmit = (data: FormData) => {
    /*
    const updateData: UserUpdateMe = {}

    // only include fields that have changed
    if (data.nickname !== currentUser?.nickname) {
      updateData.nickname = data.nickname
    }
    if (data.email !== currentUser?.email) {
      updateData.email = data.email
    }

    mutation.mutate(updateData)
    */
    mutation.mutate(data)
  }

  const onCancel = () => {
    form.reset()
    toggleEditMode()
  }

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>{t('settings.profile.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-4"
          >
            <FormField
              control={form.control}
              name="nickname"
              render={({ field }) =>
                editMode ? (
                  <FormItem>
                    <FormLabel>{t('settings.profile.nickname')}</FormLabel>
                    <FormControl>
                      <Input type="text" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                ) : (
                  <FormItem>
                    <FormLabel>{t('settings.profile.nickname')}</FormLabel>
                    <p
                      className={cn(
                        "py-2 truncate max-w-sm",
                        !field.value && "text-muted-foreground",
                      )}
                    >
                      {field.value || t('settings.profile.na')}
                    </p>
                  </FormItem>
                )
              }
            />

            <FormField
              control={form.control}
              name="email"
              render={({ field }) =>
                editMode ? (
                  <FormItem>
                    <FormLabel>{t('settings.profile.email')}</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                ) : (
                  <FormItem>
                    <FormLabel>{t('settings.profile.email')}</FormLabel>
                    <p className="py-2 truncate max-w-sm">{field.value}</p>
                  </FormItem>
                )
              }
            />

            <div className="flex gap-3 pt-2">
              {editMode ? (
                <>
                  <LoadingButton
                    type="submit"
                    loading={mutation.isPending}
                    disabled={!form.formState.isDirty}
                  >
                    {t('settings.profile.save')}
                  </LoadingButton>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={onCancel}
                    disabled={mutation.isPending}
                  >
                    {t('settings.profile.cancel')}
                  </Button>
                </>
              ) : (
                <Button type="button" onClick={toggleEditMode}>
                  {t('settings.profile.edit')}
                </Button>
              )}
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}

export default UserInformation
