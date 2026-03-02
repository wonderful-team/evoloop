import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useEffect } from "react"
import { z } from "zod"
import { AuthLayout } from "@/components/Common/AuthLayout"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import { LoadingButton } from "@evoloop/shared/components/ui/loading-button"
import { PasswordInput } from "@evoloop/shared/components/ui/password-input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

const createSchema = (t: any) =>
  z
    .object({
      email: z.email(),
      full_name: z
        .string()
        .min(1, { message: t("auth.errors.fullNameRequired") }),
      password: z
        .string()
        .min(1, { message: t("auth.errors.passwordRequired") })
        .min(8, { message: t("auth.errors.passwordMin8") }),
      confirm_password: z
        .string()
        .min(1, { message: t("auth.errors.confirmPasswordRequired") }),
    })
    .refine((data) => data.password === data.confirm_password, {
      message: t("auth.errors.passwordsNoMatch"),
      path: ["confirm_password"],
    })

type FormData = z.infer<ReturnType<typeof createSchema>>

export const Route = createFileRoute("/signup")({
  component: SignUp,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "Sign Up - FastAPI Cloud",
      },
    ],
  }),
})

function SignUp() {
  const { t } = useTranslation()

  useEffect(() => {
    document.title = t("auth.signup.pageTitle", "Sign Up - EvoLoop")
  }, [t])

  const { signUpMutation } = useAuth()
  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      email: "",
      full_name: "",
      password: "",
      confirm_password: "",
    },
  })

  const onSubmit = (data: FormData) => {
    if (signUpMutation.isPending) return

    // exclude confirm_password from submission data
    const { confirm_password: _confirm_password, ...submitData } = data
    signUpMutation.mutate(submitData)
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-2 text-center">
            <div className="flex flex-col items-center gap-2 text-center">
              <h1 className="text-2xl font-bold">
                {t("auth.register.desktopTitle")}
              </h1>
            </div>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="full_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.register.fullName")}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="full-name-input"
                      placeholder={t("auth.register.fullNamePlaceholder")}
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
                  <FormLabel>{t("auth.register.email")}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="email-input"
                      placeholder={t("auth.register.emailPlaceholder")}
                      type="email"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.login.passwordPlaceholder")}</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="password-input"
                      placeholder={t("auth.login.passwordPlaceholder")}
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
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t("auth.register.confirmPasswordPlaceholder")}
                  </FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="confirm-password-input"
                      placeholder={t(
                        "auth.register.confirmPasswordPlaceholder",
                      )}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <LoadingButton
              type="submit"
              className="w-full"
              loading={signUpMutation.isPending}
            >
              {t("auth.register.submit")}
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            {t("auth.register.hasAccount")}{" "}
            <RouterLink to="/login" className="underline underline-offset-4">
              {t("auth.register.login")}
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}

export default SignUp
