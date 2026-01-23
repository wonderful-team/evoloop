import { zodResolver } from "@hookform/resolvers/zod"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
// Step schemas
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { AuthService } from "../client"
import { Logo } from "../components/Common/Logo"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"

// Step schemas moved to component

export function ForgotPasswordScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)

  // Schemas
  const step0Schema = z.object({
    mobile: z
      .string()
      .min(11, t("auth.errors.invalidMobile"))
      .max(11, t("auth.errors.invalidMobile")),
    vercode: z.string().min(1, t("auth.errors.captchaRequired")),
  })
  const step1Schema = z.object({
    dynacode: z.string().min(4, t("auth.errors.codeRequired")),
  })
  const step2Schema = z
    .object({
      password: z.string().min(6, t("auth.errors.passwordTooShort")),
      rePassword: z.string(),
    })
    .refine((data) => data.password === data.rePassword, {
      message: t("auth.errors.passwordMismatch"),
      path: ["rePassword"],
    })
  const [isLoading, setIsLoading] = useState(false)
  const [captcha, setCaptcha] = useState({ id: "", img: "" })

  // State to hold cross-step data
  const [mobile, setMobile] = useState("")
  const [key, setKey] = useState("")
  const [smsCode, setSmsCode] = useState("")

  // Countdown
  const [countdown, setCountdown] = useState(0)

  const refreshCaptcha = async () => {
    try {
      const res: any = await AuthService.getCaptcha({ id: captcha.id })
      if (res?.img) setCaptcha(res)
    } catch { }
  }

  useEffect(() => {
    refreshCaptcha()
  }, [])

  useEffect(() => {
    let timer: NodeJS.Timeout
    if (countdown > 0) {
      timer = setInterval(() => setCountdown((c) => c - 1), 1000)
    }
    return () => clearInterval(timer)
  }, [countdown])

  // Step 0 Form
  const form0 = useForm<z.infer<typeof step0Schema>>({
    resolver: zodResolver(step0Schema),
    defaultValues: { mobile: "", vercode: "" },
  })

  // Step 1 Form
  const form1 = useForm<z.infer<typeof step1Schema>>({
    resolver: zodResolver(step1Schema),
    defaultValues: { dynacode: "" },
  })

  // Step 2 Form
  const form2 = useForm<z.infer<typeof step2Schema>>({
    resolver: zodResolver(step2Schema),
    defaultValues: { password: "", rePassword: "" },
  })

  const onStep0Submit = async (values: z.infer<typeof step0Schema>) => {
    setIsLoading(true)
    try {
      /*
      // Legacy code check logic removed/commented
      */

      // 2. Send Code
      const res = await AuthService.sendMobileCode({
        mobile: values.mobile,
        captcha_id: captcha.id,
        captcha_code: values.vercode,
        type: "forget_password",
      })

      if (res?.key) {
        setKey(res.key)
        setMobile(values.mobile)
        setCountdown(60)
        setStep(1)
      } else {
        toast.error(t("auth.errors.errorSendingCode"))
        refreshCaptcha()
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.errorSendingCode"))
      refreshCaptcha()
    } finally {
      setIsLoading(false)
    }
  }

  const onStep1Submit = async (values: z.infer<typeof step1Schema>) => {
    // Just move to next step, validation happens at end
    setSmsCode(values.dynacode)
    setStep(2)
  }

  const onStep2Submit = async (values: z.infer<typeof step2Schema>) => {
    setIsLoading(true)
    try {
      const res: any = await AuthService.resetPasswordMobile({
        mobile,
        code: smsCode,
        key,
        password: values.password,
      })
      if (res) { // Assuming boolean true or success object
        toast.success(t("auth.success.reset"))
        navigate({ to: "/login" as any })
      } else {
        // ... error handling
      }
      if (res.code >= 0) {
        toast.success(t("auth.success.reset"))
        navigate({ to: "/login" as any })
      } else {
        toast.error(res.message || t("auth.errors.resetFailed"))
        // If failed, maybe code expired? go back to step 1?
        // Or step 0?
        // Legacy: stepShow -= 1 if failed.
        setStep(1)
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.resetFailed"))
    } finally {
      setIsLoading(false)
    }
  }

  const handleResend = async () => {
    // Logic to resend code?
    // We need captcha again usually?
    // Legacy `sendDynaCode` re-check captcha.
    // If captcha is consumed, user must re-enter.
    // Effectively going back to Step 0 is safest if session expired.
    toast.info(t("auth.forgotPassword.restart"))
    setStep(0)
    refreshCaptcha()
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-background relative">
      <Button
        variant="ghost"
        className="absolute top-4 left-4 pl-0 hover:bg-transparent"
        onClick={() => navigate({ to: "/login" as any })}
      >
        <ArrowLeft className="mr-2 h-6 w-6" />
        <span className="sr-only">{t("auth.forgotPassword.back")}</span>
      </Button>

      <div className="w-full max-w-sm pt-12">
        <div className="flex flex-col items-center space-y-2 mb-8">
          <Logo variant="icon" asLink={false} />
          <h1 className="text-2xl font-bold">
            {t("auth.forgotPassword.title")}
          </h1>
          <p className="text-muted-foreground text-sm">
            {step === 0 && t("auth.forgotPassword.step0")}
            {step === 1 && t("auth.forgotPassword.step1")}
            {step === 2 && t("auth.forgotPassword.step2")}
          </p>
        </div>

        {step === 0 && (
          <Form {...form0}>
            <form
              onSubmit={form0.handleSubmit(onStep0Submit)}
              className="space-y-4"
            >
              <FormField
                control={form0.control}
                name="mobile"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input
                        className="placeholder:text-xs"
                        placeholder={t("auth.forgotPassword.mobilePlaceholder")}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form0.control}
                name="vercode"
                render={({ field }) => (
                  <FormItem className="relative">
                    <FormControl>
                      <Input
                        className="placeholder:text-xs"
                        placeholder={t(
                          "auth.forgotPassword.captchaPlaceholder",
                        )}
                        {...field}
                      />
                    </FormControl>
                    {captcha.img && (
                      <img
                        src={captcha.img}
                        alt="Captcha"
                        className="absolute right-1 top-1 h-8 cursor-pointer"
                        onClick={refreshCaptcha}
                      />
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{" "}
                {t("auth.forgotPassword.next")}
              </Button>
            </form>
          </Form>
        )}

        {step === 1 && (
          <Form {...form1}>
            <form
              onSubmit={form1.handleSubmit(onStep1Submit)}
              className="space-y-4"
            >
              <div className="text-center mb-4">
                <p className="text-sm text-foreground">
                  {t("auth.forgotPassword.sentTo")} {mobile}
                </p>
              </div>
              <FormField
                control={form1.control}
                name="dynacode"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input
                        placeholder={t(
                          "auth.forgotPassword.code4DigitPlaceholder",
                        )}
                        maxLength={4}
                        className="text-center tracking-widest text-lg placeholder:text-xs"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">
                  {countdown > 0
                    ? `${t("auth.forgotPassword.resendIn")} ${countdown}s`
                    : ""}
                </span>
                {countdown === 0 && (
                  <Button
                    variant="link"
                    size="sm"
                    onClick={handleResend}
                    className="p-0"
                  >
                    {t("auth.forgotPassword.resend")}
                  </Button>
                )}
              </div>
              <Button type="submit" className="w-full">
                {t("auth.forgotPassword.next")}
              </Button>
            </form>
          </Form>
        )}

        {step === 2 && (
          <Form {...form2}>
            <form
              onSubmit={form2.handleSubmit(onStep2Submit)}
              className="space-y-4"
            >
              <FormField
                control={form2.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input
                        className="placeholder:text-xs"
                        type="password"
                        placeholder={t(
                          "auth.forgotPassword.newPasswordPlaceholder",
                        )}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form2.control}
                name="rePassword"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input
                        className="placeholder:text-xs"
                        type="password"
                        placeholder={t(
                          "auth.forgotPassword.confirmPasswordPlaceholder",
                        )}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{" "}
                {t("auth.forgotPassword.submit")}
              </Button>
            </form>
          </Form>
        )}
      </div>
    </div>
  )
}
