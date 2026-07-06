import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import { LoadingButton } from "@evoloop/shared/components/ui/loading-button"
import { PasswordInput } from "@evoloop/shared/components/ui/password-input"
import i18n from "@evoloop/shared/i18n"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { AuthService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

const createSchema = (t: any) =>
  z
    .object({
      username: z.string().min(3, {
        message: t("auth.errors.usernameMinLength"),
      }),
      password: z
        .string()
        .min(1, { message: t("auth.errors.passwordRequired") })
        .min(8, {
          message: t("auth.errors.passwordMin8"),
        }),
      confirm_password: z
        .string()
        .min(1, { message: t("auth.errors.confirmPasswordRequired") }),
      agreement: z.boolean().optional(),
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
        title: i18n.t("auth.signup.pageTitle"),
      },
    ],
  }),
})

function SignUp() {
  const { t } = useTranslation()

  useEffect(() => {
    document.title = t("auth.signup.pageTitle")
  }, [t])

  const { signUpMutation, registerConfigQuery } = useAuth()
  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      username: "",
      password: "",
      confirm_password: "",
      agreement: false,
    },
  })

  const [agreementType, setAgreementType] = useState<
    "SERVICE" | "PRIVACY" | null
  >(null)
  const [agreementContent, setAgreementContent] = useState<{
    title: string
    content: string
  } | null>(null)
  const [isAgreementLoading, setIsAgreementLoading] = useState(false)

  const showAgreement =
    registerConfigQuery.data?.data?.value?.agreement_show === "1" ||
    registerConfigQuery.data?.data?.value?.agreement_show === 1

  const handleShowAgreement = async (type: "SERVICE" | "PRIVACY") => {
    setAgreementType(type)
    setIsAgreementLoading(true)
    try {
      const res = await AuthService.getRegisterAgreement({ type })
      if (res?.data) {
        setAgreementContent(res.data as any)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setIsAgreementLoading(false)
    }
  }

  useEffect(() => {
    const handleOpenAgreement = (e: Event) => {
      const customEvent = e as CustomEvent<"SERVICE" | "PRIVACY">
      if (customEvent.detail) {
        handleShowAgreement(customEvent.detail)
      }
    }
    window.addEventListener("open-agreement", handleOpenAgreement)
    return () => {
      window.removeEventListener("open-agreement", handleOpenAgreement)
    }
  }, [])

  const onSubmit = (data: FormData) => {
    if (showAgreement && !data.agreement) {
      form.setError("agreement", {
        type: "manual",
        message: t("auth.register.agreeToTermsRequired"),
      })
      return
    }

    if (signUpMutation.isPending) return

    // exclude confirm_password and agreement from submission data
    const {
      confirm_password: _confirm_password,
      agreement: _agreement,
      ...submitData
    } = data
    signUpMutation.mutate(submitData)
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-2xl font-bold">
            {t("auth.register.desktopTitle")}
          </h1>
        </div>

        {registerConfigQuery.isLoading ? (
          <div className="flex justify-center p-8">
            <span className="text-muted-foreground">{t("common.loading")}</span>
          </div>
        ) : (
          <div className="w-full">
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="space-y-4"
              >
                <FormField
                  control={form.control}
                  name="username"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("auth.register.username")}</FormLabel>
                      <FormControl>
                        <Input
                          data-testid="username-input"
                          placeholder={t("auth.register.usernamePlaceholder")}
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
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        {t("auth.login.passwordPlaceholder")}
                      </FormLabel>
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

                {showAgreement && (
                  <FormField
                    control={form.control}
                    name="agreement"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-start space-x-2 space-y-0 rounded-md py-1">
                        <FormControl>
                          <Checkbox
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                        <div className="space-y-1 leading-tight flex-1">
                          <FormLabel className="font-normal text-xs text-muted-foreground flex flex-wrap items-center">
                            <span>{t("auth.register.agreementText")}</span>
                            <a
                              href="#"
                              onClick={(e) => {
                                e.preventDefault()
                                handleShowAgreement("SERVICE")
                              }}
                              className="text-primary hover:underline"
                            >
                              {t("auth.register.agreementService")}
                            </a>
                            <span>{t("auth.register.agreementAnd")}</span>
                            <a
                              href="#"
                              onClick={(e) => {
                                e.preventDefault()
                                handleShowAgreement("PRIVACY")
                              }}
                              className="text-primary hover:underline"
                            >
                              {t("auth.register.agreementPrivacy")}
                            </a>
                          </FormLabel>
                          <FormMessage />
                        </div>
                      </FormItem>
                    )}
                  />
                )}

                <LoadingButton
                  type="submit"
                  className="w-full"
                  loading={signUpMutation.isPending}
                >
                  {t("auth.register.submit")}
                </LoadingButton>
              </form>
            </Form>
          </div>
        )}

        <div className="text-center text-sm">
          {t("auth.register.hasAccount")}{" "}
          <RouterLink to="/login" className="underline underline-offset-4">
            {t("auth.register.login")}
          </RouterLink>
        </div>
      </div>

      <Dialog
        open={!!agreementType}
        onOpenChange={(open) => !open && setAgreementType(null)}
      >
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {agreementContent?.title ||
                (agreementType === "SERVICE"
                  ? t("auth.register.agreementService")
                  : t("auth.register.agreementPrivacy"))}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            {isAgreementLoading ? (
              <div className="flex justify-center p-8 text-muted-foreground">
                {t("common.loading")}
              </div>
            ) : (
              <div
                dangerouslySetInnerHTML={{
                  __html: agreementContent?.content || "",
                }}
                className="prose prose-sm max-w-none dark:prose-invert"
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </AuthLayout>
  )
}

export default SignUp
