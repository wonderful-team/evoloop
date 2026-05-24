import { useState, useEffect, useRef } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { Phone, ShieldCheck, Loader2 } from "lucide-react"

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
import { Button } from "@evoloop/shared/components/ui/button"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

const createSchema = (t: any) =>
  z
    .object({
      mobile: z.string().regex(/^1[3-9]\d{9}$/, {
        message: t("auth.errors.invalidMobile"),
      }),
      code: z.string().length(4, {
        message: t("auth.errors.invalidCode"),
      }),
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

export const Route = createFileRoute("/recover-password")({
  component: RecoverPassword,
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
        title: "Reset Password - EvoLoop",
      },
    ],
  }),
})

function RecoverPassword() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  useEffect(() => {
    document.title = t("auth.resetPassword.pageTitle")
  }, [t])

  const { resetPasswordMutation, requestMobileCodeMutation } = useAuth()
  const [countdown, setCountdown] = useState(0)
  const [verificationKey, setVerificationKey] = useState<string | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      mobile: "",
      code: "",
      new_password: "",
      confirm_password: "",
    },
  })

  const mobileValue = form.watch("mobile")
  const isMobileValid = /^1[3-9]\d{9}$/.test(mobileValue)

  // Countdown timer effect
  useEffect(() => {
    if (countdown > 0) {
      timerRef.current = setTimeout(() => setCountdown(countdown - 1), 1000)
    } else {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [countdown])

  const handleSendCode = async () => {
    if (!isMobileValid || countdown > 0) return

    try {
      // type="findpassword" is used for password reset code
      const response = await requestMobileCodeMutation.mutateAsync({
        mobile: mobileValue,
        type: "findpassword",
      })
      
      const data = response as any
      if (data.key) {
        setVerificationKey(data.key)
      } else if (data.data?.key) {
        setVerificationKey(data.data.key)
      }
      
      setCountdown(60)
    } catch (error) {
      console.error("Failed to send code:", error)
    }
  }

  const onSubmit = async (data: FormData) => {
    if (resetPasswordMutation.isPending) return
    if (!verificationKey) {
      form.setError("code", { message: t("auth.errors.invalidCode") })
      return
    }
    
    resetPasswordMutation.mutate(
      {
        mobile: data.mobile,
        code: data.code,
        key: verificationKey,
        password: data.new_password,
      },
      {
        onSuccess: () => {
          navigate({ to: "/login" })
        },
      }
    )
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">{t("auth.reset.title")}</h1>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="mobile"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.login.mobile")}</FormLabel>
                  <div className="relative">
                    <Phone className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <FormControl>
                      <Input
                        placeholder={t("auth.login.mobilePlaceholder")}
                        className="pl-9"
                        {...field}
                      />
                    </FormControl>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.login.code")}</FormLabel>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <ShieldCheck className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                      <FormControl>
                        <Input
                          placeholder={t("auth.login.codePlaceholder")}
                          className="pl-9"
                          maxLength={4}
                          {...field}
                        />
                      </FormControl>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="w-32"
                      disabled={
                        !isMobileValid ||
                        countdown > 0 ||
                        requestMobileCodeMutation.isPending
                      }
                      onClick={handleSendCode}
                    >
                      {requestMobileCodeMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : countdown > 0 ? (
                        `${countdown}s`
                      ) : (
                        t("auth.login.getCode")
                      )}
                    </Button>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="new_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.reset.newPassword")}</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="new-password-input"
                      placeholder={t("auth.reset.newPassword")}
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
                  <FormLabel>{t("auth.reset.confirmPassword")}</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="confirm-password-input"
                      placeholder={t("auth.reset.confirmPassword")}
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
              loading={resetPasswordMutation.isPending}
              disabled={!verificationKey}
            >
              {t("auth.reset.submit")}
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            <RouterLink to="/login" className="underline underline-offset-4">
              {t("auth.reset.login")}
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
