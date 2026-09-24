import {Form, FormControl, FormField, FormItem, FormLabel, FormMessage,} from "@evoloop/shared/components/ui/form"
import {LoadingButton} from "@evoloop/shared/components/ui/loading-button"
import {PasswordInput} from "@evoloop/shared/components/ui/password-input"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import {zodResolver} from "@hookform/resolvers/zod"
import {useMutation} from "@tanstack/react-query"
import {Lock} from "lucide-react"
import {useForm} from "react-hook-form"
import {useTranslation} from "react-i18next"
import {z} from "zod"
import {MemberService} from "@/client"
import {SettingsCard} from "@/components/Settings/SettingsCard"
import {handleError} from "@/utils"

const createSchema = (t: any) =>
  z
    .object({
      current_password: z
        .string()
        .min(1, { message: t("auth.errors.passwordRequired") })
        .min(8, { message: t("auth.errors.passwordMin8") }),
      new_password: z
        .string()
        .min(1, { message: t("auth.errors.passwordRequired") })
        .min(8, { message: t("auth.errors.passwordMin8") }),
      confirm_password: z
        .string()
        .min(1, { message: t("auth.errors.confirmPasswordRequired") }),
    })
    .refine((data) => data.new_password === data.confirm_password, {
      message: t("auth.errors.passwordsNoMatch"),
      path: ["confirm_password"],
    })

type FormData = z.infer<ReturnType<typeof createSchema>>

const ChangePassword = () => {
  const { t } = useTranslation()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onSubmit",
    criteriaMode: "all",
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  })

  const mutation = useMutation({
    mutationFn: async (data: FormData) => {
      return await MemberService.changePassword({
        requestBody: {
          old_password: data.current_password,
          new_password: data.new_password,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(t("settings.password.success"))
      form.reset()
    },
    onError: handleError.bind(showErrorToast),
  })

  const onSubmit = async (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <SettingsCard
      icon={Lock}
      title={t("settings.password.title")}
      description={
        t("settings.password.description") || t("auth.changePassword.desc")
      }
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <div className="grid grid-cols-1 gap-6">
            <FormField
              control={form.control}
              name="current_password"
              render={({ field, fieldState }) => (
                <FormItem>
                  <FormLabel className="text-sm font-medium">
                    {t("settings.password.current")}
                  </FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="current-password-input"
                      placeholder="••••••••"
                      aria-invalid={fieldState.invalid}
                      className="h-11"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="new_password"
                render={({ field, fieldState }) => (
                  <FormItem>
                    <FormLabel className="text-sm font-medium">
                      {t("settings.password.new")}
                    </FormLabel>
                    <FormControl>
                      <PasswordInput
                        data-testid="new-password-input"
                        placeholder="••••••••"
                        aria-invalid={fieldState.invalid}
                        className="h-11"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirm_password"
                render={({ field, fieldState }) => (
                  <FormItem>
                    <FormLabel className="text-sm font-medium">
                      {t("settings.password.confirm")}
                    </FormLabel>
                    <FormControl>
                      <PasswordInput
                        data-testid="confirm-password-input"
                        placeholder="••••••••"
                        aria-invalid={fieldState.invalid}
                        className="h-11"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t">
            <LoadingButton
              type="submit"
              loading={mutation.isPending}
              size="lg"
              className="px-10 h-11 transition-all"
            >
              {t("settings.password.update")}
            </LoadingButton>
          </div>
        </form>
      </Form>
    </SettingsCard>
  )
}

export default ChangePassword
