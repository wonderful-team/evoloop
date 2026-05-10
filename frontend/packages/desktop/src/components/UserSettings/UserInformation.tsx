import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { Loader2, User } from "lucide-react"
import { useSettings } from "../Settings/SettingsContext"

import { MemberService } from "@/client"
import { SettingsCard } from "../Settings/SettingsCard"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"

import { handleError } from "@/utils"

const createSchema = (t: any) =>
  z.object({
    nickname: z.string().max(30).optional(),
    email: z.string().email({
      message: t("auth.errors.invalidEmail"),
    }),
  })

type FormData = z.infer<ReturnType<typeof createSchema>>

const UserInformation = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const { user: currentUser } = useAuth()
  const formSchema = createSchema(t)
  const { setComponentDirty, registerSaveHandler, unregisterSaveHandler, registerResetHandler, isSaving } = useSettings()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      nickname: currentUser?.nickname ?? undefined,
      email: currentUser?.email ?? "",
    },
  })

  // Track dirty state
  useEffect(() => {
    setComponentDirty("user_info", form.formState.isDirty)
  }, [form.formState.isDirty, setComponentDirty])

  const handleSave = async () => {
    const data = form.getValues()
    const isValid = await form.trigger()
    if (!isValid) throw new Error("Validation failed")

    const updateData: { nickname?: string; email?: string } = {}
    if (data.nickname !== currentUser?.nickname) updateData.nickname = data.nickname
    if (data.email !== currentUser?.email) updateData.email = data.email
    
    if (Object.keys(updateData).length === 0) return

    try {
      await MemberService.updateUserMe({ requestBody: updateData })
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      form.reset(data)
    } catch (error) {
      handleError.bind(showErrorToast)(error)
      throw error
    }
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("user_info", handleSave)
    registerResetHandler("user_info", () => {
      form.reset({
        nickname: currentUser?.nickname ?? undefined,
        email: currentUser?.email ?? "",
      })
    })
    return () => unregisterSaveHandler("user_info")
  }, [registerSaveHandler, unregisterSaveHandler, registerResetHandler, currentUser, form])

  return (
    <SettingsCard 
      icon={User} 
      title={t("settings.profile.title")}
      description={t("settings.profile.description")}
      headerExtra={
        isSaving && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t("common.processing")}
          </div>
        )
      }
    >
      <Form {...form}>
        <form className="flex flex-col gap-4">
          <div className="grid gap-6 md:grid-cols-2">
            <FormField
              control={form.control}
              name="nickname"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("settings.profile.nickname")}</FormLabel>
                  <FormControl>
                    <Input 
                      className="h-10 transition-colors focus:border-primary" 
                      type="text" 
                      {...field} 
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("settings.profile.email")}</FormLabel>
                  <FormControl>
                    <Input 
                      className="h-10 transition-colors focus:border-primary" 
                      type="email" 
                      {...field} 
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </form>
      </Form>
    </SettingsCard>
  )
}

export default UserInformation
