import { zodResolver } from "@hookform/resolvers/zod"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"
import { AuthService } from "../client"
import { Logo } from "../components/Common/Logo"
import { Button } from "@evoloop/shared/components/ui/button"
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
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"

// Schemas moved into component

export function RegisterScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)
  const [regMode, setRegMode] = useState<"mobile" | "account">("mobile")

  const mobileRegSchema = z.object({
    mobile: z
      .string()
      .min(11, t("auth.errors.invalidMobile"))
      .max(11, t("auth.errors.invalidMobile")),
    dynacode: z.string().min(4, t("auth.errors.codeRequired")),
    vercode: z.string().optional(),
    agreement: z
      .boolean()
      .refine((val) => val === true, t("auth.errors.mustAgree")),
  })

  const accountRegSchema = z
    .object({
      username: z
        .string()
        .min(3, t("auth.errors.usernameRequired"))
        .regex(/^[A-Za-z0-9]+$/, t("auth.register.usernamePlaceholder")),
      password: z.string().min(6, t("auth.errors.passwordTooShort")),
      rePassword: z.string(),
      vercode: z.string().optional(),
      agreement: z
        .boolean()
        .refine((val) => val === true, t("auth.errors.mustAgree")),
    })
    .refine((data) => data.password === data.rePassword, {
      message: t("auth.errors.passwordMismatch"),
      path: ["rePassword"],
    })

  // Configs
  const [config, setConfig] = useState<any>(null)
  const [captchaConfig, setCaptchaConfig] = useState(0)
  const [captcha, setCaptcha] = useState({ id: "", img: "" })

  // Mobile Code State
  const [key, setKey] = useState("")
  const [countdown, setCountdown] = useState(0)

  // Agreement Dialog
  const [agreementContent, setAgreementContent] = useState<any>(null)
  const [showAgreement, setShowAgreement] = useState(false)

  const refreshCaptcha = async () => {
    try {
      const res: any = await AuthService.getCaptcha({ id: captcha.id })
      if (res?.img) setCaptcha(res)
    } catch { }
  }

  useEffect(() => {
    // Load configurations
    const loadConfigs = async () => {
      try {
        // Parallel fetch
        const [regConf, capConf] = await Promise.all([
          AuthService.getRegisterConfig(),
          AuthService.getCaptchaConfig(),
        ])

        setConfig(regConf)
        setCaptchaConfig(Number(capConf))

        // Determine initial mode
        const rConf: any = regConf
        if (rConf?.register) {
          if (rConf.register.indexOf("mobile") !== -1) setRegMode("mobile")
          else if (rConf.register.indexOf("username") !== -1)
            setRegMode("account")
        }

        if (Number(capConf) === 1) refreshCaptcha()
      } catch (e) {
        console.error(e)
        const msg = t("auth.errors.loadConfigFailed") || "Failed to load configuration"
        toast.error(msg)
      }
    }
    loadConfigs()
  }, [])

  // Countdown
  useEffect(() => {
    let timer: NodeJS.Timeout
    if (countdown > 0) {
      timer = setInterval(() => setCountdown((c) => c - 1), 1000)
    }
    return () => clearInterval(timer)
  }, [countdown])

  const mobileForm = useForm<z.infer<typeof mobileRegSchema>>({
    resolver: zodResolver(mobileRegSchema),
    defaultValues: { mobile: "", dynacode: "", vercode: "", agreement: false },
  })

  const accountForm = useForm<z.infer<typeof accountRegSchema>>({
    resolver: zodResolver(accountRegSchema),
    defaultValues: {
      username: "",
      password: "",
      rePassword: "",
      vercode: "",
      agreement: false,
    },
  })

  const handleSendCode = async () => {
    const mobile = mobileForm.getValues("mobile")
    if (!mobile) {
      mobileForm.setError("mobile", { message: t("auth.errors.mobileRequired") })
      return
    }

    try {
      const res = await AuthService.sendMobileCode({
        mobile,
        captcha_id: captcha.id,
        captcha_code: mobileForm.getValues("vercode"),
        type: "register",
      })
      if (res?.key) {
        setKey(res.key)
        setCountdown(60)
        toast.success(t("auth.success.codeSent"))
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.errorSendingCode"))
      refreshCaptcha()
    }
  }

  const handleRegister = async (promise: Promise<any>) => {
    setIsLoading(true)
    try {
      const res = await promise
      if (res?.token) {
        localStorage.setItem("evoloop_token", res.token)
        toast.success(t("auth.success.registerSuccess"))
        // Navigate to setup or dashboard
        // Check if device binding is needed?
        navigate({ to: "/" as any })
      } else {
        toast.error(t("auth.errors.registerFailed"))
        refreshCaptcha()
      }
    } catch (e: any) {
      toast.error(e.message || t("auth.errors.registerFailed"))
      refreshCaptcha()
    } finally {
      setIsLoading(false)
    }
  }

  const onMobileSubmit = async (values: z.infer<typeof mobileRegSchema>) => {
    if (!key) {
      toast.error(t("auth.errors.sendCodeFirst"))
      return
    }

    handleRegister(
      AuthService.registerMobile({
        mobile: values.mobile,
        key,
        code: values.dynacode,
        // invite_code?
      }),
    )
  }

  const onAccountSubmit = async (values: z.infer<typeof accountRegSchema>) => {
    handleRegister(
      AuthService.registerUsername({
        username: values.username,
        password: values.password,
        captcha_id: captcha.id,
        captcha_code: values.vercode,
      })
    )
  }

  const openAgreement = async () => {
    if (!agreementContent) {
      try {
        const res: any = await AuthService.getRegisterAgreement()
        setAgreementContent(res)
      } catch { }
    }
    setShowAgreement(true)
  }

  // Determine available tabs
  const allowMobile = config?.register?.indexOf("mobile") !== -1
  const allowAccount = config?.register?.indexOf("username") !== -1

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-background relative">
      <Button
        variant="ghost"
        className="absolute top-4 left-4 pl-0 hover:bg-transparent"
        onClick={() => navigate({ to: "/login" as any })}
      >
        <ArrowLeft className="mr-2 h-6 w-6" />
        <span className="sr-only">Back</span>
      </Button>

      <div className="w-full max-w-sm pt-8">
        <div className="flex flex-col items-center space-y-2 mb-6">
          <div className="mb-2 scale-110">
            <Logo variant="icon" asLink={false} />
          </div>
          <h1 className="text-2xl font-bold">{t("auth.register.title")}</h1>
        </div>

        {config && (
          <Tabs
            value={regMode}
            onValueChange={(v) => setRegMode(v as any)}
            className="w-full"
          >
            {allowMobile && allowAccount && (
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="mobile">
                  {t("auth.register.tabMobile")}
                </TabsTrigger>
                <TabsTrigger value="account">
                  {t("auth.register.tabAccount")}
                </TabsTrigger>
              </TabsList>
            )}

            <TabsContent value="mobile">
              <Form {...mobileForm}>
                <form
                  onSubmit={mobileForm.handleSubmit(onMobileSubmit)}
                  className="space-y-4"
                >
                  <FormField
                    control={mobileForm.control}
                    name="mobile"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            placeholder={t("auth.register.mobilePlaceholder")}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {captchaConfig === 1 && (
                    <FormField
                      control={mobileForm.control}
                      name="vercode"
                      render={({ field }) => (
                        <FormItem className="relative">
                          <FormControl>
                            <Input
                              className="placeholder:text-xs"
                              placeholder={t(
                                "auth.register.captchaPlaceholder",
                              )}
                              {...field}
                            />
                          </FormControl>
                          {captcha.img && (
                            <img
                              src={captcha.img}
                              onClick={refreshCaptcha}
                              className="absolute right-1 top-1 h-8 cursor-pointer"
                            />
                          )}
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <div className="flex gap-2">
                    <FormField
                      control={mobileForm.control}
                      name="dynacode"
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormControl>
                            <Input
                              className="placeholder:text-xs"
                              placeholder={t(
                                "auth.register.smsCodePlaceholder",
                              )}
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={countdown > 0}
                      onClick={handleSendCode}
                      className="w-32"
                    >
                      {countdown > 0
                        ? `${countdown}s`
                        : t("auth.register.getCode")}
                    </Button>
                  </div>

                  {config.agreement_show === 1 && (
                    <FormField
                      control={mobileForm.control}
                      name="agreement"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md p-2">
                          <FormControl>
                            <Checkbox
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <div className="space-y-1 leading-none">
                            <span className="text-xs text-muted-foreground">
                              {t("auth.register.agree")}{" "}
                              <span
                                className="text-primary underline cursor-pointer"
                                onClick={openAgreement}
                              >
                                {t("auth.register.policy")}
                              </span>
                            </span>
                            <FormMessage />
                          </div>
                        </FormItem>
                      )}
                    />
                  )}

                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}{" "}
                    {t("auth.register.submit")}
                  </Button>
                </form>
              </Form>
            </TabsContent>

            <TabsContent value="account">
              <Form {...accountForm}>
                <form
                  onSubmit={accountForm.handleSubmit(onAccountSubmit)}
                  className="space-y-4"
                >
                  <FormField
                    control={accountForm.control}
                    name="username"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            placeholder={t("auth.register.usernamePlaceholder")}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={accountForm.control}
                    name="password"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            type="password"
                            placeholder={t("auth.register.passwordPlaceholder")}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={accountForm.control}
                    name="rePassword"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            className="placeholder:text-xs"
                            type="password"
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

                  {captchaConfig === 1 && (
                    <FormField
                      control={accountForm.control}
                      name="vercode"
                      render={({ field }) => (
                        <FormItem className="relative">
                          <FormControl>
                            <Input
                              className="placeholder:text-xs"
                              placeholder={t(
                                "auth.register.captchaPlaceholder",
                              )}
                              {...field}
                            />
                          </FormControl>
                          {captcha.img && (
                            <img
                              src={captcha.img}
                              onClick={refreshCaptcha}
                              className="absolute right-1 top-1 h-8 cursor-pointer"
                            />
                          )}
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  {config.agreement_show === 1 && (
                    <FormField
                      control={accountForm.control}
                      name="agreement"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md p-2">
                          <FormControl>
                            <Checkbox
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <div className="space-y-1 leading-none">
                            <span className="text-xs text-muted-foreground">
                              {t("auth.register.agree")}{" "}
                              <span
                                className="text-primary underline cursor-pointer"
                                onClick={openAgreement}
                              >
                                {t("auth.register.policy")}
                              </span>
                            </span>
                            <FormMessage />
                          </div>
                        </FormItem>
                      )}
                    />
                  )}

                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}{" "}
                    {t("auth.register.submit")}
                  </Button>
                </form>
              </Form>
            </TabsContent>
          </Tabs>
        )}
      </div>

      <Dialog open={showAgreement} onOpenChange={setShowAgreement}>
        <DialogContent className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{agreementContent?.title || t("auth.register.agreementsTitle")}</DialogTitle>
          </DialogHeader>
          {/* Render HTML content safely if possible, or plain text */}
          <div
            className="prose prose-sm dark:prose-invert"
            dangerouslySetInnerHTML={{
              __html: agreementContent?.content || "",
            }}
          />
        </DialogContent>
      </Dialog>

      <div className="mt-6 text-sm">
        <span className="text-muted-foreground">
          {t("auth.register.hasAccount")}{" "}
        </span>
        <Button
          variant="link"
          className="p-0 h-auto"
          onClick={() => navigate({ to: "/login" as any })}
        >
          {t("auth.register.login")}
        </Button>
      </div>
    </div>
  )
}
