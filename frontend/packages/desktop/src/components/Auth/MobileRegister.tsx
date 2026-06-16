import { Button } from "@evoloop/shared/components/ui/button"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
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
import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2, Phone, ShieldCheck } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import useAuth from "@/hooks/useAuth"

const createSchema = (t: any) =>
  z
    .object({
      mobile: z.string().regex(/^1[3-9]\d{9}$/, {
        message: t("auth.errors.invalidMobile"),
      }),
      code: z.string().length(4, {
        message: t("auth.errors.invalidCode"),
      }),
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
    .and(
      z.object({
        agreement: z.boolean().optional(),
      }),
    )

type FormData = z.infer<ReturnType<typeof createSchema>>

interface MobileRegisterProps {
  onSuccess?: () => void
  showAgreement?: boolean
}

export function MobileRegister({
  onSuccess,
  showAgreement,
}: MobileRegisterProps) {
  const { t } = useTranslation()
  const { registerMobileMutation, requestMobileCodeMutation } = useAuth()
  const [countdown, setCountdown] = useState(0)
  const [verificationKey, setVerificationKey] = useState<string | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      mobile: "",
      code: "",
      password: "",
      confirm_password: "",
      agreement: false,
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
      const response = await requestMobileCodeMutation.mutateAsync({
        mobile: mobileValue,
        type: "register",
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
    if (showAgreement && !data.agreement) {
      form.setError("agreement", {
        type: "manual",
        message: t("auth.register.agreeToTermsRequired"),
      })
      return
    }

    if (!verificationKey) {
      form.setError("code", { message: t("auth.errors.invalidCode") })
      return
    }

    try {
      await registerMobileMutation.mutateAsync({
        mobile: data.mobile,
        code: data.code,
        key: verificationKey,
        password: data.password,
      })
      onSuccess?.()
    } catch (error) {
      console.error("Mobile registration failed:", error)
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
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
                  placeholder={t("auth.register.confirmPasswordPlaceholder")}
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
              <FormItem className="flex flex-row items-start space-x-2 space-y-0 rounded-md py-2">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    className="mt-0.5"
                  />
                </FormControl>
                <div className="space-y-1 leading-tight flex-1">
                  <FormLabel className="font-normal text-xs text-muted-foreground flex flex-wrap items-center gap-1">
                    <span>{t("auth.register.agreementText")}</span>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault()
                        window.dispatchEvent(
                          new CustomEvent("open-agreement", {
                            detail: "SERVICE",
                          }),
                        )
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
                        window.dispatchEvent(
                          new CustomEvent("open-agreement", {
                            detail: "PRIVACY",
                          }),
                        )
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
          loading={registerMobileMutation.isPending}
          disabled={!verificationKey}
        >
          {t("auth.register.submit")}
        </LoadingButton>
      </form>
    </Form>
  )
}
